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

from src.constants.config import CFG_PATHS
from src.utils import LOG, load_yaml, parse_date_safe

# Load configuration
CFG = None
for p in CFG_PATHS:
    if p.exists():
        try:
            CFG = load_yaml(p)
            break
        except (OSError, ValueError) as e:
            LOG.exception("Failed to load config %s: %s", p, e)
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
        if "reference" in low or low == "ref":
            col_map["reference"] = c

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
    if "reference" in col_map:
        out["reference"] = df[col_map["reference"]].astype(str).str.strip()
    out["raw_line"] = df.apply(lambda r: " | ".join([str(r[c]) for c in df.columns]), axis=1)
    out = out.dropna(subset=["date"])
    return out


def parse_any(path):
    ext = os.path.splitext(path)[1].lower()
    if ext in [".csv", ".txt"]:
        return parse_csv(path)
    else:
        raise ValueError("Unsupported extension: " + ext)


def parse_statement(path):
    return parse_any(path)


def parse_amount_safe(s):
    if pd.isna(s):
        return 0.0
    s = str(s).strip()
    s = s.replace("$", "").replace(",", "")
    try:
        return float(s)
    except ValueError:
        # handle parentheses as negative
        if "(" in s and ")" in s:
            s2 = s.replace("(", "").replace(")", "")
            try:
                return -float(s2)
            except ValueError:
                raise
        raise
