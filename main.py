# ═══════════════════════════════════════════════
#   main.py — Master Controller
# ═══════════════════════════════════════════════

import asyncio
import os
import sys
import json
from logger_setup import setup_logger
from config import (
    TARGETS_FILE, RESULTS_FILE,
    PROGRESS_FILE, FAILED_FILE,
    SCHEDULE_ENABLED, SCHEDULE_INTERVAL_HR
)


def print_banner():
    print("""
╔══════════════════════════════════════════════╗
║    🔐 Telegram Channel Privacy System        ║
║         Final Version — Fully Fixed          ║
╚══════════════════════════════════════════════╝
""")


def show_menu():
    # Quick stats
    t = done = failed = "—"

    if os.path.exists(TARGETS_FILE):
        try:
            with open(TARGETS_FILE) as f:
                d = json.load(f)
                t = d.get("stats", {}).get("total_targets", len(d.get("targets", [])))
                wh = d.get("stats", {}).get("with_hash", "?")
                t = f"{t} (🔑{wh})"
        except Exception:
            pass

    if os.path.exists(PROGRESS_FILE):
        try:
            with open(PROGRESS_FILE) as f:
                done = len(json.load(f).get("done_ids", []))
        except Exception:
            pass

    if os.path.exists(FAILED_FILE):
        try:
            with open(FAILED_FILE) as f:
                failed = len(json.load(f))
        except Exception:
            pass

    print(f"""
  📊 Targets={t} | Done={done} | Failed={failed}
  {"─" * 48}
  [1]  Full Run       (Collect → Ban)
  [2]  Sirf Collect   (targets.json banao)
  [3]  Sirf Ban       (saved targets se)
  [4]  Retry Failed   (failed.json retry)
  [5]  Live Watcher   (auto ban new admins)
  [6]  Results dekho
  [7]  Progress reset (fresh start)
  [8]  Exit
""")
    return input("  Choice (1-8): ").strip()


async def run_full():
    from collector import main as collect
    from banner import run_banner
    print("\n🔄 Step 1: Collecting...")
    await collect()
    if os.path.exists(TARGETS_FILE):
        print("\n🔄 Step 2: Banning...")
        await run_banner()


async def run_collect():
    from collector import main as collect
    await collect()


async def run_ban():
    from banner import run_banner
    await run_banner()


async def retry_failed():
    if not os.path.exists(FAILED_FILE):
        print("❌ failed.json nahi mila!")
        return

    with open(FAILED_FILE) as f:
        failed = json.load(f)

    if not failed:
        print("✅ Koi failed nahi!")
        return

    print(f"🔄 {len(failed)} failed users retry honge...")

    with open(TARGETS_FILE) as f:
        data = json.load(f)

    # Failed users ko targets mein set karo
    original = data["targets"]
    data["targets"] = failed
    data["stats"]["total_targets"] = len(failed)

    with open(TARGETS_FILE, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    os.remove(FAILED_FILE)

    # Progress se failed IDs remove karo
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE) as f:
            prog = json.load(f)
        failed_ids = {u["id"] for u in failed}
        prog["done_ids"] = [i for i in prog["done_ids"] if i not in failed_ids]
        with open(PROGRESS_FILE, "w") as f:
            json.dump(prog, f)

    from banner import run_banner
    await run_banner()

    # Restore originals
    data["targets"] = original
    with open(TARGETS_FILE, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


async def start_watcher():
    from watcher import start_watcher as w
    print("\n👀 Watcher start (Ctrl+C se band karo)...\n")
    await w()


def show_results():
    if not os.path.exists(RESULTS_FILE):
        print("❌ results.json nahi mila.")
        return

    with open(RESULTS_FILE) as f:
        d = json.load(f)

    print(f"""
╔══════════════════════════╗
║       📊 Results         ║
╠══════════════════════════╣
  Channel : {d.get('channel')}
  Total   : {d.get('total_targets')}
  ✅ Banned: {d.get('total_banned')}
  ⏭️  Skip  : {d.get('total_skipped')}
  ❌ Failed: {d.get('total_failed', 0)}
  🌊 Floods: {d.get('total_floods')}
  ⏱️  Time  : {d.get('time_minutes', 0):.1f} min

  Per Account:""")
    for acc, r in d.get("account_results", {}).items():
        print(f"    {acc}: ✅{r.get('banned',0)} ⏭️{r.get('skipped',0)}")


def reset_progress():
    c = input("⚠️  Sure ho? (yes/no): ")
    if c.lower() in ["yes", "y", "haan", "ha"]:
        for f in [PROGRESS_FILE, FAILED_FILE]:
            if os.path.exists(f):
                os.remove(f)
                print(f"✅ {f} deleted")
        print("✅ Reset! Fresh start hoga.")
    else:
        print("❌ Cancel.")


async def run_scheduler():
    interval = SCHEDULE_INTERVAL_HR * 3600
    print(f"⏰ Scheduler: har {SCHEDULE_INTERVAL_HR} ghante mein auto run")
    while True:
        print("\n⏰ Scheduled run...")
        await run_full()
        print(f"✅ Done. Next: {SCHEDULE_INTERVAL_HR} ghante mein")
        await asyncio.sleep(interval)


async def main():
    setup_logger()
    print_banner()

    if SCHEDULE_ENABLED:
        await run_scheduler()
        return

    while True:
        choice = show_menu()

        if choice == "1":
            await run_full()
        elif choice == "2":
            await run_collect()
        elif choice == "3":
            await run_ban()
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
    
