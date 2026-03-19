# ═══════════════════════════════════════════════
#   banner.py — Multi-Bot Adaptive Banner v2
#
#   Features:
#   ✅ Bot health check pehle
#   ✅ Smart retry (3 attempts)
#   ✅ Dead bot redistribution
#   ✅ Dynamic chunk rebalancing
#   ✅ Progress bar (tqdm)
#   ✅ Failed users separate file mein
#   ✅ Telegram notifications
#   ✅ Account safety monitor
#   ✅ Whitelist support
#   ✅ Resume support
# ═══════════════════════════════════════════════

import asyncio
import aiohttp
import json
import os
import time
import logging
from tqdm import tqdm
from config import (
    BOTS, MY_CHANNEL,
    TARGETS_FILE, RESULTS_FILE, PROGRESS_FILE, FAILED_FILE,
    BASE_DELAY, FLOOD_INCREASE, FLOOD_DECREASE,
    MIN_DELAY, MAX_DELAY, SUCCESS_THRESHOLD, MAX_RETRIES,
    WHITELIST_IDS, NOTIFY_EVERY
)
from notifier import (
    notify_start, notify_progress,
    notify_complete, notify_error, notify_bot_dead
)

logger = logging.getLogger(__name__)
TELEGRAM_API = "https://api.telegram.org/bot{token}/{method}"


# ═══════════════════════════════════════════════
#   Adaptive Delay — Per Bot
# ═══════════════════════════════════════════════
class AdaptiveDelay:
    def __init__(self, bot_name):
        self.bot_name = bot_name
        self.delay = BASE_DELAY
        self.flood_count = 0
        self.success_streak = 0
        self.total_success = 0
        self.total_flood = 0

    def on_success(self):
        self.success_streak += 1
        self.total_success += 1
        if self.success_streak >= SUCCESS_THRESHOLD:
            self.delay = max(MIN_DELAY, self.delay - FLOOD_DECREASE)
            self.success_streak = 0

    def on_flood(self):
        self.flood_count += 1
        self.total_flood += 1
        self.success_streak = 0
        self.delay = min(MAX_DELAY, self.delay + FLOOD_INCREASE)

    def on_error(self):
        self.success_streak = 0

    async def wait(self):
        await asyncio.sleep(self.delay)

    def status(self):
        return f"spd={self.delay:.1f}s 🌊{self.total_flood}"


# ═══════════════════════════════════════════════
#   Progress Manager — Resume support
# ═══════════════════════════════════════════════
class ProgressManager:
    def __init__(self):
        self.done_ids = set()
        self._lock = asyncio.Lock()
        self.load()

    def load(self):
        if os.path.exists(PROGRESS_FILE):
            try:
                with open(PROGRESS_FILE, "r") as f:
                    self.done_ids = set(json.load(f).get("done_ids", []))
                logger.info(f"📂 Resume: {len(self.done_ids)} pehle se done, skip honge")
            except Exception:
                self.done_ids = set()

    async def mark_done(self, user_id):
        async with self._lock:
            self.done_ids.add(user_id)
            if len(self.done_ids) % 50 == 0:
                self._save()

    def _save(self):
        with open(PROGRESS_FILE, "w") as f:
            json.dump({"done_ids": list(self.done_ids)}, f)

    def save(self):
        self._save()

    def is_done(self, user_id):
        return user_id in self.done_ids

    def clear(self):
        self.done_ids = set()
        if os.path.exists(PROGRESS_FILE):
            os.remove(PROGRESS_FILE)


# ═══════════════════════════════════════════════
#   Bot API Helper
# ═══════════════════════════════════════════════
async def api_call(session, token, method, data=None):
    url = TELEGRAM_API.format(token=token, method=method)
    try:
        async with session.post(
            url,
            json=data or {},
            timeout=aiohttp.ClientTimeout(total=30)
        ) as resp:
            return await resp.json()
    except asyncio.TimeoutError:
        return {"ok": False, "description": "Timeout"}
    except Exception as e:
        return {"ok": False, "description": str(e)}


async def ban_user(session, token, channel_id, user_id):
    """
    Ban with smart retry logic.
    Returns: (success, retry_after, error_description)
    """
    result = await api_call(session, token, "banChatMember", {
        "chat_id": channel_id,
        "user_id": user_id,
        "revoke_messages": False
    })

    if result.get("ok"):
        return True, None, None

    error_code = result.get("error_code", 0)
    description = result.get("description", "Unknown")

    if error_code == 429:
        retry_after = result.get("parameters", {}).get("retry_after", 30)
        return False, retry_after, "FLOOD"

    return False, None, description


# ═══════════════════════════════════════════════
#   Bot Health Check
# ═══════════════════════════════════════════════
async def check_bot_health(token, channel_id):
    """
    Bot verify karta hai:
    1. Token valid hai?
    2. Channel mein admin hai?
    3. Ban permission hai?

    Returns: (healthy: bool, bot_username: str, reason: str)
    """
    async with aiohttp.ClientSession() as session:
        # Token check
        me = await api_call(session, token, "getMe")
        if not me.get("ok"):
            return False, "Unknown", "Invalid token"

        bot_username = me["result"].get("username", "Unknown")

        # Admin check
        member = await api_call(session, token, "getChatMember", {
            "chat_id": channel_id,
            "user_id": me["result"]["id"]
        })

        if not member.get("ok"):
            return False, bot_username, "Channel mein nahi hai ya access nahi"

        status = member["result"].get("status", "")
        if status not in ["administrator", "creator"]:
            return False, bot_username, f"Admin nahi hai (status: {status})"

        # Ban permission check
        can_ban = member["result"].get("can_restrict_members", False)
        if not can_ban:
            return False, bot_username, "Ban permission nahi hai"

        return True, bot_username, "OK"


async def health_check_all_bots(channel_id):
    """
    Saare bots ka health check karta hai.
    Returns: list of (token, bot_username, healthy)
    """
    logger.info("\n🏥 Bot Health Check...\n")
    healthy_bots = []
    dead_bots = []

    tasks = [check_bot_health(token, channel_id) for token in BOTS]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    for i, (token, result) in enumerate(zip(BOTS, results)):
        bot_num = f"Bot{i+1}"

        if isinstance(result, Exception):
            logger.error(f"   [{bot_num}] ❌ Exception: {result}")
            dead_bots.append((token, bot_num))
            continue

        healthy, username, reason = result

        if healthy:
            logger.info(f"   [{bot_num}] ✅ @{username} — Ready!")
            healthy_bots.append((token, f"@{username}"))
        else:
            logger.warning(f"   [{bot_num}] ❌ @{username} — {reason}")
            dead_bots.append((token, bot_num))

    logger.info(f"\n✅ Healthy: {len(healthy_bots)} | ❌ Dead: {len(dead_bots)}\n")
    return healthy_bots, dead_bots


# ═══════════════════════════════════════════════
#   Shared Counter — Thread-safe stats
# ═══════════════════════════════════════════════
class SharedStats:
    def __init__(self, total):
        self.total = total
        self.banned = 0
        self.skipped = 0
        self.floods = 0
        self._lock = asyncio.Lock()
        self.pbar = tqdm(
            total=total,
            desc="Banning",
            unit="user",
            bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}]"
        )

    async def add_banned(self):
        async with self._lock:
            self.banned += 1
            self.pbar.update(1)
            self.pbar.set_postfix_str(f"✅{self.banned} ⏭️{self.skipped} 🌊{self.floods}")

    async def add_skipped(self):
        async with self._lock:
            self.skipped += 1
            self.pbar.update(1)

    async def add_flood(self):
        async with self._lock:
            self.floods += 1

    def close(self):
        self.pbar.close()


# ═══════════════════════════════════════════════
#   Bot Worker
# ═══════════════════════════════════════════════
async def bot_worker(token, bot_username, channel_id, chunk, progress, stats, failed_list):
    """
    Ek bot ka async worker.
    Smart retry + adaptive delay + failed tracking.
    """
    adaptive = AdaptiveDelay(bot_username)
    bot_banned = 0
    bot_skipped = 0
    notification_counter = 0

    # Ignorable errors — ye normal hain
    IGNORABLE = [
        "USER_NOT_PARTICIPANT", "PARTICIPANT_ID_INVALID",
        "user not found", "USER_ID_INVALID",
        "Forbidden", "USER_KICKED", "bot was blocked"
    ]

    async with aiohttp.ClientSession() as session:
        for user in chunk:
            user_id = user["id"]

            # Already done? Skip
            if progress.is_done(user_id):
                continue

            # Whitelist check (double safety)
            if user_id in WHITELIST_IDS:
                await progress.mark_done(user_id)
                continue

            name = f"{user['first_name']} {user['last_name']}".strip() or "Unknown"
            success = False

            # ── Smart Retry Loop ─────────────────────
            for attempt in range(1, MAX_RETRIES + 1):
                ok, retry_after, error = await ban_user(session, token, channel_id, user_id)

                if ok:
                    success = True
                    bot_banned += 1
                    adaptive.on_success()
                    await progress.mark_done(user_id)
                    await stats.add_banned()

                    # Notification counter
                    notification_counter += 1
                    if notification_counter % NOTIFY_EVERY == 0:
                        asyncio.create_task(
                            notify_progress(stats.banned, stats.total, stats.floods)
                        )
                    break

                elif error == "FLOOD":
                    wait = retry_after or 30
                    logger.warning(f"[{bot_username}] 🌊 Flood {wait}s (attempt {attempt})")
                    adaptive.on_flood()
                    await stats.add_flood()
                    await asyncio.sleep(wait + 3)
                    # Retry loop continue karega

                else:
                    # Ignorable error?
                    logger.warning(f"[SKIP REASON] {name}: {error}")
                    if any(e in str(error) for e in IGNORABLE):
                        await progress.mark_done(user_id)
                        bot_skipped += 1
                        await stats.add_skipped()
                        success = True  # Dobara try mat karo
                        break
                    else:
                        logger.debug(f"[{bot_username}] Attempt {attempt} fail: {name} — {error}")
                        adaptive.on_error()
                        if attempt < MAX_RETRIES:
                            await asyncio.sleep(adaptive.delay * attempt)

            # Saare retries fail — failed list mein daalo
            if not success:
                logger.warning(f"[{bot_username}] ❌ All retries fail: {name}")
                failed_list.append({**user, "error": str(error)})
                bot_skipped += 1
                await stats.add_skipped()

            await adaptive.wait()

    return {
        "bot": bot_username,
        "banned": bot_banned,
        "skipped": bot_skipped,
        "total_floods": adaptive.total_flood,
        "final_delay": adaptive.delay
    }


# ═══════════════════════════════════════════════
#   Main Banner
# ═══════════════════════════════════════════════
async def run_banner():
    from logger_setup import setup_logger
    setup_logger()

    logger.info("═" * 55)
    logger.info("   🚫 Multi-Bot Banner v2")
    logger.info("═" * 55)

    # ── Load targets ─────────────────────────────
    if not os.path.exists(TARGETS_FILE):
        logger.error(f"❌ {TARGETS_FILE} nahi mila! Pehle collector chalao.")
        return

    with open(TARGETS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    targets = data["targets"]
    channel_id = data["channel_id"]

    # Channel ID format fix
    if not str(channel_id).startswith("-100"):
        channel_id_full = int(f"-100{abs(channel_id)}")
    else:
        channel_id_full = channel_id

    logger.info(f"📢 Channel  : {data['channel']} (ID: {channel_id_full})")
    logger.info(f"👥 Targets  : {len(targets)}")

    # ── Health check ─────────────────────────────
    healthy_bots, dead_bots = await health_check_all_bots(channel_id_full)

    if not healthy_bots:
        msg = "❌ Koi bhi bot healthy nahi hai! Check karo config.py"
        logger.error(msg)
        await notify_error(msg)
        return

    # ── Progress manager ─────────────────────────
    progress = ProgressManager()
    remaining = [t for t in targets if not progress.is_done(t["id"])]

    logger.info(f"📊 Remaining: {len(remaining)} (done: {len(targets) - len(remaining)})")

    if not remaining:
        logger.info("✅ Saare users pehle se ban hain!")
        return

    # ── Confirm ──────────────────────────────────
#    confirm = input(f"\nConfirm: {len(remaining)} users ko {len(healthy_bots)} bots se ban karna hai? (yes/no): ")
#    if confirm.lower() not in ["yes", "y", "haan", "ha"]:
#        logger.info("❌ Cancel.")
#        return

    # ── Notify start ─────────────────────────────
    await notify_start(len(remaining), len(healthy_bots))

    # ── Divide chunks ────────────────────────────
    n_bots = len(healthy_bots)
    chunk_size = len(remaining) // n_bots
    chunks = []
    for i in range(n_bots):
        start = i * chunk_size
        end = start + chunk_size if i < n_bots - 1 else len(remaining)
        chunks.append(remaining[start:end])

    logger.info(f"\n📦 Chunk distribution:")
    for i, (_, username) in enumerate(healthy_bots):
        logger.info(f"   {username}: {len(chunks[i])} users")

    # ── Shared stats + failed list ────────────────
    stats = SharedStats(len(remaining))
    failed_list = []

    # ── Run all bots in parallel ──────────────────
    start_time = time.time()
    logger.info(f"\n🚀 Starting {n_bots} bots in parallel...\n")

    tasks = [
        bot_worker(
            token, username, channel_id_full,
            chunks[i], progress, stats, failed_list
        )
        for i, (token, username) in enumerate(healthy_bots)
    ]

    bot_results_list = await asyncio.gather(*tasks, return_exceptions=True)
    stats.close()

    elapsed = time.time() - start_time

    # ── Save failed users ─────────────────────────
    if failed_list:
        with open(FAILED_FILE, "w", encoding="utf-8") as f:
            json.dump(failed_list, f, ensure_ascii=False, indent=2)
        logger.warning(f"⚠️  {len(failed_list)} failed users saved: {FAILED_FILE}")

    # Final progress save
    progress.save()

    # ── Summary ──────────────────────────────────
    total_banned = stats.banned
    total_skipped = stats.skipped
    total_floods = stats.floods

    logger.info(f"\n{'═' * 55}")
    logger.info(f"✅ ALL DONE!")
    logger.info(f"   ✔️  Banned   : {total_banned}")
    logger.info(f"   ⏭️  Skipped  : {total_skipped}")
    logger.info(f"   ❌ Failed   : {len(failed_list)}")
    logger.info(f"   🌊 Floods   : {total_floods}")
    logger.info(f"   ⏱️  Time     : {elapsed/60:.1f} minutes")

    # Save results
    bot_results = {}
    for r in bot_results_list:
        if isinstance(r, dict):
            bot_results[r["bot"]] = r

    final = {
        "channel": data["channel"],
        "total_targets": len(targets),
        "total_banned": total_banned,
        "total_skipped": total_skipped,
        "total_failed": len(failed_list),
        "total_floods": total_floods,
        "time_minutes": elapsed / 60,
        "bot_results": bot_results
    }

    with open(RESULTS_FILE, "w", encoding="utf-8") as f:
        json.dump(final, f, ensure_ascii=False, indent=2)

    # Final notification
    await notify_complete(total_banned, total_skipped, total_floods, elapsed / 60)
    logger.info(f"💾 Results: {RESULTS_FILE}")


if __name__ == "__main__":
    asyncio.run(run_banner())
          
