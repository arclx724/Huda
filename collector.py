# ═══════════════════════════════════════════════
#   collector.py — Concurrent Groups Scanner v3
#
#   Updates:
#   ✅ access_hash save karta hai (ban ke liye zaroori)
#   ✅ Channel ke admins automatically whitelist
#   ✅ Concurrent group scanning
#   ✅ Sirf groups scan karta hai (channels nahi)
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
#   Channel ke admins auto fetch
# ═══════════════════════════════════════════════
async def fetch_channel_admins(client):
    channel_admin_ids = set()
    logger.info("\n🔍 Channel ke admins fetch ho rahe hain...")
    try:
        async for user in client.iter_participants(
            MY_CHANNEL,
            filter=ChannelParticipantsAdmins
        ):
            channel_admin_ids.add(user.id)
            name = f"{user.first_name or ''} {user.last_name or ''}".strip()
            logger.info(f"   ⚪ Safe: {name} (ID={user.id})")
        logger.info(f"✅ {len(channel_admin_ids)} channel admins whitelist mein\n")
    except Exception as e:
        logger.warning(f"⚠️  Channel admins fetch fail: {e}")
    return channel_admin_ids


# ═══════════════════════════════════════════════
#   Single group scanner
# ═══════════════════════════════════════════════
async def scan_group(client, dialog, targets: dict, semaphore: asyncio.Semaphore, all_whitelist: set):
    async with semaphore:
        group_name = dialog.name
        found_count = 0

        try:
            async for user in client.iter_participants(
                dialog.entity,
                filter=ChannelParticipantsAdmins
            ):
                if user.is_self:
                    continue

                if user.id in all_whitelist:
                    continue

                if user.id not in targets:
                    targets[user.id] = {
                        "id": user.id,
                        # ✅ access_hash save karo — ban ke liye zaroori!
                        "access_hash": user.access_hash or 0,
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
                    # access_hash update karo agar pehle 0 tha
                    if user.access_hash and targets[user.id].get("access_hash", 0) == 0:
                        targets[user.id]["access_hash"] = user.access_hash
                    if group_name not in targets[user.id]["found_in"]:
                        targets[user.id]["found_in"].append(group_name)

            await asyncio.sleep(2)
            logger.info(f"✅ Scanned: {group_name} ({found_count} new)")
            return True, found_count

        except ChatAdminRequiredError:
            logger.warning(f"⚠️  Hidden: {group_name}")
            return False, 0

        except (ChannelPrivateError, UserNotParticipantError):
            logger.warning(f"⚠️  Access nahi: {group_name}")
            return False, 0

        except FloodWaitError as e:
            logger.warning(f"⏳ FloodWait {e.seconds}s — {group_name}")
            await asyncio.sleep(e.seconds + 2)
            return False, 0

        except Exception as e:
            logger.error(f"❌ Error: {group_name} — {type(e).__name__}")
            return False, 0


# ═══════════════════════════════════════════════
#   All groups concurrent scan
# ═══════════════════════════════════════════════
async def collect_targets(client, all_whitelist: set):
    targets = {}
    semaphore = asyncio.Semaphore(COLLECTOR_CONCURRENT)

    logger.info("\n" + "═" * 55)
    logger.info("   📋 Groups Concurrent Scanner v3")
    logger.info("═" * 55 + "\n")

    dialogs = []
    async for dialog in client.iter_dialogs():
        # Sirf groups — channels nahi
        if not dialog.is_group:
            continue

        try:
            if hasattr(dialog.entity, 'username') and dialog.entity.username == MY_CHANNEL:
                continue
        except Exception:
            pass

        dialogs.append(dialog)

    logger.info(f"📊 Total groups: {len(dialogs)}")
    logger.info(f"⚡ Concurrent: {COLLECTOR_CONCURRENT} at a time\n")

    tasks = [
        scan_group(client, d, targets, semaphore, all_whitelist)
        for d in dialogs
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    scanned = sum(1 for r in results if isinstance(r, tuple) and r[0])
    skipped = sum(1 for r in results if isinstance(r, tuple) and not r[0])

    return list(targets.values()), {
        "total_groups": len(dialogs),
        "scanned": scanned,
        "skipped": skipped,
        "total_targets": len(targets)
    }


# ═══════════════════════════════════════════════
#   Entry Point
# ═══════════════════════════════════════════════
async def main():
    from logger_setup import setup_logger
    setup_logger()

    logger.info("═" * 55)
    logger.info("   🔐 Collector v3 — With access_hash")
    logger.info("═" * 55)

    async with TelegramClient(SESSION, API_ID, API_HASH) as client:
        await client.start(phone=PHONE)
        me = await client.get_me()
        logger.info(f"✅ Login: {me.first_name} (@{me.username or 'N/A'})")

        try:
            channel = await client.get_entity(MY_CHANNEL)
            logger.info(f"📢 Channel: {channel.title}")
        except Exception as e:
            logger.error(f"❌ Channel nahi mila: {e}")
            return

        channel_admin_ids = await fetch_channel_admins(client)
        all_whitelist = set(WHITELIST_IDS) | channel_admin_ids
        logger.info(f"🛡️  Whitelist: {len(all_whitelist)} users\n")

        targets, stats = await collect_targets(client, all_whitelist)

        if not targets:
            logger.error("❌ Koi target nahi mila!")
            return

        # access_hash stats
        with_hash = sum(1 for t in targets if t.get("access_hash", 0) != 0)
        logger.info(f"🔑 access_hash: {with_hash}/{len(targets)} users ke paas hai")

        save_data = {
            "channel": MY_CHANNEL,
            "channel_id": channel.id,
            "stats": stats,
            "targets": targets
        }

        with open(TARGETS_FILE, "w", encoding="utf-8") as f:
            json.dump(save_data, f, ensure_ascii=False, indent=2)

        bots = sum(1 for t in targets if t["is_bot"])
        logger.info(f"\n{'═' * 55}")
        logger.info(f"✅ Done! Admins={len(targets)-bots} Bots={bots} Total={len(targets)}")
        logger.info(f"   Scanned={stats['scanned']} Skipped={stats['skipped']}")
        logger.info(f"   💾 Saved: {TARGETS_FILE}")
        logger.info(f"\n▶️  Ab Option 3 chalao!")


if __name__ == "__main__":
    asyncio.run(main())
    
