import os
import json
import pandas as pd

import dateparser
from dotenv import load_dotenv
from datetime import datetime, date
import logging
import yaml
import hashlib
import re
import tempfile
from functools import cache
from typing import Union, Optional, Dict, Any

load_dotenv()

LOG = logging.getLogger("cc_splitwise")
handler = logging.StreamHandler()
formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
handler.setFormatter(formatter)
LOG.addHandler(handler)
LOG.setLevel(os.getenv("LOG_LEVEL", "INFO"))

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))


def load_yaml(path):
    with open(path, "r") as f:
        return yaml.safe_load(f)


def clean_description_for_splitwise(
    description: str, config: Optional[Dict] = None
) -> str:
    """Clean and normalize transaction descriptions for human readability in Splitwise.

    Removes technical noise like transaction IDs, payment method prefixes, URLs, country codes,
    and formats the result to be human-readable.

    Args:
        description: Raw description from credit card statement
        config: Optional configuration for cleaning rules

    Returns:
        str: Clean, human-readable description suitable for Splitwise

    Examples:
        >>> clean_description_for_splitwise("GRAB*A-8PXHISMWWU9TASINGAPORE           SG")
        'Grab'
        >>> clean_description_for_splitwise("GglPay GUARDIAN HEALTH & BEAUTY-1110104105")
        'Guardian Health & Beauty'
        >>> clean_description_for_splitwise("UBER EATS           help.uber.com       CA")
        'Uber Eats'
    """
    if not description or not isinstance(description, str):
        return description or ""

    # Start with original
    cleaned = description.strip()

    # Try merchant lookup first - if we know this merchant, use canonical name
    merchant_lookup = _load_merchant_lookup()
    normalized_merchant = clean_merchant_name(cleaned).lower()
    if normalized_merchant in merchant_lookup:
        merchant_info = merchant_lookup[normalized_merchant]
        # Use a readable version of the merchant key
        canonical_name = " ".join(word.title() for word in normalized_merchant.split())
        LOG.info(f"Using canonical merchant name: '{canonical_name}' (from lookup)")
        return canonical_name

    # 0. Extract meaningful lines from multiline descriptions
    if "\n" in cleaned:
        lines = [line.strip() for line in cleaned.split("\n") if line.strip()]
        # Strategy: look for the second or third line as it often has the merchant name
        # Skip generic category labels (LODGING, RESTAURANT, ONLINE SUBS, etc.)
        category_words = {
            "LODGING",
            "RESTAURANT",
            "ONLINE",
            "SUBS",
            "TAXICAB",
            "LIMOUSINE",
            "BEAUTY",
            "BARBER",
            "SHOP",
            "MASSAGE",
            "PARLOR",
            "DUTY-FREE",
            "STORE",
        }
        best_line = ""
        for line in lines:
            # Skip transaction IDs (long hex or numeric codes at start)
            if re.match(r"^[0-9a-f]{8,}", line, re.IGNORECASE):
                continue
            if re.match(
                r"^\d{4,}\s+\d+", line
            ):  # Skip lines like "3152388905  88099554"
                continue
            # Skip lines that are just category labels
            words = set(line.upper().split())
            if words and words.issubset(category_words):
                continue
            # Skip very short lines (less than 3 chars)
            if len(line) <= 3:
                continue
            # Prefer lines with actual merchant names (containing letters and meaningful length)
            if re.search(r"[a-zA-Z]{3,}", line) and len(line) > 3:
                best_line = line
                break
        if best_line:
            cleaned = best_line
        elif lines:
            # Fallback: try to find any line with letters
            for line in lines:
                if re.search(r"[a-zA-Z]{3,}", line):
                    cleaned = line
                    break
            else:
                cleaned = lines[0]

    # 1. Remove transaction IDs (alphanumeric codes after * or -)
    cleaned = re.sub(r"[*-][A-Z0-9]{10,}", "", cleaned)

    # 2. Remove payment method prefixes (more comprehensive)
    payment_prefixes = [
        r"^GglPay\s+",
        r"^ApplePay\s+",
        r"^AMZN\s+Mktp\s+",
        r"^SQ\s*\*\s*",
        r"^Grab\*\s*",
        r"^PayPal\s*\*\s*",
        r"^TST\*\s+",
        r"^SP\s+",
    ]
    for prefix in payment_prefixes:
        cleaned = re.sub(prefix, "", cleaned, flags=re.IGNORECASE)

    # 3. Remove URLs and domains
    cleaned = re.sub(r"https?://[^\s]+", "", cleaned)
    cleaned = re.sub(r"www\.[^\s]+", "", cleaned)
    cleaned = re.sub(r"\bhelp\.[a-z]+\.com\b", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\b[a-z]+\.com\b", "", cleaned, flags=re.IGNORECASE)

    # 4. Remove reference numbers and codes
    cleaned = re.sub(r"^[A-Z0-9]{6,}\s+", "", cleaned)
    cleaned = re.sub(r"^\d{4,}\s+", "", cleaned)
    cleaned = re.sub(r"-\d{6,}", "", cleaned)  # Remove trailing codes like -1110104105

    # 5. Remove phone numbers in various formats
    cleaned = re.sub(r"\(\d{3}\)\d{3}-\d{4}", "", cleaned)
    cleaned = re.sub(r"\+?\d{10,}", "", cleaned)

    # 6. Remove country codes and location patterns
    location_patterns = [
        r"\s+SINGAPORE\s*\d*",
        r"\s+BADUNG\s*-?\s*BALI?",
        r"\s+JAKARTA\s+[A-Z]{3}",
        r"\s+GIANYAR\s*-?\s*BAL?",
        r"\s+DENPASAR",
        r",?\s*[A-Z]{2}\s*\d{5}",  # State code + zip
        r"\s+[A-Z]{2}$",  # Country code at end
        r"\s+NA$",  # Remove "NA" at end
    ]
    for pattern in location_patterns:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)

    # 7. Remove trailing/leading category descriptions
    cleaned = re.sub(
        r"^\s*(ONLINE\s+SUBS?|LODGING|RESTAURANT|TAXICAB|BEAUTY|BARBER\s+SHOP)\s+",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        r"\s+(ONLINE\s+SUBS?|LODGING|RESTAURANT|TAXICAB|BEAUTY|BARBER\s+SHOP)$",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )

    # 8. Fix concatenated words (missing spaces) - lowercase followed by uppercase
    cleaned = re.sub(r"([a-z])([A-Z])", r"\1 \2", cleaned)

    # 9. Remove trailing special characters, numbers, and extra codes
    cleaned = re.sub(r"[*#\-]+$", "", cleaned)
    cleaned = re.sub(r"\s+\d{4,}$", "", cleaned)  # Remove trailing long numbers
    cleaned = re.sub(r"\s+[A-Z0-9]{5,}$", "", cleaned)  # Remove trailing codes
    cleaned = re.sub(r"\s+HO$", "", cleaned, flags=re.IGNORECASE)  # Remove " HO" suffix

    # 10. Collapse multiple spaces
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    # 11. Remove standalone very short words and numeric-only words
    words = cleaned.split()
    words = [w for w in words if not (w.isdigit() and len(w) < 5)]
    cleaned = " ".join(words)

    # 12. Title case for better readability
    words = cleaned.split()
    formatted_words = []
    for word in words:
        if len(word) <= 3 and word.isupper():
            # Keep short all-caps words (e.g., "USA", "NYC", "BMW")
            formatted_words.append(word)
        elif word.isupper() and len(word) > 3:
            # Title case long all-caps words
            formatted_words.append(word.title())
        elif word.islower():
            # Title case lowercase words
            formatted_words.append(word.title())
        else:
            # Keep mixed case as-is (likely proper nouns)
            formatted_words.append(word)
    cleaned = " ".join(formatted_words)

    # 13. Fallback: if we cleaned too much, return a shortened original
    if not cleaned or len(cleaned) < 3:
        # Take first meaningful part of original
        cleaned = description.replace("\n", " ").strip()[:50]
        cleaned = re.sub(r"[*-][A-Z0-9]{10,}", "", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        # Simple title case
        cleaned = " ".join(word.title() for word in cleaned.split())

    return cleaned


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
    merchant_config = (config or {}).get("merchant_cleaning", {})
    patterns = merchant_config.get("patterns", [])
    merchants = merchant_config.get("merchants", [])

    # Start with the original description
    cleaned = description.strip()

    # Split into lines and work with them
    lines = [line.strip() for line in cleaned.split("\n") if line.strip()]

    # Common patterns to identify and remove
    # Transaction IDs (hex strings, alphanumeric codes at start)
    transaction_id_patterns = [
        r"^[0-9a-f]{7,}\s+",  # Hex IDs at start
        r"^[A-Z0-9]{7,}\s+",  # Alphanumeric IDs at start
        r"^\d{10,}\s+",  # Long numeric IDs
        r"^\d{4}-\d{2}-\d{2}\s+",  # Date patterns at start
        r"^\d{10,}[A-Z@.]+\s*",  # Long numbers followed by text (phone/email patterns)
        r"^\+\d{10,}\s+",  # Phone numbers at start like +18556687574
    ]

    # Patterns to skip when evaluating candidate lines
    skip_line_patterns = [
        r"^\d{10,}[@A-Z.]+",  # Phone/email patterns
        r"^\+\d{10,}",  # Phone numbers with +
        r"^(?:CH|NT)_[A-Z0-9]+\s+\+\d{10,}$",  # Stripe/payment charge with phone like "CH_2SFYNP7Q +18556687574"
        r"^\d{1,3}[\.,]\d{3}[\.,]\d{3}[\.,]\d{2}\s+.*RUPIAH",  # Indonesian rupiah amounts
        r"^FOREIGN SPEND AMOUNT:",
        r"^COMMISSION AMOUNT:",
        r"^CURRENCY EXCHANGE RATE:",
        r"^TICKET NUMBER\s*:",
        r"^ADDITIONAL INFO\s*:",
        r"^DESCRIPTION\s*:",
        r"^PRICE\s*:",
        r"^\(?\d{3}\)?[\s\.-]?\d{3}[\s\.-]?\d{4}$",  # Phone numbers: (800)698-4637, 800-806-6453, 415-348-6377
        r"^1?800\d{7}$",  # Toll-free without dashes: 8006984637, 18002211212 (11 digits)
        r"^\d{3}-\d{3}-\d{4}$",  # Standard phone format: 415-348-6377
        r"^\d{10,11}$",  # 10-11 digit numbers (phone/ID): 4158005959, 18002211212
        r"^\d{8,9}$",  # 8-9 digit numbers (likely phone or ID): 66362100, 9566306007
        r"^0{2,}\d{1,5}$",  # Numbers with leading zeros: 007093, 000010
        r"^\d{3,5}$",  # Short numeric codes: 811, 94403
        r"^\d{15,}$",  # Very long concatenated numbers: 128358141588002383150
        r"^[A-Z0-9]{5,12}\s+[\d\-\(\)]+$",  # Transaction ID + phone number pattern
    ]

    # Category labels that appear in Amex descriptions
    category_labels = [
        "TELECOM SERVICE",
        "CABLE & PAY TV",
        "TAXICAB & LIMOUSINE",
        "ONLINE SUBS",
        "MERCHANDISE",
        "PASSENGER TICKET",
        "LODGING",
        "BEAUTY/BARBER SHOP",
        "BEAUTY & BARBER",
        "MEDICAL SERVICE",
        "SPORTS CLOTHING",
        "LUXURY MATTR",
        "CONNECTIVITY",
        "INSURANCE",
        "COMPUTER PROGRAMMING",
        "LARGE DIGITAL GOODS M",
        "SQUAREUP.COM/RECEIPTS",
        "DUTY-FREE STORE",
        "MISC FOOD STORE",
        "MISC/SPECIALTY RETAIL",
        "RESTAURANT",
        "MASSAGE PARLOR",
        "SHOE STORE",
        "FAMILY CLOTHING",
        "HEALTH & BEAUTY",
        "EDUCATIONAL SERVICE",
        "ARTIST SUPPLY & CRAFT",
        "RECREATION SERVICE",
    ]

    # Payment processor prefixes and special merchants
    payment_processors = {
        # Stripe transaction patterns - extract merchant name after phone
        r"^CH_[A-Z0-9]+\s+\+?\d{10,}\s+": "",  # Remove CH_ transaction ID and phone
        r"^NT_[A-Z0-9]+\s+\+?\d{10,}\s+": "",  # Remove NT_ transaction ID and phone
        # Specific merchant patterns from review corrections
        r"\bNIKE\.COM\b": "Nike",
        r"\bPLANTTHERAPY\.COM\b": "Planttherapy",
        r"\bGOVEE\b": "Govee",
        # Airlines - extract full name
        r"\bAMERICAN\s+AIRLINES\b": "American Airlines",
        r"\bJETBLUE\s+AIRWAYS\b": "JetBlue Airways",
        r"\bUNITED\s+AIRLINES\b": "United Airlines",
        r"\bEMIRATES\s+AIRLINES\b": "Emirates",
        # Amazon - clean up merchandise patterns
        r"^[A-Z0-9]{7,}\s+MERCHANDISE.*": "",  # Remove transaction ID + merchandise
        r"\bAMAZON\.COM\b": "Amazon",
        r"\bAMAZON\s+MARKETPLACE\s+NA\s+PA\b": "Amazon Marketplace",
        r"\bAMAZON\s+MARKETPLACE\b": "Amazon",
        # Grab - any GRAB* transaction
        r"\bGRAB\s*\*\s*[A-Z0-9-]*": "Grab",  # Matches GRAB*A-8PXHISMWWU9TAV, Grab* A-8OTSU6QGX53TAV
        # Uber patterns
        r"\b[A-Z0-9]{6,}\s+UBER\s+EATS\b": "Uber Eats",  # Codes like BNJNFFMM before UBER EATS
        r"\b[A-Z0-9]{6,}\s+UBER TRIP\b": "Uber Trip",  # Codes like SR2VRFGO before Uber Trip
        r"\bUBER\s+TRIP\b": "Uber Trip",
        r"\bUBER\s+EATS\b": "Uber Eats",
        r"\bUBER\s+": "Uber ",
        # Google services
        r"\bGOOGLE\s*\*\s*FI\s+[A-Z0-9]+": "Google Fi",  # Google Fi with reference code
        r"\bGOOGLE\s*\*\s*": "Google ",
        # Payment processors
        r"\bGGLPAY\s+": "",  # Remove GglPay prefix entirely
        r"\bPAYPAL\s*\*?\s*": "PayPal ",
        r"\bSQ\s*\*\s*": "Square ",
        r"\bAMZN\s+": "Amazon ",
        r"\bSP\s+": "",  # Remove SP prefix
    }

    # Common city names and location indicators to remove
    location_patterns = [
        r"\b(?:SAN FRANCISCO|SANTA MONICA|NEW YORK|LOS ANGELES|SEATTLE|PORTLAND|"
        r"CHICAGO|BOSTON|TORONTO|VANCOUVER|LONDON|PARIS|TOKYO|LONG BEACH|TWIN FALLS|"
        r"BEAVERTON|TSUEN WAN)\b",
        r"\b(?:CA|NY|WA|TX|FL|IL|MA|OR|DC|SG|UK|GB|NA|HK|ID)\s*$",  # State/country codes at end only
    ]

    # URLs and domains to remove
    url_patterns = [
        r"SQUAREUP\.COM/RECEIPTS",
        r"G\.CO/HELPPAY#?",
        r"HELP\.UBER\.COM",
        r"AMZN\.COM/BILL",
        r"HULU\.COM/BILL",
        # Don't remove brand domains - only generic ones
        # r"\b[A-Z]+\.COM\b",  # Disabled - removes Nike.com, Planttherapy.com etc
    ]

    # Foreign transaction details
    foreign_patterns = [
        r"FOREIGN SPEND AMOUNT:.*$",
        r"COMMISSION AMOUNT:.*$",
        r"CURRENCY EXCHANGE RATE:.*$",
    ]

    #Process lines to find the best merchant name
    # Strategy: Prefer lines with GglPay or actual merchant names
    candidate_lines = []
    gglpay_lines = []
    
    for line in lines:
        line_upper = line.upper()

        # Skip lines matching skip patterns
        if any(re.match(pattern, line_upper) for pattern in skip_line_patterns):
            continue

        # Skip lines that start with transaction ID + category label (like "RXBZZ6DJHJM CABLE & PAY TV")
        # Pattern: alphanumeric ID followed by a category label
        if re.match(r"^[A-Z0-9]{7,}\s+", line_upper):
            # Check if the rest is a category label
            rest = re.sub(r"^[A-Z0-9]{7,}\s+", "", line_upper)
            if rest in category_labels:
                continue
        
        # Skip lines that are NUMBER + category label (like "007093      LODGING")
        if re.match(r"^\d+\s+", line_upper):
            rest = re.sub(r"^\d+\s+", "", line_upper)
            if rest in category_labels:
                continue
        
        # Skip lines with transaction IDs + phone/number patterns (like "1Z6ET73P132800 811 1648")
        if re.match(r"^[A-Z0-9]{10,}\s+\d+", line_upper):
            continue
        
        # Skip lines that are SHORT_CODE + PHONE (like "JZD 512-487-1630")
        # But extract the short code as it's likely the merchant
        phone_with_code = re.match(r"^([A-Z]{2,5})\s+[\d\-\(\)]+$", line_upper)
        if phone_with_code:
            # Use the code part as merchant name
            candidate_lines.append(phone_with_code.group(1))
            continue

        # Skip lines that are just category labels
        if line_upper in category_labels:
            continue

        # Skip lines that are just locations
        if line_upper in [
            "CA",
            "NY",
            "SG",
            "UK",
            "USA",
            "NA",
            "SAN FRANCISCO",
            "NEW YORK",
            "SINGAPORE",
            "DENPASAR",
            "BADUNG",
            "GIANYAR",
            "JAKARTA SLT",
            "BADUNG - BALI",
            "GIANYAR - BAL",
            "SANTA MONICA",
        ]:
            continue

        # Skip lines that are URLs or domain patterns
        if any(re.search(pattern, line_upper) for pattern in url_patterns):
            continue

        # Skip foreign transaction detail lines
        if any(re.search(pattern, line_upper) for pattern in foreign_patterns):
            continue

        # Prioritize lines with merchant names over emails
        # Check if this line has an actual business name (not email, not city)
        has_merchant_name = any([
            "LEFT DOOR" in line_upper,
            "GOVEE" in line_upper,
            "PLANTTHERAPY" in line_upper,
            "NIKE" in line_upper,
            "AMAZON" in line_upper,
        ])
        
        # Prioritize lines with GglPay or common merchant indicators
        if "GGLPAY" in line_upper or "GOOGLE" in line_upper or "UBER" in line_upper or "GRAB" in line_upper or has_merchant_name:
            gglpay_lines.append(line)
        else:
            candidate_lines.append(line)

    # Use GglPay lines first, then other candidates
    if gglpay_lines:
        cleaned = gglpay_lines[0]
    elif candidate_lines:
        cleaned = candidate_lines[0]
    else:
        cleaned = description
    
    # CRITICAL RULE: If selected line is just numbers/dashes/parens, skip it and try next candidate
    # This catches any numeric-only patterns that slipped through
    if re.match(r'^[\d\s\-\(\)\.]+$', cleaned.strip()):
        # Try to find a non-numeric candidate
        for candidate in candidate_lines[1:] + gglpay_lines[1:]:
            if not re.match(r'^[\d\s\-\(\)\.]+$', candidate.strip()):
                cleaned = candidate
                break
        else:
            # If all candidates are numeric, use the original description
            cleaned = description

    # Convert to uppercase for processing
    cleaned = cleaned.upper()

    # Remove transaction IDs from the start
    for pattern in transaction_id_patterns:
        cleaned = re.sub(pattern, "", cleaned)

    # Remove category labels
    for label in category_labels:
        cleaned = re.sub(
            r"\b" + re.escape(label) + r"\b", "", cleaned, flags=re.IGNORECASE
        )

    # Apply payment processor patterns
    for pattern, replacement in payment_processors.items():
        cleaned = re.sub(pattern, replacement, cleaned, flags=re.IGNORECASE)

    # Remove URLs and domains
    for pattern in url_patterns:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)

    # Remove location patterns
    for pattern in location_patterns:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)

    # Remove foreign transaction details
    for pattern in foreign_patterns:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)

    # Apply configured patterns from config
    for pattern_config in patterns:
        pattern = pattern_config.get("pattern")
        replacement = pattern_config.get("replacement", "")
        if pattern:
            try:
                cleaned = re.sub(pattern, replacement, cleaned, flags=re.IGNORECASE)
            except re.error as e:
                LOG.warning(f"Invalid regex pattern '{pattern}': {e}")

    # Apply merchant-specific overrides from config
    for merchant in merchants:
        match_pattern = merchant.get("match")
        if match_pattern and re.search(match_pattern, cleaned, re.IGNORECASE):
            cleaned = merchant["name"]
            break  # Stop after first match

    # Remove trailing store/location IDs (like -1110104105, BAL0313, 0215)
    cleaned = re.sub(r"-\d{10,}$", "", cleaned)  # -1110104105
    cleaned = re.sub(r"\s+\d{10,}$", "", cleaned)  # 000000126458
    cleaned = re.sub(r"\s+[A-Z]{3,}\d{4,}\s+\w+$", "", cleaned, flags=re.IGNORECASE)  # BAL0313 CAMPUH
    cleaned = re.sub(r"\s+\d{4}$", "", cleaned)  # Trailing 4-digit codes like 0215
    cleaned = re.sub(r"-\d{7,}$", "", cleaned)  # -1119108
    
    # Remove trailing location phrases
    cleaned = re.sub(r"\s+BADUNG - BALI\s+LODGING$", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+SINGAPORE\s+-\s*FO$", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+NGEE ANN CITY$", "", cleaned, flags=re.IGNORECASE)
    
    # Remove company suffixes
    cleaned = re.sub(r"\s+(?:SINGAPORE\s+)?PTE\.?\s+LTD\.?", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+\(SINGAPORE\)", "", cleaned, flags=re.IGNORECASE)
    
    # Remove phone numbers that slipped through
    cleaned = re.sub(r"^\+?\d{10,}\s+", "", cleaned)  # Phone at start
    cleaned = re.sub(r"\s+\+?\d{10,}$", "", cleaned)  # Phone at end
    cleaned = re.sub(r"\s+\(\d{3}\)\d{3}-\d{4}", "", cleaned)  # (800)698-4637 format
    cleaned = re.sub(r"^\d{10,}\s+", "", cleaned)  # Long numbers at start like 18556687574
    
    # Remove "HO" suffix (head office marker in some names)
    # But be careful - "HO" can be part of name like "MEXICOLA HO"
    # Only remove if it looks like a suffix
    cleaned = re.sub(r"\s+HO$", "", cleaned, flags=re.IGNORECASE)

    # Clean up whitespace and special characters
    cleaned = " ".join(cleaned.split())
    cleaned = re.sub(
        r"[^\w\s&/-]", "", cleaned
    )  # Keep letters, numbers, spaces, &, /, and -

    # Remove trailing/leading hyphens and ampersands
    cleaned = cleaned.strip("- &/")

    # Title case the result
    cleaned = " ".join(word.capitalize() for word in cleaned.split())

    # Handle special cases for acronyms and brands
    special_cases = {
        "Fi": "Fi",  # Google Fi
        "Uber": "Uber",
        "Hulu": "Hulu",
        "Grab": "Grab",
        "Nyc": "NYC",
        "Usa": "USA",
        "Uk": "UK",
        "Mrt": "MRT",  # Mass Rapid Transit
        "Pte": "Pte",
        "Ltd": "Ltd",
        "Ho": "HO",  # Head Office (when part of name like "Mexicola HO")
    }

    words = cleaned.split()
    for i, word in enumerate(words):
        if word in special_cases:
            words[i] = special_cases[word]
        # Handle Bus/MRT case - keep slash
        if "/" in word:
            parts = word.split("/")
            word = "/".join([special_cases.get(p, p) for p in parts])
            words[i] = word
    cleaned = " ".join(words)

    return cleaned.strip() or description


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


def parse_date(s: str) -> date:
    """Parse a date string and return a datetime.date.

    Raises ValueError if parsing fails. This is a small helper intended for
    callers that want a date object (unlike parse_date_safe which returns an ISO
    string or None).
    """
    if s is None:
        raise ValueError("No date string provided")
    parsed = dateparser.parse(str(s))
    if not parsed:
        raise ValueError(f"Could not parse date: {s}")
    return parsed.date()


def parse_float_safe(v) -> float:
    try:
        return float(v)
    except (ValueError, TypeError):
        return 0.0


def generate_fingerprint(
    date_val: str, amount_val: Union[str, float], desc_val: str
) -> str:
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
        date_str = date_obj.strftime("%Y-%m-%d") if date_obj else "unknown_date"

        # Normalize amount to 2 decimal places as string
        try:
            amount = float(amount_val)
            amount_str = f"{amount:.2f}"
        except (ValueError, TypeError):
            amount_str = str(amount_val).strip()

        # Normalize description
        desc = (desc_val or "").strip()

        # Create fingerprint
        fingerprint_str = f"{date_str}|{amount_str}|{desc}"
        return hashlib.sha256(fingerprint_str.encode("utf-8")).hexdigest()
    except Exception as e:
        LOG.error(f"Error generating fingerprint: {e}")
        # Fallback to a less reliable but more robust method
        return hashlib.sha256(
            f"{date_val}|{amount_val}|{desc_val}".encode("utf-8")
        ).hexdigest()


@cache
def _load_amex_category_mapping() -> Dict:
    """Load and cache the Amex category to Splitwise category mapping.

    Returns:
        Dict mapping Amex category names to Splitwise category paths (Category > Subcategory).
    """
    mapping_path = os.path.join(PROJECT_ROOT, "config", "amex_category_mapping.json")
    try:
        if os.path.exists(mapping_path):
            with open(mapping_path, "r") as f:
                result = json.load(f)
            LOG.info(f"Loaded {len(result)} Amex category mappings")
            return result
        else:
            LOG.warning(f"Amex category mapping file not found: {mapping_path}")
            return {}
    except Exception as e:
        LOG.error(f"Error loading Amex category mapping: {e}")
        return {}


@cache
def _load_splitwise_category_ids() -> Dict[str, Any]:
    """Load Splitwise category ID mappings from JSON (cached).

    Returns:
        Dict with 'category_mapping' (full path -> IDs) and 'category_lookup' (name -> [IDs])
    """
    mapping_path = os.path.join(PROJECT_ROOT, "config", "splitwise_category_ids.json")
    try:
        if os.path.exists(mapping_path):
            with open(mapping_path, "r") as f:
                result = json.load(f)
            LOG.debug(
                f"Loaded {len(result.get('category_mapping', {}))} category ID mappings"
            )
            return result
        else:
            LOG.warning(f"Splitwise category IDs file not found: {mapping_path}")
            return {"category_mapping": {}, "category_lookup": {}}
    except Exception as e:
        LOG.error(f"Error loading Splitwise category IDs: {e}")
        return {"category_mapping": {}, "category_lookup": {}}


def _resolve_category_ids(category_path: str) -> Optional[Dict[str, Any]]:
    """Resolve a category path (e.g., 'Transportation > Taxi') to category and subcategory IDs.

    Args:
        category_path: Full category path in format 'Category > Subcategory'

    Returns:
        Dict with category_id, category_name, subcategory_id, subcategory_name, or None
    """
    category_ids = _load_splitwise_category_ids()
    category_mapping = category_ids.get("category_mapping", {})

    if category_path in category_mapping:
        return category_mapping[category_path]

    # Try to find by subcategory name alone (if unambiguous)
    category_lookup = category_ids.get("category_lookup", {})
    if " > " in category_path:
        subcategory_name = category_path.split(" > ")[1]
        matches = category_lookup.get(subcategory_name, [])
        if len(matches) == 1:
            # Unambiguous match
            match = matches[0]
            return {
                "category_id": match["category_id"],
                "category_name": match["category_name"],
                "subcategory_id": match["subcategory_id"],
                "subcategory_name": subcategory_name,
            }

    LOG.warning(f"Could not resolve category path: {category_path}")
    return None


@cache
def _load_merchant_lookup() -> Dict:
    """Load and cache the merchant category lookup from JSON.

    Returns:
        Dict mapping normalized merchant names to category info.
    """
    lookup_path = os.path.join(PROJECT_ROOT, "config", "merchant_category_lookup.json")
    try:
        if os.path.exists(lookup_path):
            with open(lookup_path, "r") as f:
                result = json.load(f)
            LOG.info(f"Loaded {len(result)} merchants from lookup")
            return result
        else:
            LOG.warning(f"Merchant lookup file not found: {lookup_path}")
            return {}
    except Exception as e:
        LOG.error(f"Error loading merchant lookup: {e}")
        return {}


@cache
def _load_category_config() -> Dict:
    """Load and cache the category configuration from YAML.

    Returns:
        Dict containing the category configuration with default values if not found.
    """
    from src.constants.config import CFG_PATHS

    default_config = {
        "default_category": {
            "id": 2,  # Uncategorized category
            "name": "Uncategorized",
            "subcategory_id": 18,  # General subcategory
            "subcategory_name": "General",
        },
        "patterns": [],
    }

    try:
        LOG.info(f"Looking for config files in: {CFG_PATHS}")
        for path in CFG_PATHS:
            LOG.info(f"Checking if config file exists: {path} - {path.exists()}")
            if path.exists():
                LOG.info(f"Loading config from: {path}")
                config = load_yaml(path)
                LOG.info(f"Loaded config keys: {list(config.keys())}")
                if "category_inference" in config:
                    LOG.info("Successfully loaded category_inference config")
                    return config["category_inference"]

        # Fallback to default config if no config file found
        LOG.warning(f"No config file found in any of: {CFG_PATHS}")
        LOG.warning("Using default category configuration")
        return default_config
    except Exception as e:
        LOG.error(f"Error loading category config: {str(e)}", exc_info=True)
        return default_config


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

    # Clean the merchant name first
    merchant = clean_merchant_name(
        transaction.get("merchant") or transaction.get("description", "")
    )
    description = (transaction.get("description") or "").lower()

    # Get category config
    category_config = _load_category_config()
    default_category = category_config.get("default_category", {})

    # Log the transaction being processed with cleaned merchant
    LOG.info(
        f"Processing transaction - Description: '{description}', Cleaned Merchant: '{merchant}'"
    )

    # STEP 1: Try merchant lookup first (highest confidence)
    merchant_lookup = _load_merchant_lookup()
    merchant_key = merchant.lower()
    if merchant_key in merchant_lookup:
        merchant_info = merchant_lookup[merchant_key]
        category_name = merchant_info["category"]
        subcategory_name = merchant_info.get("subcategory")
        confidence_score = merchant_info.get("confidence", 1.0)
        
        # Construct full category path if subcategory exists
        if subcategory_name and " > " not in category_name:
            category_path = f"{category_name} > {subcategory_name}"
        else:
            category_path = category_name
            
        LOG.info(
            f"Merchant lookup match: '{merchant}' → {category_path} "
            f"(confidence: {confidence_score:.2f}, occurrences: {merchant_info.get('count', 0)})"
        )

        # Try to resolve to IDs (category_path might be a full path or just a name)
        if " > " not in category_path:
            # Old format without subcategory - try to find the category
            category_ids = _resolve_category_ids(f"Food and drink > {category_path}")
            if not category_ids:
                category_ids = _resolve_category_ids(
                    f"Transportation > {category_path}"
                )
            if not category_ids:
                category_ids = _resolve_category_ids(f"Home > {category_path}")
            # Add more categories as needed
        else:
            # New format with full path
            category_ids = _resolve_category_ids(category_path)

        if category_ids:
            return {
                **category_ids,
                "confidence": f"high_{confidence_score:.2f}",
                "matched_pattern": None,
                "matched_in": "merchant_lookup",
            }
        else:
            # Fallback to name-only if ID resolution fails
            return {
                "category_id": None,
                "category_name": category_name,
                "subcategory_id": None,
                "subcategory_name": None,
                "confidence": f"high_{confidence_score:.2f}",
                "matched_pattern": None,
                "matched_in": "merchant_lookup",
            }

    # STEP 2: Try Amex category field (high confidence - from credit card statement)
    amex_category = transaction.get("amex_category") or transaction.get("category")
    if amex_category and isinstance(amex_category, str) and amex_category.strip():
        amex_category = amex_category.strip()
        amex_mapping = _load_amex_category_mapping()

        if amex_category in amex_mapping:
            category_path = amex_mapping[amex_category]
            LOG.info(f"Amex category match: '{amex_category}' → {category_path}")

            # Resolve to IDs
            category_ids = _resolve_category_ids(category_path)
            if category_ids:
                return {
                    **category_ids,
                    "confidence": "high_0.95",
                    "matched_pattern": amex_category,
                    "matched_in": "amex_category",
                }
            else:
                # Fallback if ID resolution fails
                return {
                    "category_id": None,
                    "category_name": category_path,
                    "subcategory_id": None,
                    "subcategory_name": None,
                    "confidence": "high_0.95",
                    "matched_pattern": amex_category,
                    "matched_in": "amex_category",
                }
        else:
            # Unknown Amex category - log it for future mapping
            LOG.warning(
                f"Unknown Amex category: '{amex_category}' - add to mapping file"
            )

    # STEP 3: Try regex patterns (existing logic)

    # STEP 2: Try regex patterns - check for matches in both description and merchant
    for category in category_config.get("patterns", []):
        for subcategory in category.get("subcategories", []):
            for pattern in subcategory.get("patterns", []):
                try:
                    # Compile pattern with case-insensitive flag
                    regex = re.compile(pattern, re.IGNORECASE)
                    desc_match = bool(description and regex.search(description))
                    merchant_match = bool(merchant and regex.search(merchant.lower()))

                    if desc_match or merchant_match:
                        match_type = "description" if desc_match else "merchant"
                        LOG.info(
                            f"Matched pattern '{pattern}' in {match_type} to category '{category['name']} > {subcategory['name']}'"
                        )
                        return {
                            "category_id": category["id"],
                            "category_name": category["name"],
                            "subcategory_id": subcategory["id"],
                            "subcategory_name": subcategory["name"],
                            "confidence": "high",
                            "matched_pattern": pattern,
                            "matched_in": match_type,
                        }
                except re.error as e:
                    LOG.warning(f"Invalid regex pattern '{pattern}': {e}")
                    continue

    # Log when no match is found
    LOG.info(
        f"No category match found for transaction. Description: '{description}', Cleaned Merchant: '{merchant}'"
    )

    # Return the default "Uncategorized" category
    return {
        "category_id": default_category.get("id", 2),  # Uncategorized category
        "category_name": default_category.get("name", "Uncategorized"),
        "subcategory_id": default_category.get(
            "subcategory_id", 18
        ),  # General subcategory
        "subcategory_name": default_category.get("subcategory_name", "General"),
        "confidence": "low",
        "matched_pattern": None,
        "matched_in": None,
    }
