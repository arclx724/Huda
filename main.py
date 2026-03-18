"""
Telegram Userbot - DM by User ID
Library: Telethon
Author: You :)
"""

import asyncio
import logging
from telethon import TelegramClient, errors
from config import API_ID, API_HASH, SESSION_NAME, MESSAGE, USER_IDS, DELAY

# ── Logging setup ─────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s - %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("userbot.log", encoding="utf-8"),
    ]
)
log = logging.getLogger(__name__)


# ── Core Function ─────────────────────────────────────────────────────────────
async def send_dms():
    client = TelegramClient(SESSION_NAME, API_ID, API_HASH)
    await client.start()

    me = await client.get_me()
    log.info(f"Logged in as: {me.first_name} (@{me.username or 'no username'})")
    log.info(f"Total users to DM: {len(USER_IDS)}\n")

    success_count = 0
    fail_count = 0

    for user_id in USER_IDS:
        try:
            await client.send_message(int(user_id), MESSAGE)
            log.info(f"✅ Sent to user_id: {user_id}")
            success_count += 1

        except errors.UserIsBlockedError:
            log.warning(f"🚫 Blocked by user_id: {user_id}")
            fail_count += 1

        except errors.PeerFloodError:
            log.error("⛔ PeerFloodError! Telegram is rate limiting you. Stopping to protect account.")
            break

        except errors.InputUserDeactivatedError:
            log.warning(f"❌ Account deleted/deactivated: {user_id}")
            fail_count += 1

        except errors.UserPrivacyRestrictedError:
            log.warning(f"🔒 Privacy settings block DM: {user_id}")
            fail_count += 1

        except errors.FloodWaitError as e:
            log.warning(f"⏳ FloodWait! Sleeping for {e.seconds} seconds...")
            await asyncio.sleep(e.seconds)

        except Exception as e:
            log.error(f"⚠️ Unexpected error for {user_id}: {e}")
            fail_count += 1

        # Delay between each DM to avoid spam detection
        await asyncio.sleep(DELAY)

    log.info(f"\n── Done ──────────────────────────")
    log.info(f"✅ Success : {success_count}")
    log.info(f"❌ Failed  : {fail_count}")
    log.info(f"📋 Total   : {len(USER_IDS)}")

    await client.disconnect()


# ── Entry Point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    asyncio.run(send_dms())

