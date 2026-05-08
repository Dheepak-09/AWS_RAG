import os
import logging
from logging.handlers import RotatingFileHandler

# ---------------------------------------------------------------------------
# Log directory
# ---------------------------------------------------------------------------
LOG_DIR  = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")
LOG_FILE = os.path.join(LOG_DIR, "app.log")

os.makedirs(LOG_DIR, exist_ok=True)

# ---------------------------------------------------------------------------
# Log format
# ---------------------------------------------------------------------------
LOG_FORMAT  = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# ---------------------------------------------------------------------------
# Setup function — called once at startup
# ---------------------------------------------------------------------------
def setup_logging():
    """
    Configure root logger with:
    - Console handler  → shows logs in terminal (uvicorn output)
    - File handler     → writes to logs/app.log (rotates at 5MB, keeps 3 backups)
    Both at INFO level.
    """
    formatter = logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT)

    # -- Console handler -----------------------------------------------------
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)

    # -- File handler (rotating) ---------------------------------------------
    # Max 5MB per file, keeps last 3 backup files
    file_handler = RotatingFileHandler(
        LOG_FILE,
        maxBytes=5 * 1024 * 1024,  # 5 MB
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)

    # -- Root logger ---------------------------------------------------------
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    # Avoid adding duplicate handlers if setup_logging() is called more than once
    if not root_logger.handlers:
        root_logger.addHandler(console_handler)
        root_logger.addHandler(file_handler)

    # Silence noisy third-party loggers
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("botocore").setLevel(logging.WARNING)
    logging.getLogger("boto3").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)


# ---------------------------------------------------------------------------
# Get a named logger for each module
# Usage: from app.logger import get_logger
#        logger = get_logger(__name__)
# ---------------------------------------------------------------------------
def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)