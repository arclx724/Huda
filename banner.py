# ═══════════════════════════════════════════════
#   banner.py — Shared Queue Multi-Account Banner
#
#   Key Optimization:
#   ✅ Shared queue — koi account idle nahi baithega
#   ✅ FloodWait pe account pause, doosra kaam karta hai
#   ✅ Fastest possible speed without getting banned
#   ✅ access_hash properly use karta hai
#   ✅ Resume support
#   ✅ Progress bar
# ═══════════════════════════════════════════════

import asyncio
import json
import os
import time
import logging
from tqdm import tqdm
from telethon import TelegramClient
from telethon.tl.functions.channels import EditBannedRequest
from telethon.tl.types import ChatBannedRights, InputPeerUser
from telethon.errors import (
    FloodWaitError, UserAdminInvalidError,
    ChatAdminRequiredError, UserIdInvalidError,
    PeerIdInvalidError
)
from config import (
    API_ID, API_HASH, PHONE, SESSION, EXTRA_PHONES,
    TARGETS_FILE, RESULTS_FILE, PROGRESS_FILE, FAILED_FILE,
    BASE_DELAY, FLOOD_INCREASE, FLOOD_DECREASE,
    MIN_DELAY, MAX_DELAY, SUCCESS_THRESHOLD, MAX_RETRIES,
    WHITELIST_IDS, NOTIFY_EVERY
)
from notifier import notify_start, notify_progress, notify_complete, notify_error

logger = logging.getLogger(__name__)

BAN_RIGHTS = ChatBannedRights(until_date=None, view_messages=True)


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
        self.is_waiting = False      # FloodWait mein hai?
        self.wait_until = 0          # Kab tak wait karna hai

    def on_success(self):
        self.total_success += 1
        self.success_streak += 1
        if self.success_streak >= SUCCESS_THRESHOLD:
            old = self.delay
            self.delay = max(MIN_DELAY, self.delay - FLOOD_DECREASE)
            self.success_streak = 0
            if old != self.delay:
                logger.info(f"[{self.name}] ⚡ Speed up → {self.delay:.1f}s")

    def on_flood(self, seconds):
        self.total_flood += 1
        self.success_streak = 0
        self.delay = min(MAX_DELAY, self.delay + FLOOD_INCREASE)
        self.is_waiting = True
        self.wait_until = time.time() + seconds + 3
        logger.warning(f"[{self.name}] 🌊 FloodWait {seconds}s → delay {self.delay:.1f}s")

    def flood_done(self):
        self.is_waiting = False

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
                with open(PROGRESS_FILE) as f:
                    self.done_ids = set(json.load(f).get("done_ids", []))
                logger.info(f"📂 Resume: {len(self.done_ids)} pehle se done")
            except Exception:
                self.done_ids = set()

    async def mark_done(self, uid):
        async with self._lock:
            self.done_ids.add(uid)
            if len(self.done_ids) % 50 == 0:
                self._save()

    def _save(self):
        with open(PROGRESS_FILE, "w") as f:
            json.dump({"done_ids": list(self.done_ids)}, f)

    def save(self):
        self._save()

    def is_done(self, uid):
        return uid in self.done_ids


# ═══════════════════════════════════════════════
#   Shared Stats
# ═══════════════════════════════════════════════
class SharedStats:
    def __init__(self, total):
        self.total = total
        self.banned = 0
        self.skipped = 0
        self.floods = 0
        self._lock = asyncio.Lock()
        self.pbar = tqdm(
            total=total, desc="Banning", unit="user",
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
#   Account Worker — Shared Queue se kaam karta hai
# ═══════════════════════════════════════════════
async def account_worker(phone, session_name, channel_id, queue, progress, stats, failed_list, results):
    """
    Shared queue se users lete hain aur ban karte hain.
    FloodWait aaye toh queue mein wapas daalo aur wait karo —
    doosre accounts meanwhile kaam karte rahenge!
    """
    adaptive = AdaptiveDelay(phone)
    acc_banned = 0
    acc_skipped = 0
    acc_no_hash = 0
    notification_counter = 0

    logger.info(f"[{phone}] 🚀 Start")

    try:
        client = TelegramClient(session_name, API_ID, API_HASH)
        await client.start(phone=lambda: phone)
        me = await client.get_me()
        logger.info(f"[{phone}] ✅ Login: {me.first_name}")

        # Channel fetch
        try:
            channel = await client.get_input_entity(channel_id)
        except Exception as e:
            logger.error(f"[{phone}] ❌ Channel error: {e}")
            await client.disconnect()
            results[phone] = {"banned": 0, "skipped": 0, "floods": 0, "error": str(e)}
            return

        while True:
            # Queue se next user lo
            try:
                user = queue.get_nowait()
            except asyncio.QueueEmpty:
                break  # Queue empty — kaam khatam!

            uid = user["id"]

            # Already done?
            if progress.is_done(uid):
                queue.task_done()
                continue

            # Whitelist?
            if uid in WHITELIST_IDS:
                await progress.mark_done(uid)
                queue.task_done()
                continue

            name = f"{user['first_name']} {user['last_name']}".strip() or "Unknown"
            access_hash = user.get("access_hash", 0)

            # No hash — skip
            if access_hash == 0:
                logger.debug(f"[{phone}] No hash: {name}")
                await progress.mark_done(uid)
                acc_no_hash += 1
                acc_skipped += 1
                await stats.add_skipped()
                queue.task_done()
                continue

            user_entity = InputPeerUser(user_id=uid, access_hash=access_hash)
            success = False
            last_error = ""

            # ── Retry Loop ───────────────────────────
            for attempt in range(1, MAX_RETRIES + 1):
                try:
                    await client(EditBannedRequest(channel, user_entity, BAN_RIGHTS))
                    success = True
                    acc_banned += 1
                    adaptive.on_success()
                    await progress.mark_done(uid)
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
                    adaptive.on_flood(e.seconds)
                    await stats.add_flood()

                    # ── SMART: Queue mein wapas daalo ──
                    # Doosre accounts ye user handle kar lenge!
                    await queue.put(user)
                    queue.task_done()

                    logger.warning(f"[{phone}] 😴 FloodWait {e.seconds}s — user wapas queue mein, main so raha hoon")
                    await asyncio.sleep(e.seconds + 3)
                    adaptive.flood_done()

                    # Queue se fresh kaam lo
                    success = True  # Loop se bahar niklo
                    break

                except (UserAdminInvalidError, UserIdInvalidError, PeerIdInvalidError):
                    await progress.mark_done(uid)
                    acc_skipped += 1
                    await stats.add_skipped()
                    success = True
                    break

                except ChatAdminRequiredError:
                    logger.error(f"[{phone}] ❌ Channel admin nahi hai!")
                    await client.disconnect()
                    results[phone] = {
                        "banned": acc_banned, "skipped": acc_skipped,
                        "floods": adaptive.total_flood, "error": "Not admin"
                    }
                    return

                except Exception as e:
                    last_error = str(e)
                    adaptive.on_error()
                    if attempt < MAX_RETRIES:
                        await asyncio.sleep(adaptive.delay * attempt)

            if not success:
                logger.warning(f"[{phone}] ❌ Failed: {name} — {last_error}")
                failed_list.append({**user, "error": last_error})
                acc_skipped += 1
                await stats.add_skipped()

            queue.task_done()
            await adaptive.wait()

        await client.disconnect()

    except Exception as e:
        logger.error(f"[{phone}] ❌ Fatal: {e}")

    logger.info(f"[{phone}] 🏁 Done! ✅{acc_banned} ⏭️{acc_skipped} 🌊{adaptive.total_flood}")
    results[phone] = {
        "phone": phone,
        "banned": acc_banned,
        "skipped": acc_skipped,
        "no_hash": acc_no_hash,
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
    logger.info("   🚫 Shared Queue Banner — Maximum Speed")
    logger.info("═" * 55)

    if not os.path.exists(TARGETS_FILE):
        logger.error(f"❌ {TARGETS_FILE} nahi mila! Pehle collect karo (Option 2)")
        return

    with open(TARGETS_FILE) as f:
        data = json.load(f)

    targets = data["targets"]
    channel_id = data["channel"]

    with_hash = sum(1 for t in targets if t.get("access_hash", 0) != 0)
    without_hash = len(targets) - with_hash

    logger.info(f"📢 Channel   : {channel_id}")
    logger.info(f"👥 Total     : {len(targets)}")
    logger.info(f"🔑 With hash : {with_hash} (ban honge)")
    logger.info(f"⚠️  No hash   : {without_hash} (skip)")

    all_phones = [PHONE]
    session_names = [SESSION]
    logger.info(f"📱 Accounts  : {len(all_phones)}")

    # Progress
    progress = ProgressManager()
    remaining = [t for t in targets if not progress.is_done(t["id"])]
    logger.info(f"📊 Remaining : {len(remaining)}")

    if not remaining:
        logger.info("✅ Saare users pehle se done!")
        return

    await notify_start(len(remaining), len(all_phones))

    # ── SHARED QUEUE BANAO ────────────────────────
    queue = asyncio.Queue()
    for user in remaining:
        await queue.put(user)

    logger.info(f"\n📦 Shared queue: {queue.qsize()} users")
    logger.info(f"🚀 {len(all_phones)} accounts queue se parallel kaam karenge")
    logger.info(f"💡 FloodWait pe user wapas queue mein — doosra account uthayega!\n")

    stats = SharedStats(len(remaining))
    failed_list = []
    acc_results = {}
    start_time = time.time()

    # Saare accounts parallel chalao — shared queue pe!
    tasks = [
        account_worker(
            phone=all_phones[i],
            session_name=session_names[i],
            channel_id=channel_id,
            queue=queue,
            progress=progress,
            stats=stats,
            failed_list=failed_list,
            results=acc_results
        )
        for i in range(len(all_phones))
        
    ]

    await asyncio.gather(*tasks)
    stats.close()

    elapsed = time.time() - start_time

    # Save failed
    if failed_list:
        with open(FAILED_FILE, "w") as f:
            json.dump(failed_list, f, ensure_ascii=False, indent=2)
        logger.warning(f"⚠️  {len(failed_list)} failed: {FAILED_FILE}")

    progress.save()

    # Summary
    logger.info(f"\n{'═' * 55}")
    logger.info(f"✅ ALL DONE!")
    logger.info(f"   ✔️  Banned  : {stats.banned}")
    logger.info(f"   ⏭️  Skipped : {stats.skipped}")
    logger.info(f"   ❌ Failed  : {len(failed_list)}")
    logger.info(f"   🌊 Floods  : {stats.floods}")
    logger.info(f"   ⏱️  Time    : {elapsed/60:.1f} min")
    logger.info(f"\n   Per Account:")
    for phone, r in acc_results.items():
        logger.info(f"   📱 {phone}: ✅{r.get('banned',0)} ⏭️{r.get('skipped',0)} 🌊{r.get('total_floods',0)}")

    with open(RESULTS_FILE, "w") as f:
        json.dump({
            "channel": channel_id,
            "total_targets": len(targets),
            "total_banned": stats.banned,
            "total_skipped": stats.skipped,
            "total_failed": len(failed_list),
            "total_floods": stats.floods,
            "time_minutes": elapsed / 60,
            "account_results": acc_results
        }, f, ensure_ascii=False, indent=2)

    await notify_complete(stats.banned, stats.skipped, stats.floods, elapsed / 60)
    logger.info(f"🔒 Channel secure! Results: {RESULTS_FILE}")


if __name__ == "__main__":
    asyncio.run(run_banner())
    
