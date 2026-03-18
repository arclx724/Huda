# ═══════════════════════════════════════════════
#   notifier.py — Telegram Notifications
#
#   Kya karta hai:
#   - Tumhe Telegram pe progress updates bhejta hai
#   - Kaam complete hone pe final report bhejta hai
#   - Errors aane pe alert karta hai
# ═══════════════════════════════════════════════

import aiohttp
import asyncio
import logging
from config import NOTIFY_BOT_TOKEN, NOTIFY_USER_ID

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"


async def send_notification(message: str, silent: bool = False):
    """
    Tumhare Telegram pe message bhejta hai.

    Args:
        message: Bhejne wala message
        silent: True = no notification sound
    """
    if not NOTIFY_BOT_TOKEN or NOTIFY_BOT_TOKEN == "your_notify_bot_token":
        return  # Configured nahi hai, skip

    try:
        url = TELEGRAM_API.format(token=NOTIFY_BOT_TOKEN)
        payload = {
            "chat_id": NOTIFY_USER_ID,
            "text": message,
            "parse_mode": "HTML",
            "disable_notification": silent
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                result = await resp.json()
                if not result.get("ok"):
                    logger.warning(f"Notification fail: {result.get('description')}")

    except Exception as e:
        logger.warning(f"Notification error: {e}")


async def notify_start(total_targets: int, total_bots: int):
    msg = (
        f"🚀 <b>Privacy System Started!</b>\n\n"
        f"👥 Targets: <b>{total_targets}</b>\n"
        f"🤖 Bots: <b>{total_bots}</b>\n\n"
        f"⏳ Kaam shuru ho gaya..."
    )
    await send_notification(msg)


async def notify_progress(banned: int, total: int, floods: int):
    percent = (banned / total * 100) if total > 0 else 0
    bar_filled = int(percent / 10)
    bar = "█" * bar_filled + "░" * (10 - bar_filled)

    msg = (
        f"📊 <b>Progress Update</b>\n\n"
        f"[{bar}] {percent:.1f}%\n"
        f"✅ Banned: <b>{banned}/{total}</b>\n"
        f"🌊 Floods: <b>{floods}</b>"
    )
    await send_notification(msg, silent=True)


async def notify_complete(banned: int, skipped: int, floods: int, time_min: float):
    msg = (
        f"✅ <b>Kaam Complete!</b>\n\n"
        f"✔️ Banned: <b>{banned}</b>\n"
        f"⏭️ Skipped: <b>{skipped}</b>\n"
        f"🌊 Floods: <b>{floods}</b>\n"
        f"⏱️ Time: <b>{time_min:.1f} minutes</b>\n\n"
        f"🔒 Ye log ab tumhara channel nahi dekh payenge!"
    )
    await send_notification(msg)


async def notify_error(error_msg: str):
    msg = (
        f"❌ <b>Error!</b>\n\n"
        f"<code>{error_msg}</code>\n\n"
        f"Check karo AWS server pe."
    )
    await send_notification(msg)


async def notify_bot_dead(bot_name: str, redistributed_to: list):
    msg = (
        f"⚠️ <b>Bot Down!</b>\n\n"
        f"<b>{bot_name}</b> fail ho gaya.\n"
        f"Uska kaam redistribute ho gaya: {', '.join(redistributed_to)}"
    )
    await send_notification(msg)


async def notify_new_admin(admin_name: str, group_name: str):
    msg = (
        f"👀 <b>New Admin Detected!</b>\n\n"
        f"👤 Admin: <b>{admin_name}</b>\n"
        f"👥 Group: <b>{group_name}</b>\n\n"
        f"🚫 Channel se ban kar diya gaya!"
    )
    await send_notification(msg)

