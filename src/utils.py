import os
import json
import pandas as pd

import dateparser
from dotenv import load_dotenv
from datetime import datetime
import logging
import yaml
import hashlib
import re
import tempfile
from typing import Union, Optional, Dict

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


def clean_merchant_name(description: str, config: Optional[Dict] = None) -> str:
    """Clean up and standardize merchant names from transaction descriptions.
    
    Args:
        description: Raw description string from the transaction
        config: Optional configuration dictionary. If not provided, will use default config.
        
    Returns:
        str: Cleaned and standardized merchant name
    """
    if not description or not isinstance(description, str):
        return description or ""
        
    # Get merchant cleaning config, or use empty config if not available
    merchant_config = (config or {}).get('merchant_cleaning', {})
    patterns = merchant_config.get('patterns', [])
    merchants = merchant_config.get('merchants', [])
    
    # Convert to uppercase for case-insensitive matching
    cleaned = description.upper()
    
    # Apply patterns
    for pattern_config in patterns:
        pattern = pattern_config.get('pattern')
        replacement = pattern_config.get('replacement', '')
        if pattern:
            try:
                cleaned = re.sub(pattern, replacement, cleaned, flags=re.IGNORECASE)
            except re.error as e:
                LOG.warning(f"Invalid regex pattern '{pattern}': {e}")
    
    # Apply merchant-specific overrides
    for merchant in merchants:
        match_pattern = merchant.get('match')
        if match_pattern and re.search(match_pattern, cleaned, re.IGNORECASE):
            cleaned = merchant['name']
            break  # Stop after first match
    
    # Remove everything after newline if configured
    if merchant_config.get('remove_after_newline', True):
        cleaned = cleaned.split('\n')[0].strip()
    
    # Clean up whitespace
    cleaned = ' '.join(cleaned.split())
    
    # Fall back to legacy merchant_overrides if no match found
    if cleaned == description.upper() and 'merchant_overrides' in (config or {}):
        for pattern, replacement in (config['merchant_overrides'] or {}).items():
            if re.search(pattern, cleaned, re.IGNORECASE):
                cleaned = replacement
                break
    
    # Title case the result if it was changed
    if cleaned != description.upper():
        cleaned = ' '.join(word.capitalize() for word in cleaned.split())
    
    return cleaned or description

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


def parse_date_safe(s):
    """Safely parse a date string into ISO format (YYYY-MM-DD).
    
    Args:
        s: Input date string to parse
        
    Returns:
        str: Date in YYYY-MM-DD format, or None if parsing fails
    """
    if pd.isna(s) or not s:
        return None
        
    s = str(s).strip()
    current_year = datetime.now().year
    
    # Try parsing the date as-is first
    dt = dateparser.parse(s)
    if dt is not None:
        return dt.date().isoformat()
        
    # If first attempt fails, try appending current year
    dt = dateparser.parse(f"{s} {current_year}")
    if dt is not None:
        return dt.date().isoformat()
        
    return None


def parse_float_safe(v) -> float:
    try:
        return float(v)
    except (ValueError, TypeError):
        return 0.0


def generate_fingerprint(date_val: str, amount_val: Union[str, float], desc_val: str) -> str:
    """Generate a stable fingerprint for a transaction.
    
    Args:
        date_val: Date string in any parseable format
        amount_val: Transaction amount (string or float)
        desc_val: Transaction description
        
    Returns:
        A stable fingerprint string for the transaction
    """
    from datetime import datetime
    
    # Parse and normalize date to YYYY-MM-DD
    try:
        dt = dateparser.parse(str(date_val))
        if dt is None:
            raise ValueError(f"Could not parse date: {date_val}")
        date_str = dt.strftime("%Y-%m-%d")
    except Exception as e:
        raise ValueError(f"Invalid date format: {date_val}") from e
    
    # Normalize amount to float
    try:
        if isinstance(amount_val, str):
            # Remove any non-numeric characters except decimal point and negative sign
            amount_str = re.sub(r'[^\d.-]', '', str(amount_val))
            amount = float(amount_str)
        else:
            amount = float(amount_val)
    except (ValueError, TypeError) as e:
        raise ValueError(f"Invalid amount: {amount_val}") from e
    
    # Generate a slug from the description
    slug = merchant_slug(desc_val)
    
    # Create a fingerprint using the same logic as compute_import_id
    return compute_import_id(date_str, amount, slug)
