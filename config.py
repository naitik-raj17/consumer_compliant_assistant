import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

APP_NAME = "ConsumerGuard"

# Bundled resources (PyInstaller sets _MEIPASS), otherwise the source folder.
BASE_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
KB_SEED_DIR = BASE_DIR / "kb_seed"


def _data_dir() -> Path:
    override = os.environ.get("CG_DATA_DIR")
    if override:
        return Path(override)
    if sys.platform.startswith("win"):
        return Path(os.environ.get("APPDATA", str(Path.home() / "AppData" / "Roaming"))) / APP_NAME
    return Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local" / "share"))) / APP_NAME


DATA_DIR = _data_dir()
DB_PATH = DATA_DIR / "consumerguard.db"
PDF_DIR = DATA_DIR / "pdfs"
LOG_PATH = DATA_DIR / "consumerguard.log"

OLLAMA_URL = os.environ.get("CG_OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
LLM_MODEL = os.environ.get("CG_LLM_MODEL", "qwen2.5:1.5b")
EMBED_MODEL = os.environ.get("CG_EMBED_MODEL", "nomic-embed-text")
LLM_TIMEOUT = 300
EMBED_TIMEOUT = 60
PING_TIMEOUT = 2

# Pecuniary limits (CPA 2019 as amended by the 2021 rules), in rupees.
DISTRICT_LIMIT = 50_00_000      # Rs. 50 lakh
STATE_LIMIT = 2_00_00_000       # Rs. 2 crore

CHUNK_SIZE = 800
TOP_K = 4

CATEGORIES = ["ecommerce", "banking", "real_estate", "medical", "telecom", "other"]
STATUSES = ["submitted", "under_review", "drafted", "resolved", "rejected"]
ROLES = ["consumer", "admin"]

SEED_ADMIN_EMAIL = os.environ.get("CG_ADMIN_EMAIL", "admin@cg.local")
SEED_ADMIN_PASSWORD = os.environ.get("CG_ADMIN_PASSWORD", "KanikaIsBandar")


def ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    PDF_DIR.mkdir(parents=True, exist_ok=True)


def setup_logging() -> None:
    ensure_dirs()
    root = logging.getLogger()
    if any(isinstance(h, RotatingFileHandler) for h in root.handlers):
        return
    handler = RotatingFileHandler(LOG_PATH, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root.addHandler(handler)
    root.setLevel(logging.INFO)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
