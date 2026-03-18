# ═══════════════════════════════════════════════
#   config.py — Saari settings ek jagah
# ═══════════════════════════════════════════════

# ── Tumhara Userbot ─────────────────────────────
API_ID      = 123456
API_HASH    = "your_api_hash_here"
PHONE       = "+91XXXXXXXXXX"
SESSION     = "collector_session"

# ── Tumhara Channel ─────────────────────────────
MY_CHANNEL  = "your_channel_username"   # @ ke bina

# ── Bots (BotFather se banao) ───────────────────
# Saare bots channel mein ADMIN + BAN permission ke saath add karo
BOTS = [
    "111111111:AAA-your-bot-1-token",
    "222222222:BBB-your-bot-2-token",
    "333333333:CCC-your-bot-3-token",
]

# ── Notification Bot ────────────────────────────
# Koi bhi ek bot ka token yahan daalo jo tumhe updates bheje
# Aur apna Telegram User ID daalo (https://t.me/userinfobot se pata karo)
NOTIFY_BOT_TOKEN = "your_notify_bot_token"   # Koi bhi ek bot token
NOTIFY_USER_ID   = 123456789                 # Tumhara Telegram user ID
NOTIFY_EVERY     = 100                       # Har 100 bans pe notification

# ── Whitelist ───────────────────────────────────
# Ye users kabhi ban nahi honge — User IDs daalo
WHITELIST_IDS = [
    # 123456789,   # Example: apna koi trusted friend
    # 987654321,
]

# ── Speed Settings ──────────────────────────────
BASE_DELAY        = 1.5    # Starting delay (sec)
FLOOD_INCREASE    = 2.5    # FloodWait pe delay kitna badhao
FLOOD_DECREASE    = 0.15   # Success pe delay kitna ghataao
MIN_DELAY         = 0.5    # Minimum delay
MAX_DELAY         = 20.0   # Maximum delay
SUCCESS_THRESHOLD = 15     # Kitne success ke baad speed badhao
MAX_RETRIES       = 3      # Fail hone pe kitni baar retry karo

# ── Concurrent Collection ───────────────────────
COLLECTOR_CONCURRENT = 3   # Ek saath kitne groups scan ho

# ── Auto Scheduler ──────────────────────────────
SCHEDULE_ENABLED     = False   # True karo auto-run ke liye
SCHEDULE_INTERVAL_HR = 168     # Har kitne ghante mein run karo (168 = 1 week)

# ── Files ───────────────────────────────────────
TARGETS_FILE  = "targets.json"
RESULTS_FILE  = "results.json"
PROGRESS_FILE = "progress.json"
FAILED_FILE   = "failed.json"
LOG_FILE      = "logs/activity.log"

