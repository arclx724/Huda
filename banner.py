# ═══════════════════════════════════════════════
#   banner.py — Multi-Account Telethon Banner
#
#   Features:
#   ✅ Multiple accounts parallel banning
#   ✅ Same API_ID/HASH — sirf alag phone numbers
#   ✅ Non-members bhi ban honge (Telethon magic)
#   ✅ Adaptive delay per account
#   ✅ Smart retry (3 attempts)
#   ✅ Resume support
#   ✅ Progress bar
#   ✅ Failed users tracking
#   ✅ Telegram notifications
# ═══════════════════════════════════════════════

import asyncio
import json
import os
import time
import logging
from tqdm import tqdm
from telethon import TelegramClient
from telethon.tl.functions.channels import EditBannedRequest
from telethon.tl.types import ChatBannedRights
from telethon.errors import (
    FloodWaitError, UserAdminInvalidError,
    ChatAdminRequiredError, UserIdInvalidError
)
from config import (
    API_ID, API_HASH,
    TARGETS_FILE, RESULTS_FILE, PROGRESS_FILE, FAILED_FILE,
    BASE_DELAY, FLOOD_INCREASE, FLOOD_DECREASE,
    MIN_DELAY, MAX_DELAY, SUCCESS_THRESHOLD, MAX_RETRIES,
    WHITELIST_IDS, NOTIFY_EVERY,
    EXTRA_PHONES
)
from notifier import notify_start, notify_progress, notify_complete, notify_error

logger = logging.getLogger(__name__)

# Channel ban rights — permanent, view bhi nahi kar sakta
BAN_RIGHTS = ChatBannedRights(
    until_date=None,
    view_messages=True,
)


# ═══════════════════════════════════════════════
#   Adaptive Delay — Per Account
# ═══════════════════════════════════════════════
class AdaptiveDelay:
    def __init__(self, name):
        self.name = name
        self.delay = BASE_DELAY
        self.total_success = 0
        self.total_flood = 0
        self.success_streak = 0

    def on_success(self):
        self.total_success += 1
        self.success_streak += 1
        if self.success_streak >= SUCCESS_THRESHOLD:
            self.delay = max(MIN_DELAY, self.delay - FLOOD_DECREASE)
            self.success_streak = 0

    def on_flood(self):
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
#   Progress Manager
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
                logger.info(f"📂 Resume: {len(self.done_ids)} pehle se done")
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
#   Shared Stats — Thread safe
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
#   Single Account Worker
# ═══════════════════════════════════════════════
async def account_worker(phone, session_name, channel_id, chunk, progress, stats, failed_list):
    """
    Ek account ka worker — apna chunk ban karta hai.

    Args:
        phone: Phone number
        session_name: Unique session file name
        channel_id: Channel username ya ID
        chunk: List of users to ban
        progress: ProgressManager
        stats: SharedStats
        failed_list: Shared failed list
    """
    adaptive = AdaptiveDelay(phone)
    acc_banned = 0
    acc_skipped = 0
    notification_counter = 0

    logger.info(f"[{phone}] 🚀 Starting — {len(chunk)} users")

    try:
        async with TelegramClient(session_name, API_ID, API_HASH) as client:
            await client.start(phone=phone)
            me = await client.get_me()
            logger.info(f"[{phone}] ✅ Login: {me.first_name}")

            # Channel entity fetch
            try:
                channel = await client.get_entity(channel_id)
            except Exception as e:
                logger.error(f"[{phone}] ❌ Channel nahi mila: {e}")
                return {"phone": phone, "banned": 0, "skipped": len(chunk), "error": str(e)}

            for user in chunk:
                user_id = user["id"]

                # Already done? Skip
                if progress.is_done(user_id):
                    continue

                # Whitelist check
                if user_id in WHITELIST_IDS:
                    await progress.mark_done(user_id)
                    continue

                name = f"{user['first_name']} {user['last_name']}".strip() or "Unknown"
                success = False

                # ── Smart Retry Loop ─────────────────
                for attempt in range(1, MAX_RETRIES + 1):
                    try:
                        await client(EditBannedRequest(channel, user_id, BAN_RIGHTS))
                        success = True
                        acc_banned += 1
                        adaptive.on_success()
                        await progress.mark_done(user_id)
                        await stats.add_banned()

                        tag = "🤖" if user.get("is_bot") else "👑"
                        logger.info(f"[{phone}] {tag} ✅ {name} | {adaptive.status()}")

                        notification_counter += 1
                        if notification_counter % NOTIFY_EVERY == 0:
                            asyncio.create_task(
                                notify_progress(stats.banned, stats.total, stats.floods)
                            )
                        break

                    except FloodWaitError as e:
                        wait = e.seconds
                        logger.warning(f"[{phone}] 🌊 FloodWait {wait}s (attempt {attempt})")
                        adaptive.on_flood()
                        await stats.add_flood()
                        await asyncio.sleep(wait + 3)
                        # Retry loop continue karega

                    except UserAdminInvalidError:
                        # User is admin — skip karo
                        logger.debug(f"[{phone}] Skip (admin): {name}")
                        await progress.mark_done(user_id)
                        acc_skipped += 1
                        await stats.add_skipped()
                        success = True
                        break

                    except UserIdInvalidError:
                        # Invalid user — skip
                        logger.warning(f"[{phone}] Skip (invalid ID): {name}")
                        await progress.mark_done(user_id)
                        acc_skipped += 1
                        await stats.add_skipped()
                        success = True
                        break

                    except ChatAdminRequiredError:
                        logger.error(f"[{phone}] ❌ Channel admin nahi hai! Ban karna possible nahi.")
                        return {
                            "phone": phone,
                            "banned": acc_banned,
                            "skipped": acc_skipped,
                            "total_floods": adaptive.total_flood,
                            "error": "Not admin in channel"
                        }

                    except Exception as e:
                        error_str = str(e)
                        logger.debug(f"[{phone}] Attempt {attempt} fail: {name} — {error_str}")
                        adaptive.on_error()
                        if attempt < MAX_RETRIES:
                            await asyncio.sleep(adaptive.delay * attempt)

                # Saare retries fail
                if not success:
                    logger.warning(f"[{phone}] ❌ All retries fail: {name}")
                    failed_list.append({**user, "error": "All retries failed"})
                    acc_skipped += 1
                    await stats.add_skipped()

                await adaptive.wait()

    except Exception as e:
        logger.error(f"[{phone}] ❌ Account error: {e}")
        return {
            "phone": phone,
            "banned": acc_banned,
            "skipped": acc_skipped,
            "total_floods": adaptive.total_flood,
            "error": str(e)
        }

    logger.info(f"[{phone}] 🏁 Done! Banned={acc_banned} Skipped={acc_skipped} Floods={adaptive.total_flood}")

    return {
        "phone": phone,
        "banned": acc_banned,
        "skipped": acc_skipped,
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
    logger.info("   🚫 Multi-Account Telethon Banner")
    logger.info("═" * 55)

    # ── Load targets ─────────────────────────────
    if not os.path.exists(TARGETS_FILE):
        logger.error(f"❌ {TARGETS_FILE} nahi mila! Pehle collector chalao.")
        return

    with open(TARGETS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    targets = data["targets"]
    channel_id = data["channel"]  # Username use karenge — reliable hai

    # ── All accounts setup ────────────────────────
    # Main account + extra accounts
    from config import PHONE
    all_phones = [PHONE] + EXTRA_PHONES

    logger.info(f"📢 Channel  : {channel_id}")
    logger.info(f"👥 Targets  : {len(targets)}")
    logger.info(f"📱 Accounts : {len(all_phones)}")

    # ── Progress manager ─────────────────────────
    progress = ProgressManager()
    remaining = [t for t in targets if not progress.is_done(t["id"])]

    logger.info(f"📊 Remaining: {len(remaining)} (done: {len(targets) - len(remaining)})")

    if not remaining:
        logger.info("✅ Saare users pehle se ban hain!")
        return

    # ── Notify ───────────────────────────────────
    await notify_start(len(remaining), len(all_phones))
    logger.info(f"\n🚀 Auto ban shuru — {len(remaining)} users, {len(all_phones)} accounts\n")

    # ── Divide chunks ────────────────────────────
    n_accounts = len(all_phones)
    chunk_size = len(remaining) // n_accounts
    chunks = []
    for i in range(n_accounts):
        start = i * chunk_size
        end = start + chunk_size if i < n_accounts - 1 else len(remaining)
        chunks.append(remaining[start:end])

    logger.info(f"📦 Chunk distribution:")
    for i, phone in enumerate(all_phones):
        logger.info(f"   {phone}: {len(chunks[i])} users")

    # ── Shared objects ────────────────────────────
    stats = SharedStats(len(remaining))
    failed_list = []

    # ── Run all accounts parallel ─────────────────
    start_time = time.time()
    logger.info(f"\n🚀 {n_accounts} accounts parallel mein start...\n")

    tasks = [
        account_worker(
            phone=all_phones[i],
            session_name=f"session_{i}",
            channel_id=channel_id,
            chunk=chunks[i],
            progress=progress,
            stats=stats,
            failed_list=failed_list
        )
        for i in range(n_accounts)
    ]

    account_results = await asyncio.gather(*tasks, return_exceptions=True)
    stats.close()

    elapsed = time.time() - start_time

    # ── Save failed ───────────────────────────────
    if failed_list:
        with open(FAILED_FILE, "w", encoding="utf-8") as f:
            json.dump(failed_list, f, ensure_ascii=False, indent=2)
        logger.warning(f"⚠️  {len(failed_list)} failed: {FAILED_FILE}")

    progress.save()

    # ── Summary ───────────────────────────────────
    logger.info(f"\n{'═' * 55}")
    logger.info(f"✅ ALL DONE!")
    logger.info(f"   ✔️  Banned   : {stats.banned}")
    logger.info(f"   ⏭️  Skipped  : {stats.skipped}")
    logger.info(f"   ❌ Failed   : {len(failed_list)}")
    logger.info(f"   🌊 Floods   : {stats.floods}")
    logger.info(f"   ⏱️  Time     : {elapsed/60:.1f} minutes")

    acc_results = {}
    for r in account_results:
        if isinstance(r, dict):
            acc_results[r["phone"]] = r
            logger.info(f"   📱 {r['phone']}: Banned={r.get('banned',0)} Skipped={r.get('skipped',0)}")

    # Save results
    final = {
        "channel": channel_id,
        "total_targets": len(targets),
        "total_banned": stats.banned,
        "total_skipped": stats.skipped,
        "total_failed": len(failed_list),
        "total_floods": stats.floods,
        "time_minutes": elapsed / 60,
        "account_results": acc_results
    }

    with open(RESULTS_FILE, "w", encoding="utf-8") as f:
        json.dump(final, f, ensure_ascii=False, indent=2)

    await notify_complete(stats.banned, stats.skipped, stats.floods, elapsed / 60)
    logger.info(f"💾 Results: {RESULTS_FILE}")
    logger.info(f"🔒 Ye log ab tumhara channel nahi dekh payenge!")


if __name__ == "__main__":
    asyncio.run(run_banner())
    
