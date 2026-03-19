# ═══════════════════════════════════════════════
#   banner.py — Multi-Account Telethon Banner v4.1
#
#   Fix:
#   ✅ access_hash use karta hai — participant invalid error fix
#   ✅ get_input_entity with InputPeerUser fallback
#   ✅ Multiple accounts parallel
#   ✅ Adaptive delay
#   ✅ Smart retry
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
    ChatAdminRequiredError, UserIdInvalidError
)
from config import (
    API_ID, API_HASH, PHONE, SESSION,
    EXTRA_PHONES,
    TARGETS_FILE, RESULTS_FILE, PROGRESS_FILE, FAILED_FILE,
    BASE_DELAY, FLOOD_INCREASE, FLOOD_DECREASE,
    MIN_DELAY, MAX_DELAY, SUCCESS_THRESHOLD, MAX_RETRIES,
    WHITELIST_IDS, NOTIFY_EVERY
)
from notifier import notify_start, notify_progress, notify_complete, notify_error

logger = logging.getLogger(__name__)

BAN_RIGHTS = ChatBannedRights(
    until_date=None,
    view_messages=True,
)


# ═══════════════════════════════════════════════
#   Adaptive Delay
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
    adaptive = AdaptiveDelay(phone)
    acc_banned = 0
    acc_skipped = 0
    notification_counter = 0

    logger.info(f"[{phone}] 🚀 Starting — {len(chunk)} users")

    try:
        client = TelegramClient(session_name, API_ID, API_HASH)
        await client.start(phone=lambda: phone)

        me = await client.get_me()
        logger.info(f"[{phone}] ✅ Login: {me.first_name}")

        # Channel entity
        try:
            channel = await client.get_input_entity(channel_id)
        except Exception as e:
            logger.error(f"[{phone}] ❌ Channel nahi mila: {e}")
            await client.disconnect()
            return {"phone": phone, "banned": 0, "skipped": len(chunk), "total_floods": 0, "error": str(e)}

        for user in chunk:
            user_id = user["id"]

            if progress.is_done(user_id):
                continue

            if user_id in WHITELIST_IDS:
                await progress.mark_done(user_id)
                continue

            name = f"{user['first_name']} {user['last_name']}".strip() or "Unknown"
            success = False
            last_error = ""

            # ── Dynamic Entity Fetch with Fallback ────────
            try:
                user_entity = await client.get_input_entity(user["id"])
            except Exception:
                user_entity = InputPeerUser(
                    user_id=user["id"],
                    access_hash=user.get("access_hash", 0)
                )

            # ── Smart Retry Loop ─────────────────────
            for attempt in range(1, MAX_RETRIES + 1):
                try:
                    await client(EditBannedRequest(channel, user_entity, BAN_RIGHTS))
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
                    logger.warning(f"[{phone}] 🌊 FloodWait {wait}s")
                    adaptive.on_flood()
                    await stats.add_flood()
                    await asyncio.sleep(wait + 3)

                except UserAdminInvalidError:
                    # Channel ka admin hai — skip
                    await progress.mark_done(user_id)
                    acc_skipped += 1
                    await stats.add_skipped()
                    success = True
                    break

                except UserIdInvalidError:
                    await progress.mark_done(user_id)
                    acc_skipped += 1
                    await stats.add_skipped()
                    success = True
                    break

                except ChatAdminRequiredError:
                    logger.error(f"[{phone}] ❌ Channel admin nahi hai!")
                    await client.disconnect()
                    return {
                        "phone": phone,
                        "banned": acc_banned,
                        "skipped": acc_skipped,
                        "total_floods": adaptive.total_flood,
                        "error": "Not admin"
                    }

                except Exception as e:
                    last_error = str(e)
                    logger.warning(f"[{phone}] Attempt {attempt}: {name} — {last_error}")
                    adaptive.on_error()
                    if attempt < MAX_RETRIES:
                        await asyncio.sleep(adaptive.delay * attempt)

            if not success:
                logger.warning(f"[{phone}] ❌ Failed: {name} — {last_error}")
                failed_list.append({**user, "error": last_error})
                acc_skipped += 1
                await stats.add_skipped()

            await adaptive.wait()

        await client.disconnect()

    except Exception as e:
        logger.error(f"[{phone}] ❌ Error: {e}")
        return {"phone": phone, "banned": acc_banned, "skipped": acc_skipped, "total_floods": adaptive.total_flood, "error": str(e)}

    logger.info(f"[{phone}] 🏁 Done! Banned={acc_banned} Skipped={acc_skipped} Floods={adaptive.total_flood}")
    return {"phone": phone, "banned": acc_banned, "skipped": acc_skipped, "total_floods": adaptive.total_flood, "final_delay": adaptive.delay}


# ═══════════════════════════════════════════════
#   Main Banner
# ═══════════════════════════════════════════════
async def run_banner():
    from logger_setup import setup_logger
    setup_logger()

    logger.info("═" * 55)
    logger.info("   🚫 Multi-Account Banner v4.1 — Entity Fix")
    logger.info("═" * 55)

    if not os.path.exists(TARGETS_FILE):
        logger.error(f"❌ {TARGETS_FILE} nahi mila!")
        return

    with open(TARGETS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    targets = data["targets"]
    channel_id = data["channel"]

    # access_hash stats
    with_hash = sum(1 for t in targets if t.get("access_hash", 0) != 0)
    logger.info(f"🔑 access_hash available: {with_hash}/{len(targets)} users")

    if with_hash == 0:
        logger.warning("⚠️  Kisi ke paas access_hash nahi! Pehle collector dobara chalao")

    all_phones = [PHONE] + EXTRA_PHONES
    session_names = [SESSION] + [f"session_{i+1}" for i in range(len(EXTRA_PHONES))]

    logger.info(f"📢 Channel  : {channel_id}")
    logger.info(f"👥 Targets  : {len(targets)}")
    logger.info(f"📱 Accounts : {len(all_phones)}")

    progress = ProgressManager()
    remaining = [t for t in targets if not progress.is_done(t["id"])]

    logger.info(f"📊 Remaining: {len(remaining)}")

    if not remaining:
        logger.info("✅ Saare users pehle se ban hain!")
        return

    await notify_start(len(remaining), len(all_phones))

    # Chunks divide
    n = len(all_phones)
    chunk_size = len(remaining) // n
    chunks = []
    for i in range(n):
        start = i * chunk_size
        end = start + chunk_size if i < n - 1 else len(remaining)
        chunks.append(remaining[start:end])

    logger.info(f"\n📦 Distribution:")
    for i, phone in enumerate(all_phones):
        logger.info(f"   {phone}: {len(chunks[i])} users")

    stats = SharedStats(len(remaining))
    failed_list = []

    start_time = time.time()
    logger.info(f"\n🚀 {n} accounts parallel start...\n")

    tasks = [
        account_worker(
            phone=all_phones[i],
            session_name=session_names[i],
            channel_id=channel_id,
            chunk=chunks[i],
            progress=progress,
            stats=stats,
            failed_list=failed_list
        )
        for i in range(n)
    ]

    account_results = await asyncio.gather(*tasks, return_exceptions=True)
    stats.close()

    elapsed = time.time() - start_time

    if failed_list:
        with open(FAILED_FILE, "w", encoding="utf-8") as f:
            json.dump(failed_list, f, ensure_ascii=False, indent=2)
        logger.warning(f"⚠️  {len(failed_list)} failed saved")

    progress.save()

    logger.info(f"\n{'═' * 55}")
    logger.info(f"✅ ALL DONE!")
    logger.info(f"   ✔️  Banned  : {stats.banned}")
    logger.info(f"   ⏭️  Skipped : {stats.skipped}")
    logger.info(f"   ❌ Failed  : {len(failed_list)}")
    logger.info(f"   🌊 Floods  : {stats.floods}")
    logger.info(f"   ⏱️  Time    : {elapsed/60:.1f} min")

    acc_results = {}
    for r in account_results:
        if isinstance(r, dict):
            acc_results[r["phone"]] = r
            logger.info(f"   📱 {r['phone']}: ✅{r.get('banned',0)} ⏭️{r.get('skipped',0)}")

    with open(RESULTS_FILE, "w", encoding="utf-8") as f:
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
    logger.info(f"🔒 Ye log ab tumhara channel nahi dekh payenge!")


if __name__ == "__main__":
    asyncio.run(run_banner())
    
