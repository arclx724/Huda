"""
config.py - Userbot Configuration
"""

# ── Telegram API Credentials ───────────────────────────────────────────────────
# Get these from https://my.telegram.org → "API development tools"
API_ID   = 123456          # Replace with your api_id (integer)
API_HASH = "your_api_hash" # Replace with your api_hash (string)

# ── Session Name ───────────────────────────────────────────────────────────────
# A .session file will be created with this name (keeps you logged in)
SESSION_NAME = "my_userbot"

# ── Message to Send ───────────────────────────────────────────────────────────
MESSAGE = """Hey! 👋
This is an automated message from me.
[Write your message here]"""

# ── Delay Between Each DM (in seconds) ────────────────────────────────────────
# Recommended: 5-10 seconds minimum to avoid Telegram spam limits
DELAY = 7  # seconds

# ── Target User IDs ───────────────────────────────────────────────────────────
# Add the user_ids of friends who don't have a Telegram username
USER_IDS = [
    123456789,   # Friend 1
    987654321,   # Friend 2
    112233445,   # Friend 3
    # Add more...
]
