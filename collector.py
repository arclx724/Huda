# ═══════════════════════════════════════════════
#   collector.py — Final Version
#
#   Flow:
#   1. Channel ke admins whitelist mein daalo
#   2. Saare groups scan karo (concurrent)
#   3. access_hash properly save karo
#   4. Unmilne wale users ko resolve karo (cache se)
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
#   Step 1: Channel admins whitelist
# ═══════════════════════════════════════════════
async def fetch_channel_admins(client):
    ids = set()
    logger.info("🔍 Channel admins fetch ho rahe hain...")
    try:
        async for user in client.iter_participants(
            MY_CHANNEL, filter=ChannelParticipantsAdmins
        ):
            ids.add(user.id)
            name = f"{user.first_name or ''} {user.last_name or ''}".strip()
            logger.info(f"   ⚪ Safe (channel admin): {name}")
        logger.info(f"✅ {len(ids)} channel admins whitelist mein\n")
    except Exception as e:
        logger.warning(f"⚠️  Channel admins fetch fail: {e}")
    return ids


# ═══════════════════════════════════════════════
#   Step 2: Single group scan
# ═══════════════════════════════════════════════
async def scan_group(client, dialog, targets: dict, semaphore, all_whitelist: set):
    async with semaphore:
        group_name = dialog.name
        found = 0

        try:
            async for user in client.iter_participants(
                dialog.entity,
                filter=ChannelParticipantsAdmins
            ):
                if user.is_self or user.id in all_whitelist:
                    continue

                if user.id not in targets:
                    targets[user.id] = {
                        "id": user.id,
                        "access_hash": user.access_hash or 0,
                        "first_name": user.first_name or "",
                        "last_name": user.last_name or "",
                        "username": user.username or "",
                        "is_bot": user.bot,
                        "found_in": [group_name]
                    }
                    found += 1
                    tag = "🤖" if user.bot else "👑"
                    name = f"{user.first_name or ''} {user.last_name or ''}".strip()
                    logger.info(f"   {tag} {name} (@{user.username or 'N/A'})")
                else:
                    # access_hash update karo agar better value mili
                    if user.access_hash and targets[user.id].get("access_hash", 0) == 0:
                        targets[user.id]["access_hash"] = user.access_hash
                    if group_name not in targets[user.id]["found_in"]:
                        targets[user.id]["found_in"].append(group_name)

            await asyncio.sleep(2)
            logger.info(f"✅ {group_name} — {found} new")
            return True

        except ChatAdminRequiredError:
            logger.warning(f"⚠️  Hidden: {group_name}")
            return False
        except (ChannelPrivateError, UserNotParticipantError):
            logger.warning(f"⚠️  No access: {group_name}")
            return False
        except FloodWaitError as e:
            logger.warning(f"⏳ FloodWait {e.seconds}s")
            await asyncio.sleep(e.seconds + 2)
            return False
        except Exception as e:
            logger.error(f"❌ {group_name}: {type(e).__name__}")
            return False


# ═══════════════════════════════════════════════
#   Step 3: Resolve missing access_hashes
#   (Main account ke session cache se)
# ═══════════════════════════════════════════════
async def resolve_missing_hashes(client, targets: dict):
    """
    Jo users ka access_hash 0 hai, unhe
    Telethon session cache se resolve karta hai.
    Main account ne scanning ke time sab cache kar liya hai!
    """
    missing = [t for t in targets.values() if t.get("access_hash", 0) == 0]

    if not missing:
        logger.info("✅ Saare users ke paas access_hash hai!")
        return

    logger.info(f"\n🔑 {len(missing)} users ka access_hash resolve ho raha hai...")
    resolved = 0
    failed = 0

    for user in missing:
        try:
            # Session cache se entity lo
            entity = await client.get_input_entity(user["id"])
            if hasattr(entity, "access_hash") and entity.access_hash:
                targets[user["id"]]["access_hash"] = entity.access_hash
                resolved += 1
            else:
                failed += 1
        except Exception:
            # Username se try karo
            if user.get("username"):
                try:
                    entity = await client.get_input_entity(f"@{user['username']}")
                    if hasattr(entity, "access_hash") and entity.access_hash:
                        targets[user["id"]]["access_hash"] = entity.access_hash
                        resolved += 1
                        continue
                except Exception:
                    pass
            failed += 1
        await asyncio.sleep(0.1)

    logger.info(f"🔑 Resolved: {resolved} | Still missing: {failed}")
    if failed > 0:
        logger.info(f"ℹ️  {failed} users Telegram privacy hide kar rahe hain — skip honge")


# ═══════════════════════════════════════════════
#   Main Collector
# ═══════════════════════════════════════════════
async def main():
    from logger_setup import setup_logger
    setup_logger()

    logger.info("═" * 55)
    logger.info("   🔐 Collector — Final Version")
    logger.info("═" * 55)

    async with TelegramClient(SESSION, API_ID, API_HASH) as client:
        await client.start(phone=PHONE)
        me = await client.get_me()
        logger.info(f"✅ Login: {me.first_name} (@{me.username or 'N/A'})")

        # Channel verify
        try:
            channel = await client.get_entity(MY_CHANNEL)
            logger.info(f"📢 Channel: {channel.title}")
        except Exception as e:
            logger.error(f"❌ Channel nahi mila: {e}")
            return

        # Channel admins whitelist
        channel_admins = await fetch_channel_admins(client)
        all_whitelist = set(WHITELIST_IDS) | channel_admins
        logger.info(f"🛡️  Whitelist: {len(all_whitelist)} users\n")

        # Saare groups scan karo
        targets = {}
        semaphore = asyncio.Semaphore(COLLECTOR_CONCURRENT)
        dialogs = []

        logger.info("📋 Groups collect ho rahe hain...")
        async for dialog in client.iter_dialogs():
            if not dialog.is_group:
                continue
            try:
                if hasattr(dialog.entity, 'username') and dialog.entity.username == MY_CHANNEL:
                    continue
            except Exception:
                pass
            dialogs.append(dialog)

        logger.info(f"📊 Total groups: {len(dialogs)}\n")

        tasks = [scan_group(client, d, targets, semaphore, all_whitelist) for d in dialogs]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        scanned = sum(1 for r in results if r is True)
        skipped = sum(1 for r in results if r is False)

        logger.info(f"\n📊 Scan done: {scanned} scanned, {skipped} skipped")
        logger.info(f"👥 Collected: {len(targets)} users\n")

        # Missing access_hashes resolve karo
        await resolve_missing_hashes(client, targets)

        if not targets:
            logger.error("❌ Koi target nahi mila!")
            return

        # Save
        with_hash = sum(1 for t in targets.values() if t.get("access_hash", 0) != 0)
        without_hash = len(targets) - with_hash

        save_data = {
            "channel": MY_CHANNEL,
            "channel_id": channel.id,
            "stats": {
                "total_groups": len(dialogs),
                "scanned": scanned,
                "skipped": skipped,
                "total_targets": len(targets),
                "with_hash": with_hash,
                "without_hash": without_hash
            },
            "targets": list(targets.values())
        }

        with open(TARGETS_FILE, "w", encoding="utf-8") as f:
            json.dump(save_data, f, ensure_ascii=False, indent=2)

        bots = sum(1 for t in targets.values() if t["is_bot"])
        logger.info(f"\n{'═' * 55}")
        logger.info(f"✅ Collection Complete!")
        logger.info(f"   👑 Admins    : {len(targets) - bots}")
        logger.info(f"   🤖 Bots      : {bots}")
        logger.info(f"   📊 Total     : {len(targets)}")
        logger.info(f"   🔑 With hash : {with_hash}")
        logger.info(f"   ⚠️  No hash   : {without_hash} (skip honge)")
        logger.info(f"   💾 Saved     : {TARGETS_FILE}")
        logger.info(f"\n▶️  Ab Option 3 (Ban) chalao!")


if __name__ == "__main__":
    asyncio.run(main())
            
