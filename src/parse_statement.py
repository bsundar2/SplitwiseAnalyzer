# scripts/parse_statement.py
"""
Parse CSV or PDF statements into a pandas DataFrame with columns:
  - date (YYYY-MM-DD)
  - description (string)
  - amount (positive float)
  - raw_line (string)
"""

import os
import pandas as pd
from dateutil import parser as dateparser
from utils import LOG, mkdir_p, load_yaml

# Robust config loading: try repo root config.yaml or config/config.yaml
BASE_DIR = os.path.dirname(os.path.dirname(__file__))
CFG_PATHS = [
    os.path.join(BASE_DIR, "config.yaml"),
    os.path.join(BASE_DIR, "config", "config.yaml"),
]
CFG = None
for p in CFG_PATHS:
    if os.path.exists(p):
        try:
            CFG = load_yaml(p)
            break
        except Exception:
            CFG = None
            break


def parse_csv(path):
    LOG.info("Parsing CSV: %s", path)
    df = pd.read_csv(path, dtype=str)
    # Try to find common columns
    col_map = {}
    for c in df.columns:
        low = c.lower()
        if "date" in low:
            col_map["date"] = c
        if "description" in low or "merchant" in low or "detail" in low:
            col_map["description"] = c
        if "amount" in low or "debit" in low or "credit" in low:
            col_map["amount"] = c

    if "date" not in col_map or "description" not in col_map or "amount" not in col_map:
        # fallback: try first three columns
        col_names = list(df.columns)
        col_map["date"] = col_names[0]
        col_map["description"] = col_names[1]
        col_map["amount"] = col_names[2]

    out = pd.DataFrame()
    out["date"] = df[col_map["date"]].apply(parse_date_safe)
    out["description"] = df[col_map["description"]].astype(str).str.strip()
    out["amount"] = df[col_map["amount"]].apply(parse_amount_safe).abs()
    out["raw_line"] = df.apply(lambda r: " | ".join([str(r[c]) for c in df.columns]), axis=1)
    out = out.dropna(subset=["date"])
    return out


def parse_any(path):
    ext = os.path.splitext(path)[1].lower()
    if ext in [".csv", ".txt"]:
        return parse_csv(path)
    else:
        raise ValueError("Unsupported extension: " + ext)

def parse_date_safe(s):
    if pd.isna(s):
        return None
    s = str(s).strip()
    try:
        dt = dateparser.parse(s, dayfirst=False)
        return dt.date().isoformat()
    except Exception:
        # Try adding year if not present
        try:
            dt = dateparser.parse(s + " 2025")
            return dt.date().isoformat()
        except Exception:
            return None

def parse_amount_safe(s):
    if pd.isna(s):
        return 0.0
    s = str(s).strip()
    s = s.replace("$", "").replace(",", "")
    try:
        return float(s)
    except Exception:
        # handle parentheses as negative
        if "(" in s and ")" in s:
            s2 = s.replace("(", "").replace(")", "")
            return -float(s2)
        raise
