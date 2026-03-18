# ═══════════════════════════════════════════════
#   logger_setup.py — Logging Setup
#
#   Console + File dono mein logs save karta hai
#   File: logs/activity.log (date-wise)
# ═══════════════════════════════════════════════

import logging
import os
from datetime import datetime
from config import LOG_FILE


def setup_logger():
    # logs/ folder banao agar nahi hai
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)

    # Root logger configure karo
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)

    # Format
    fmt = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # ── Console Handler ──────────────────────────
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    console.setFormatter(fmt)

    # ── File Handler ─────────────────────────────
    # Aaj ki date se file naam banao
    today = datetime.now().strftime("%Y-%m-%d")
    log_path = LOG_FILE.replace("activity", today)

    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(fmt)

    logger.addHandler(console)
    logger.addHandler(file_handler)

    return logger
  
