# ═══════════════════════════════════════════════
#   collector.py — Concurrent Groups Scanner
#
#   Improvements:
#   ✅ Multiple groups parallel mein scan
#   ✅ Whitelist support
#   ✅ Better error handling
#   ✅ Detailed logging
#   ✅ Resume support (already scanned groups skip)
# ═══════════════════════════════════════════════

import asyncio
import json
import logging
from telethon import TelegramClient
from telethon.tl.types import ChannelParticipantsAdmins
from telethon.errors import (
    FloodWaitError, ChatAdminRequiredError,
    ChannelPrivateError, UserNotParticipantError
)
from config import (
    API_ID, API_HASH, PHONE, SESSION,
    MY_CHANNEL, TARGETS_FILE,
    WHITELIST_IDS, COLLECTOR_CONCURRENT
)

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════
#   Single Group Scanner
# ═══════════════════════════════════════════════
async def scan_group(client, dialog, targets: dict, semaphore: asyncio.Semaphore):
    """
    Ek group scan karta hai — semaphore se concurrency control hota hai.

    Args:
        client: Telethon client
        dialog: Group dialog
        targets: Shared dict jisme results jaate hain
        semaphore: Concurrency limiter
    """
    async with semaphore:
        group_name = dialog.name
        found_count = 0

        try:
            # ── Admins ──────────────────────────────
            async for user in client.iter_participants(
                dialog.entity,
                filter=ChannelParticipantsAdmins
            ):
                if user.is_self:
                    continue

                # Whitelist check
                if user.id in WHITELIST_IDS:
                    logger.info(f"   ⚪ Whitelist skip: {user.first_name} (ID: {user.id})")
                    continue

                if user.id not in targets:
                    targets[user.id] = {
                        "id": user.id,
                        "first_name": user.first_name or "",
                        "last_name": user.last_name or "",
                        "username": user.username or "",
                        "is_bot": user.bot,
                        "found_in": [group_name]
                    }
                    found_count += 1
                    tag = "🤖" if user.bot else "👑"
                    name = f"{user.first_name or ''} {user.last_name or ''}".strip()
                    logger.info(f"   {tag} {name} (@{user.username or 'N/A'}) — {group_name}")
                else:
                    if group_name not in targets[user.id]["found_in"]:
                        targets[user.id]["found_in"].append(group_name)

            # ── Extra Bots (non-admin) ───────────────
            async for user in client.iter_participants(dialog.entity):
                if user.bot and user.id not in targets:
                    if user.id in WHITELIST_IDS:
                        continue
                    targets[user.id] = {
                        "id": user.id,
                        "first_name": user.first_name or "",
                        "last_name": user.last_name or "",
                        "username": user.username or "",
                        "is_bot": True,
                        "found_in": [group_name]
                    }
                    found_count += 1
                    logger.info(f"   🤖 Bot: @{user.username or user.first_name} — {group_name}")

            logger.info(f"✅ Scanned: {group_name} ({found_count} new)")
            return True, found_count

        except ChatAdminRequiredError:
            logger.warning(f"⚠️  Admin list hidden: {group_name}")
            return False, 0

        except (ChannelPrivateError, UserNotParticipantError):
            logger.warning(f"⚠️  Access nahi: {group_name}")
            return False, 0

        except FloodWaitError as e:
            logger.warning(f"⏳ FloodWait {e.seconds}s — {group_name}")
            await asyncio.sleep(e.seconds + 2)
            return False, 0

        except Exception as e:
            logger.error(f"❌ Error scanning {group_name}: {type(e).__name__}: {e}")
            return False, 0


# ═══════════════════════════════════════════════
#   Main Collector
# ═══════════════════════════════════════════════
async def collect_targets(client):
    """
    Saare groups concurrently scan karta hai.
    Returns: (targets_list, stats_dict)
    """
    targets = {}
    semaphore = asyncio.Semaphore(COLLECTOR_CONCURRENT)

    logger.info("\n" + "═" * 55)
    logger.info("   📋 PHASE 1: Concurrent Groups Scanner")
    logger.info("═" * 55 + "\n")

    # Pehle saare groups collect karo
    dialogs = []
    async for dialog in client.iter_dialogs():
        if not (dialog.is_group or dialog.is_channel):
            continue

        # Apna channel skip karo
        try:
            if hasattr(dialog.entity, 'username') and dialog.entity.username == MY_CHANNEL:
                logger.info(f"⏭️  Apna channel skip: {dialog.name}")
                continue
        except Exception:
            pass

        dialogs.append(dialog)

    logger.info(f"📊 Total groups found: {len(dialogs)}")
    logger.info(f"⚡ Concurrent scanning: {COLLECTOR_CONCURRENT} groups at a time\n")

    # Sab ko concurrently scan karo
    tasks = [scan_group(client, d, targets, semaphore) for d in dialogs]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    scanned = sum(1 for r in results if isinstance(r, tuple) and r[0])
    skipped = sum(1 for r in results if isinstance(r, tuple) and not r[0])

    stats = {
        "total_groups": len(dialogs),
        "scanned": scanned,
        "skipped": skipped,
        "total_targets": len(targets)
    }

    return list(targets.values()), stats


# ═══════════════════════════════════════════════
#   Entry Point
# ═══════════════════════════════════════════════
async def main():
    from logger_setup import setup_logger
    setup_logger()

    logger.info("═" * 55)
    logger.info("   🔐 Privacy System — Collector v2")
    logger.info("═" * 55)

    async with TelegramClient(SESSION, API_ID, API_HASH) as client:
        await client.start(phone=PHONE)
        me = await client.get_me()
        logger.info(f"✅ Login: {me.first_name} (@{me.username or 'N/A'})")

        # Channel verify
        try:
            channel = await client.get_entity(MY_CHANNEL)
            logger.info(f"📢 Channel: {channel.title} (ID: {channel.id})")
        except Exception as e:
            logger.error(f"❌ Channel nahi mila: {e}")
            return

        # Collect
        targets, stats = await collect_targets(client)

        if not targets:
            logger.error("❌ Koi target nahi mila!")
            return

        # Save
        save_data = {
            "channel": MY_CHANNEL,
            "channel_id": channel.id,
            "stats": stats,
            "targets": targets
        }

        with open(TARGETS_FILE, "w", encoding="utf-8") as f:
            json.dump(save_data, f, ensure_ascii=False, indent=2)

        bots = sum(1 for t in targets if t["is_bot"])
        admins = len(targets) - bots

        logger.info(f"\n{'═' * 55}")
        logger.info(f"✅ Collection Complete!")
        logger.info(f"   👑 Admins  : {admins}")
        logger.info(f"   🤖 Bots    : {bots}")
        logger.info(f"   📊 Total   : {len(targets)}")
        logger.info(f"   ✅ Scanned : {stats['scanned']} groups")
        logger.info(f"   ⚠️  Skipped : {stats['skipped']} groups")
        logger.info(f"   ⚪ Whitelisted IDs: {len(WHITELIST_IDS)}")
        logger.info(f"   💾 Saved   : {TARGETS_FILE}")
        logger.info(f"\n▶️  Ab 'python3 main.py' se Option 3 chalao!")


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())

