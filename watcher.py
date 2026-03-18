# ═══════════════════════════════════════════════
#   watcher.py — Live New Admin Watcher
#
#   Kya karta hai:
#   - Tumhare saare groups monitor karta hai
#   - Koi naya admin add ho toh turant detect karta hai
#   - Automatically channel se ban kar deta hai
#   - Tumhe Telegram pe notify karta hai
#   - 24/7 background mein chalta hai
# ═══════════════════════════════════════════════

import asyncio
import aiohttp
import logging
from telethon import TelegramClient, events
from telethon.tl.types import (
    ChatAdminRights, ChannelParticipantAdmin,
    ChannelParticipantCreator
)
from config import (
    API_ID, API_HASH, PHONE, SESSION,
    MY_CHANNEL, BOTS, WHITELIST_IDS
)
from notifier import notify_new_admin, notify_error

logger = logging.getLogger(__name__)
TELEGRAM_API = "https://api.telegram.org/bot{token}/{method}"


# ═══════════════════════════════════════════════
#   Ban via Bot API
# ═══════════════════════════════════════════════
async def ban_user_via_bot(channel_id, user_id):
    """
    Pehle available bot se user ko ban karta hai.
    Ek bot fail ho toh doosra try karta hai.
    """
    if not str(channel_id).startswith("-100"):
        channel_id_full = int(f"-100{abs(channel_id)}")
    else:
        channel_id_full = channel_id

    async with aiohttp.ClientSession() as session:
        for i, token in enumerate(BOTS):
            url = TELEGRAM_API.format(token=token, method="banChatMember")
            try:
                async with session.post(url, json={
                    "chat_id": channel_id_full,
                    "user_id": user_id,
                    "revoke_messages": False
                }, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    result = await resp.json()

                    if result.get("ok"):
                        logger.info(f"✅ Ban success via Bot{i+1}")
                        return True

                    error = result.get("description", "")
                    # Already banned ya user nahi hai — OK hai
                    if "USER_NOT_PARTICIPANT" in error or "PARTICIPANT_ID_INVALID" in error:
                        return True

                    logger.warning(f"Bot{i+1} fail: {error}")

            except Exception as e:
                logger.warning(f"Bot{i+1} exception: {e}")
                continue

    logger.error(f"❌ Saare bots fail ho gaye user {user_id} ke liye")
    return False


# ═══════════════════════════════════════════════
#   Watcher
# ═══════════════════════════════════════════════
async def start_watcher():
    from logger_setup import setup_logger
    setup_logger()

    logger.info("═" * 55)
    logger.info("   👀 Live Admin Watcher — Started")
    logger.info("═" * 55)

    async with TelegramClient(SESSION, API_ID, API_HASH) as client:
        await client.start(phone=PHONE)
        me = await client.get_me()
        logger.info(f"✅ Login: {me.first_name} (@{me.username})")

        # Channel entity fetch
        try:
            channel = await client.get_entity(MY_CHANNEL)
            channel_id = channel.id
            logger.info(f"📢 Watching for: {channel.title}")
        except Exception as e:
            logger.error(f"❌ Channel nahi mila: {e}")
            await notify_error(f"Watcher start fail: {e}")
            return

        # ── Event Handler: Admin Change ───────────
        @client.on(events.ChatAction())
        async def on_chat_action(event):
            """
            Ye event tab fire hota hai jab:
            - Koi admin banta hai
            - Koi member join karta hai
            - Koi leave karta hai
            """
            try:
                # Sirf admin promotion events
                if not (event.user_added or event.user_joined):
                    return

                # Affected user ko check karo
                user = await event.get_user()
                if not user or user.is_self:
                    return

                if user.id in WHITELIST_IDS:
                    return

                # Check karo ki ye user admin hai kisi group mein
                chat = await event.get_chat()

                try:
                    participant = await client.get_permissions(chat, user)

                    is_admin = (
                        hasattr(participant, 'is_admin') and participant.is_admin or
                        hasattr(participant, 'is_creator') and participant.is_creator
                    )

                    if is_admin:
                        name = f"{user.first_name or ''} {user.last_name or ''}".strip()
                        group_name = getattr(chat, 'title', 'Unknown Group')

                        logger.info(f"🚨 New Admin detected: {name} in {group_name}")

                        # Ban karo channel se
                        success = await ban_user_via_bot(channel_id, user.id)

                        if success:
                            logger.info(f"✅ Auto-banned: {name}")
                            await notify_new_admin(name, group_name)
                        else:
                            logger.error(f"❌ Auto-ban fail: {name}")
                            await notify_error(f"Auto-ban fail: {name} in {group_name}")

                except Exception:
                    pass

            except Exception as e:
                logger.debug(f"Event handler error: {e}")

        # ── Event Handler: Admin Rights Changed ───
        @client.on(events.Raw())
        async def on_raw_update(update):
            """
            Raw updates se admin promotion detect karta hai
            (ChatAction se jo miss ho jaye)
            """
            from telethon.tl.types import (
                UpdateChannelParticipant,
                ChannelParticipantAdmin,
                ChannelParticipantCreator
            )

            if not isinstance(update, UpdateChannelParticipant):
                return

            new_participant = update.new_participant

            # Naya admin ban gaya?
            if not isinstance(new_participant, (ChannelParticipantAdmin, ChannelParticipantCreator)):
                return

            user_id = update.user_id

            if user_id in WHITELIST_IDS:
                return

            try:
                user = await client.get_entity(user_id)
                name = f"{user.first_name or ''} {user.last_name or ''}".strip()

                # Group name dhundho
                try:
                    chat = await client.get_entity(update.channel_id)
                    group_name = getattr(chat, 'title', f'Group {update.channel_id}')
                except Exception:
                    group_name = f"Group {update.channel_id}"

                logger.info(f"🚨 Admin promoted: {name} in {group_name}")

                success = await ban_user_via_bot(channel_id, user_id)

                if success:
                    logger.info(f"✅ Auto-banned: {name}")
                    await notify_new_admin(name, group_name)
                else:
                    await notify_error(f"Auto-ban fail: {name}")

            except Exception as e:
                logger.debug(f"Raw update handler error: {e}")

        logger.info(f"\n🟢 Watcher active! Ctrl+C se band karo.\n")
        logger.info(f"   Monitoring: All joined groups")
        logger.info(f"   Channel  : {channel.title}")
        logger.info(f"   Whitelist: {len(WHITELIST_IDS)} users safe\n")

        # Forever run karo
        await client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(start_watcher())

