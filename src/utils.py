import os
import json
from dotenv import load_dotenv
from datetime import datetime
import logging
import yaml
import hashlib
import re
import tempfile

load_dotenv()

LOG = logging.getLogger("cc_splitwise")
handler = logging.StreamHandler()
formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
handler.setFormatter(formatter)
LOG.addHandler(handler)
LOG.setLevel(os.getenv("LOG_LEVEL", "INFO"))

PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))

def load_yaml(path):
    with open(path, "r") as f:
        return yaml.safe_load(f)

def read_env(key, default=None):
    return os.getenv(key, default)

def mkdir_p(path):
    os.makedirs(path, exist_ok=True)

def now_iso():
    # Use timezone-aware UTC timestamp
    from datetime import timezone
    return datetime.now(timezone.utc).isoformat()

def load_state(path):
    if not os.path.exists(path):
        return {}
    with open(path, "r") as f:
        return json.load(f)

def save_state(path, obj):
    with open(path, "w") as f:
        json.dump(obj, f, indent=2)

def save_state_atomic(path, obj):
    """Write JSON to a temp file then atomically replace the destination."""
    d = os.path.dirname(path)
    if d and not os.path.exists(d):
        os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".tmp", dir=d)
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(obj, f, indent=2)
        os.replace(tmp, path)
    except OSError as e:
        # If replace failed, try to remove the temp file. Only catch OSError for filesystem ops.
        try:
            os.remove(tmp)
        except OSError:
            # If we can't remove the temp file, log and re-raise the original exception.
            LOG.warning("Failed to remove temp file %s: %s", tmp, e)
        raise


def merchant_slug(s: str) -> str:
    """Create a compact slug from merchant/description text."""
    if not s:
        return ""
    s = str(s).lower()
    # remove common company suffixes
    s = re.sub(r"\b(inc|llc|ltd|co|corp|company|the)\b", "", s)
    # keep alnum and replace others with hyphens
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s


def compute_import_id(date: str, amount: float, merchant: str) -> str:
    """Deterministic import id for a transaction.

    Uses date (ISO), amount in cents (rounded), and normalized merchant slug.
    Returns a sha256 hex digest.
    """
    cents = int(round(float(amount) * 100))
    key = f"{date}|{cents}|{merchant_slug(merchant)}"
    h = hashlib.sha256(key.encode("utf-8")).hexdigest()
    return h
