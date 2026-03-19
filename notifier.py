# ═══════════════════════════════════════════════
#   notifier.py — Telegram Notifications
# ═══════════════════════════════════════════════

import aiohttp
import logging
from config import NOTIFY_BOT_TOKEN, NOTIFY_USER_ID

logger = logging.getLogger(__name__)


async def send_notification(message: str, silent: bool = False):
    if not NOTIFY_BOT_TOKEN or not NOTIFY_USER_ID:
        return
    try:
        url = f"https://api.telegram.org/bot{NOTIFY_BOT_TOKEN}/sendMessage"
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json={
                "chat_id": NOTIFY_USER_ID,
                "text": message,
                "parse_mode": "HTML",
                "disable_notification": silent
            }, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                result = await resp.json()
                if not result.get("ok"):
                    logger.debug(f"Notify fail: {result.get('description')}")
    except Exception as e:
        logger.debug(f"Notify error: {e}")


async def notify_start(total, accounts):
    await send_notification(
        f"🚀 <b>Ban Started!</b>\n\n"
        f"👥 Targets: <b>{total}</b>\n"
        f"📱 Accounts: <b>{accounts}</b>"
    )


async def notify_progress(banned, total, floods):
    pct = (banned / total * 100) if total > 0 else 0
    bar = "█" * int(pct / 10) + "░" * (10 - int(pct / 10))
    await send_notification(
        f"📊 <b>Progress</b>\n[{bar}] {pct:.1f}%\n"
        f"✅ {banned}/{total} | 🌊 {floods}",
        silent=True
    )


async def notify_complete(banned, skipped, floods, mins):
    await send_notification(
        f"✅ <b>Done!</b>\n\n"
        f"✔️ Banned: <b>{banned}</b>\n"
        f"⏭️ Skipped: <b>{skipped}</b>\n"
        f"🌊 Floods: <b>{floods}</b>\n"
        f"⏱️ Time: <b>{mins:.1f} min</b>\n\n"
        f"🔒 Channel secure hai!"
    )


async def notify_error(msg):
    await send_notification(f"❌ <b>Error!</b>\n<code>{msg}</code>")


async def notify_new_admin(name, group):
    await send_notification(
        f"👀 <b>New Admin!</b>\n"
        f"👤 {name}\n"
        f"👥 {group}\n"
        f"🚫 Auto-banned!"
    )
    
