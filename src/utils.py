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
from typing import Union, Optional, Dict, Any

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
    import hashlib
    
    try:
        # Parse and normalize date
        date_obj = dateparser.parse(str(date_val))
        date_str = date_obj.strftime('%Y-%m-%d') if date_obj else 'unknown_date'
        
        # Normalize amount to 2 decimal places as string
        try:
            amount = float(amount_val)
            amount_str = f"{amount:.2f}"
        except (ValueError, TypeError):
            amount_str = str(amount_val).strip()
        
        # Normalize description
        desc = (desc_val or '').strip()
        
        # Create fingerprint
        fingerprint_str = f"{date_str}|{amount_str}|{desc}"
        return hashlib.sha256(fingerprint_str.encode('utf-8')).hexdigest()
    except Exception as e:
        LOG.error(f"Error generating fingerprint: {e}")
        # Fallback to a less reliable but more robust method
        return hashlib.sha256(f"{date_val}|{amount_val}|{desc_val}".encode('utf-8')).hexdigest()


def _load_category_config() -> Dict:
    """Load and cache the category configuration from YAML.
    
    Returns:
        Dict containing the category configuration with default values if not found.
    """
    if not hasattr(_load_category_config, '_cached_config'):
        from src.constants.config import CFG_PATHS
        
        try:
            for path in CFG_PATHS:
                if path.exists():
                    config = load_yaml(path)
                    if 'category_inference' in config:
                        _load_category_config._cached_config = config['category_inference']
                        break
            else:
                # Fallback to default config if no config file found
                _load_category_config._cached_config = {
                    'default_category': {
                        'id': 2,  # Uncategorized category
                        'name': 'Uncategorized',
                        'subcategory_id': 18,  # General subcategory
                        'subcategory_name': 'General'
                    },
                    'patterns': []
                }
                LOG.warning("No category_inference config found, using default configuration")
        except Exception as e:
            LOG.error(f"Error loading category config: {str(e)}")
            # Return default config on error
            _load_category_config._cached_config = {
                'default_category': {
                    'id': 2,  # Uncategorized category
                    'name': 'Uncategorized',
                    'subcategory_id': 18,  # General subcategory
                    'subcategory_name': 'General'
                },
                'patterns': []
            }
    return _load_category_config._cached_config


def infer_category(transaction: Dict[str, Any]) -> Dict[str, Any]:
    """Infer the most likely category for a transaction using config patterns.
    
    Args:
        transaction: Dictionary containing transaction details with:
            - description (str): Transaction description
            - merchant (str, optional): Merchant name
            - amount (float): Transaction amount
    
    Returns:
        dict: Dictionary with 'category_id', 'category_name', 'subcategory_id', 
              'subcategory_name', and 'confidence' if found
    """
    if not transaction:
        return {}
        
    description = (transaction.get('description') or '').lower()
    merchant = (transaction.get('merchant') or '').lower()
    
    # Get category config
    category_config = _load_category_config()
    default_category = category_config.get('default_category', {})
    
    # Check for matches in both description and merchant
    for category in category_config.get('patterns', []):
        for subcategory in category.get('subcategories', []):
            for pattern in subcategory.get('patterns', []):
                if (description and re.search(pattern, description)) or \
                   (merchant and re.search(pattern, merchant)):
                    return {
                        'category_id': category['id'],
                        'category_name': category['name'],
                        'subcategory_id': subcategory['id'],
                        'subcategory_name': subcategory['name'],
                        'confidence': 'high'
                    }
    
    # If no match found, return the default "Uncategorized" category
    return {
        'category_id': 2,  # Uncategorized category
        'category_name': 'Uncategorized',
        'subcategory_id': 18,  # General subcategory
        'subcategory_name': 'General',
        'confidence': 'low'
    }
