# ═══════════════════════════════════════════════
#   logger_setup.py — Logging Setup
# ═══════════════════════════════════════════════

import logging
import os
from datetime import datetime
from config import LOG_FILE


def setup_logger():
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)

    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)

    fmt = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # Console
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    console.setFormatter(fmt)

    # File
    today = datetime.now().strftime("%Y-%m-%d")
    log_path = os.path.join(os.path.dirname(LOG_FILE), f"{today}.log")
    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(fmt)

    # Clear old handlers
    logger.handlers.clear()
    logger.addHandler(console)
    logger.addHandler(file_handler)

    return logger
    
