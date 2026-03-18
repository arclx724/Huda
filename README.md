═══════════════════════════════════════════════
   🔐 Telegram Channel Privacy System v2
   Complete Setup Guide
═══════════════════════════════════════════════

📁 FILES:
  config.py       → Saari settings
  collector.py    → Concurrent groups scanner
  banner.py       → Multi-bot adaptive banner
  watcher.py      → Live new admin detector
  notifier.py     → Telegram notifications
  logger_setup.py → File + console logging
  main.py         → Entry point (yahi chalao)

─────────────────────────────────────────────
STEP 1 — Install dependencies
─────────────────────────────────────────────

  pip3 install telethon aiohttp tqdm

─────────────────────────────────────────────
STEP 2 — API credentials lo
─────────────────────────────────────────────

  1. https://my.telegram.org par jao
  2. Login karo
  3. "API development tools" click karo
  4. API_ID aur API_HASH copy karo
  5. config.py mein daalo

─────────────────────────────────────────────
STEP 3 — Bots banao (BotFather se)
─────────────────────────────────────────────

  1. @BotFather → /newbot → token copy karo
  2. Ye 2-3 baar karo
  3. Saare tokens config.py ke BOTS list mein
  4. Har bot ko channel mein:
     Admin → Ban Users permission deni hai

─────────────────────────────────────────────
STEP 4 — Notification setup (optional)
─────────────────────────────────────────────

  1. @userinfobot se apna User ID lo
  2. config.py mein NOTIFY_USER_ID daalo
  3. Koi bhi ek bot token NOTIFY_BOT_TOKEN mein
  4. Wo bot tumhe /start karo pehle!

─────────────────────────────────────────────
STEP 5 — config.py fill karo
─────────────────────────────────────────────

  API_ID      = 123456
  API_HASH    = "..."
  PHONE       = "+91XXXXXXXXXX"
  MY_CHANNEL  = "channel_username"

  BOTS = ["token1", "token2", "token3"]

  WHITELIST_IDS = [123456789]   # Trusted friends

─────────────────────────────────────────────
STEP 6 — Run karo
─────────────────────────────────────────────

  python3 main.py

─────────────────────────────────────────────
MENU OPTIONS:
─────────────────────────────────────────────

  [1] Full Run    → Collect + Ban ek saath
  [2] Collect     → Sirf list banao
  [3] Ban         → Saved list se ban karo
  [4] Retry       → Failed users dobara try
  [5] Watcher     → Live new admin auto-ban
  [6] Results     → Stats dekho
  [7] Reset       → Fresh start

─────────────────────────────────────────────
BACKGROUND (AWS + Screen)
─────────────────────────────────────────────

  # Ek session: Ban + Watcher dono
  screen -S ban
  python3 main.py  → Option 1
  Ctrl+A D

  screen -S watch
  python3 main.py  → Option 5
  Ctrl+A D

  # Wapas aao
  screen -r ban
  screen -r watch

─────────────────────────────────────────────
AUTO SCHEDULE (Weekly auto-run)
─────────────────────────────────────────────

  config.py mein:
  SCHEDULE_ENABLED     = True
  SCHEDULE_INTERVAL_HR = 168   # 1 week

  Phir: python3 main.py
  Khud har hafte run karega!

═══════════════════════════════════════════════
FEATURES SUMMARY:
─────────────────────────────────────────────
  ✅ Concurrent collection (3x faster)
  ✅ Multi-bot parallel banning
  ✅ Bot health check before start
  ✅ Smart retry (3 attempts per user)
  ✅ Adaptive delay per bot
  ✅ Dead bot redistribution
  ✅ Progress bar (tqdm)
  ✅ Resume support (beech mein ruka?)
  ✅ Failed users retry
  ✅ Live new admin watcher
  ✅ Telegram notifications
  ✅ Whitelist support
  ✅ File logging (logs/ folder)
  ✅ Auto scheduler
═══════════════════════════════════════════════

