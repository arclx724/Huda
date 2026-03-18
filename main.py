# ═══════════════════════════════════════════════
#   main.py — Master Coordinator v2
#
#   Menu:
#   1. Full Run (Collect + Ban)
#   2. Sirf Collect
#   3. Sirf Ban
#   4. Retry Failed Users
#   5. Start Live Watcher
#   6. Results dekho
#   7. Progress reset
#   8. Exit
# ═══════════════════════════════════════════════

import asyncio
import os
import sys
import json
from logger_setup import setup_logger
from config import (
    TARGETS_FILE, RESULTS_FILE, PROGRESS_FILE,
    FAILED_FILE, SCHEDULE_ENABLED, SCHEDULE_INTERVAL_HR
)


def print_banner():
    print("""
╔══════════════════════════════════════════════╗
║    🔐 Telegram Channel Privacy System v2     ║
║                                              ║
║  Auto collect + ban + watch — fully private! ║
╚══════════════════════════════════════════════╝
""")


def show_menu():
    # Quick stats
    targets_count = "—"
    done_count = "—"
    failed_count = "—"

    if os.path.exists(TARGETS_FILE):
        try:
            with open(TARGETS_FILE) as f:
                d = json.load(f)
                targets_count = d.get("stats", {}).get("total_targets", len(d.get("targets", [])))
        except Exception:
            pass

    if os.path.exists(PROGRESS_FILE):
        try:
            with open(PROGRESS_FILE) as f:
                done_count = len(json.load(f).get("done_ids", []))
        except Exception:
            pass

    if os.path.exists(FAILED_FILE):
        try:
            with open(FAILED_FILE) as f:
                failed_count = len(json.load(f))
        except Exception:
            pass

    print(f"""
  📊 Status: Targets={targets_count} | Done={done_count} | Failed={failed_count}
  {"─" * 48}
  [1]  Full Run          (Collect → Ban)
  [2]  Sirf Collect      (targets.json banao)
  [3]  Sirf Ban          (saved targets se)
  [4]  Retry Failed      (failed.json se retry)
  [5]  Live Watcher      (naye admins auto-ban)
  [6]  Results dekho
  [7]  Progress reset    (fresh start)
  [8]  Exit
""")
    return input("  Choice (1-8): ").strip()


# ── Runners ─────────────────────────────────────

async def run_full():
    from collector import main as run_collector
    from banner import run_banner

    print("\n🔄 Step 1: Collecting...")
    await run_collector()

    if not os.path.exists(TARGETS_FILE):
        print("❌ Collection fail. Ruk gaye.")
        return

    print("\n🔄 Step 2: Banning...")
    await run_banner()


async def run_collect_only():
    from collector import main as run_collector
    await run_collector()


async def run_ban_only():
    from banner import run_banner
    await run_banner()


async def retry_failed():
    """failed.json se users retry karta hai"""
    if not os.path.exists(FAILED_FILE):
        print(f"❌ {FAILED_FILE} nahi mila. Pehle ban karo.")
        return

    with open(FAILED_FILE, "r") as f:
        failed = json.load(f)

    if not failed:
        print("✅ Koi failed user nahi hai!")
        return

    print(f"🔄 {len(failed)} failed users retry honge...")

    # Failed users ko targets file mein temporarily set karo
    if os.path.exists(TARGETS_FILE):
        with open(TARGETS_FILE, "r") as f:
            data = json.load(f)
    else:
        print("❌ targets.json nahi mila!")
        return

    # Backup original targets
    original_targets = data["targets"]

    # Failed users ko targets mein set karo
    data["targets"] = failed
    data["stats"]["total_targets"] = len(failed)

    with open(TARGETS_FILE, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    # Failed file clear karo
    os.remove(FAILED_FILE)

    # Progress mein se failed IDs remove karo taaki retry ho
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE, "r") as f:
            progress = json.load(f)

        failed_ids = {u["id"] for u in failed}
        progress["done_ids"] = [i for i in progress["done_ids"] if i not in failed_ids]

        with open(PROGRESS_FILE, "w") as f:
            json.dump(progress, f)

    # Ban karo
    from banner import run_banner
    await run_banner()

    # Original targets restore karo
    data["targets"] = original_targets
    with open(TARGETS_FILE, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


async def start_watcher():
    from watcher import start_watcher as watcher_main
    print("\n👀 Watcher start ho raha hai...")
    print("Ctrl+C se band karo.\n")
    await watcher_main()


def show_results():
    if not os.path.exists(RESULTS_FILE):
        print(f"❌ {RESULTS_FILE} nahi mila.")
        return

    with open(RESULTS_FILE, "r") as f:
        data = json.load(f)

    print(f"""
╔══════════════════════════════╗
║         📊 Results           ║
╠══════════════════════════════╣
  Channel  : {data.get('channel')}
  Total    : {data.get('total_targets')}
  ✅ Banned : {data.get('total_banned')}
  ⏭️  Skipped: {data.get('total_skipped')}
  ❌ Failed : {data.get('total_failed', 0)}
  🌊 Floods : {data.get('total_floods')}
  ⏱️  Time   : {data.get('time_minutes', 0):.1f} min

  Per Bot:""")

    for bot, r in data.get("bot_results", {}).items():
        print(f"    [{bot}] Banned={r.get('banned',0)} Skipped={r.get('skipped',0)} Floods={r.get('total_floods',0)}")


def reset_progress():
    confirm = input("⚠️  Sure ho? Progress reset hogi. (yes/no): ")
    if confirm.lower() in ["yes", "y", "haan", "ha"]:
        for f in [PROGRESS_FILE, FAILED_FILE]:
            if os.path.exists(f):
                os.remove(f)
                print(f"✅ {f} delete kiya")
        print("✅ Reset complete! Fresh start hoga.")
    else:
        print("❌ Cancel.")


# ── Auto Scheduler ───────────────────────────────
async def run_scheduler():
    """Automatic periodic run"""
    import time
    interval_sec = SCHEDULE_INTERVAL_HR * 3600
    print(f"⏰ Scheduler active — har {SCHEDULE_INTERVAL_HR} ghante mein run karega")

    while True:
        print(f"\n⏰ Scheduled run starting...")
        await run_full()
        print(f"✅ Done. Next run {SCHEDULE_INTERVAL_HR} ghante mein.")
        await asyncio.sleep(interval_sec)


# ── Main ─────────────────────────────────────────
async def main():
    setup_logger()
    print_banner()

    # Auto scheduler mode
    if SCHEDULE_ENABLED:
        await run_scheduler()
        return

    while True:
        choice = show_menu()

        if choice == "1":
            await run_full()
        elif choice == "2":
            await run_collect_only()
        elif choice == "3":
            await run_ban_only()
        elif choice == "4":
            await retry_failed()
        elif choice == "5":
            await start_watcher()
        elif choice == "6":
            show_results()
        elif choice == "7":
            reset_progress()
        elif choice == "8":
            print("👋 Bye!")
            sys.exit(0)
        else:
            print("❌ 1-8 mein se choose karo.")

        print("\n" + "─" * 50)
        input("Enter dabao menu pe wapas jaane ke liye...")


if __name__ == "__main__":
    asyncio.run(main())

