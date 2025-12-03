import os
import json
from dotenv import load_dotenv
from datetime import datetime
import logging
import yaml

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
    return datetime.utcnow().isoformat() + "Z"

def load_state(path):
    if not os.path.exists(path):
        return {}
    with open(path, "r") as f:
        return json.load(f)

def save_state(path, obj):
    with open(path, "w") as f:
        json.dump(obj, f, indent=2)
