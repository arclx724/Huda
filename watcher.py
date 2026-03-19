# ═══════════════════════════════════════════════
#   watcher.py — Live New Admin Watcher
#
#   24/7 background mein chalta hai.
#   Koi naya admin bane toh turant channel se ban!
# ═══════════════════════════════════════════════

import asyncio
import aiohttp
import logging
from telethon import TelegramClient, events
from telethon.tl.types import (
    ChannelParticipantAdmin, ChannelParticipantCreator
)
from config import (
    API_ID, API_HASH, PHONE, SESSION,
    MY_CHANNEL, WHITELIST_IDS, EXTRA_PHONES
)
from notifier import notify_new_admin, notify_error

logger = logging.getLogger(__name__)
TELEGRAM_API = "https://api.telegram.org/bot{token}/{method}"


async def ban_via_bot(channel_id, user_id):
    """Bot API se ban karo — quick action ke liye"""
    from config import NOTIFY_BOT_TOKEN
    if not NOTIFY_BOT_TOKEN:
        return False

    if not str(channel_id).startswith("-100"):
        channel_id = int(f"-100{abs(channel_id)}")

    async with aiohttp.ClientSession() as session:
        url = TELEGRAM_API.format(token=NOTIFY_BOT_TOKEN, method="banChatMember")
        try:
            async with session.post(url, json={
                "chat_id": channel_id,
                "user_id": user_id
            }, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                result = await resp.json()
                return result.get("ok", False)
        except Exception:
            return False


async def start_watcher():
    from logger_setup import setup_logger
    setup_logger()

    logger.info("═" * 55)
    logger.info("   👀 Live Admin Watcher — Started")
    logger.info("═" * 55)

    async with TelegramClient(SESSION, API_ID, API_HASH) as client:
        await client.start(phone=PHONE)
        me = await client.get_me()
        logger.info(f"✅ Login: {me.first_name}")

        try:
            channel = await client.get_entity(MY_CHANNEL)
            channel_id = channel.id
            logger.info(f"📢 Watching: {channel.title}")
        except Exception as e:
            logger.error(f"❌ Channel nahi mila: {e}")
            return

        @client.on(events.Raw())
        async def on_raw(update):
            from telethon.tl.types import UpdateChannelParticipant
            if not isinstance(update, UpdateChannelParticipant):
                return

            new = update.new_participant
            if not isinstance(new, (ChannelParticipantAdmin, ChannelParticipantCreator)):
                return

            uid = update.user_id
            if uid in WHITELIST_IDS:
                return

            try:
                user = await client.get_entity(uid)
                name = f"{user.first_name or ''} {user.last_name or ''}".strip()

                try:
                    chat = await client.get_entity(update.channel_id)
                    group = getattr(chat, 'title', f'Group {update.channel_id}')
                except Exception:
                    group = f"Group {update.channel_id}"

                logger.info(f"🚨 New admin: {name} in {group}")

                # Ban karo channel se
                success = await ban_via_bot(channel_id, uid)
                if success:
                    logger.info(f"✅ Auto-banned: {name}")
                    await notify_new_admin(name, group)
                else:
                    logger.warning(f"⚠️  Auto-ban fail: {name} — manually ban karo!")
                    await notify_error(f"Auto-ban fail: {name} in {group}")

            except Exception as e:
                logger.debug(f"Watcher error: {e}")

        logger.info(f"\n🟢 Watcher active! Ctrl+C se band karo.")
        logger.info(f"   Channel  : {channel.title}")
        logger.info(f"   Whitelist: {len(WHITELIST_IDS)} safe users\n")

        await client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(start_watcher())
    
