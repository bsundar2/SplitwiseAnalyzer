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
from src.common.utils import LOG, load_yaml, parse_date_safe

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

    # Store original row count for logging
    original_count = len(df)

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
        if "reference" in low or low == "ref" or "detail" in low:
            col_map["detail"] = c
        if "category" in low or "type" in low:
            col_map["category"] = c

    if "date" not in col_map or "description" not in col_map or "amount" not in col_map:
        # fallback: try first three columns
        col_names = list(df.columns)
        col_map["date"] = col_names[0]
        col_map["description"] = col_names[1]
        col_map["amount"] = col_names[2]

    # Create output dataframe with basic columns
    out = pd.DataFrame()
    out["date"] = df[col_map["date"]].apply(parse_date_safe)
    out["description"] = df[col_map["description"]].astype(str).str.strip()
    # Don't take absolute value yet - we need to filter credits first
    out["amount"] = df[col_map["amount"]].apply(parse_amount_safe)

    # Add category column if it exists in the input
    if "category" in col_map:
        out["category"] = df[col_map["category"]].astype(str).str.strip()
    else:
        out["category"] = None

    if "detail" in col_map:
        out["detail"] = df[col_map["detail"]].astype(str).str.strip()

    out["raw_line"] = df.apply(
        lambda r: " | ".join([str(r[c]) for c in df.columns]), axis=1
    )

    # Filter out rows with null dates
    out = out.dropna(subset=["date"])

    # [TEMP] Transaction filtering - can be removed after verification
    LOG.info("[TEMP] Starting transaction filtering...")

    # Filter out transactions with null categories (if category column exists)
    if "category" in out.columns:
        before_filter = len(out)
        out = out[~out["category"].isin(["None", "null", "", None, "nan"])]
        null_filtered = before_filter - len(out)
        if null_filtered > 0:
            LOG.info(
                "[TEMP] Filtered out %d transactions with null/empty categories",
                null_filtered,
            )

    # Filter out transactions containing "Fees & Adjustments" in description
    before_fee_filter = len(out)
    fee_filter = out["description"].str.contains(
        "Fees & Adjustments", case=False, na=False
    )
    out = out[~fee_filter]
    fee_filtered = before_fee_filter - len(out)
    if fee_filtered > 0:
        LOG.info(
            "[TEMP] Filtered out %d transactions containing 'Fees & Adjustments' in description",
            fee_filtered,
        )
        # Log sample of filtered transactions
        filtered = out[fee_filter].head(3)
        if not filtered.empty:
            LOG.info("[TEMP] Sample of filtered 'Fees & Adjustments' transactions:")
            for _, row in filtered.iterrows():
                LOG.info(
                    "  [TEMP] %s - %s - $%.2f",
                    row["date"],
                    (
                        (row["description"][:50] + "...")
                        if len(row["description"]) > 50
                        else row["description"]
                    ),
                    row["amount"],
                )

    # Filter out credits (negative amounts) - MUST be done before taking absolute value
    before_credit_filter = len(out)
    credit_filter = out["amount"] < 0
    filtered_credits = out[credit_filter].copy()
    out = out[~credit_filter]
    credit_filtered = before_credit_filter - len(out)
    if credit_filtered > 0:
        LOG.info(
            "[TEMP] Filtered out %d credit transactions (amount < 0)", credit_filtered
        )
        # Log sample of filtered credit transactions
        if not filtered_credits.empty:
            LOG.info("[TEMP] Sample of filtered credit transactions:")
            for _, row in filtered_credits.head(5).iterrows():
                LOG.info(
                    "  [TEMP] %s - %s - $%.2f",
                    row["date"],
                    (
                        (row["description"][:50] + "...")
                        if len(row["description"]) > 50
                        else row["description"]
                    ),
                    row["amount"],
                )
    
    # Now take absolute value of remaining amounts (in case there are any edge cases)
    out["amount"] = out["amount"].abs()

    # Filter out payment/autopay transactions
    payment_patterns = [
        r'\bAUTOPAY\b',
        r'\bPAYMENT\s*-\s*THANK\s*YOU\b',
        r'\bAmex\s+Offer\s+Credit\b',
        r'^\s*Credit\s*$',  # Standalone "Credit"
        r'\b(?:Entertainment|Digital|Platinum)\s+Credit\b',
        r'\bREIMBURSEMENT\b',
        r'\bPOINTS\s+FOR\s+AMEX\b',
    ]
    
    before_payment_filter = len(out)
    # Combine patterns with non-capturing groups to avoid warning
    combined_pattern = '|'.join(f'(?:{p})' for p in payment_patterns)
    payment_filter = out["description"].str.contains(
        combined_pattern, case=False, na=False, regex=True
    )
    filtered_payments = out[payment_filter]
    out = out[~payment_filter]
    payment_filtered = before_payment_filter - len(out)
    
    if payment_filtered > 0:
        LOG.info(
            "[TEMP] Filtered out %d payment/credit/reimbursement transactions",
            payment_filtered
        )
        # Log sample of filtered payment transactions
        if not filtered_payments.empty:
            LOG.info("[TEMP] Sample of filtered payment/credit transactions:")
            for _, row in filtered_payments.head(5).iterrows():
                LOG.info(
                    "  [TEMP] %s - %s - $%.2f",
                    row["date"],
                    (
                        (row["description"][:50] + "...")
                        if len(row["description"]) > 50
                        else row["description"]
                    ),
                    row["amount"],
                )

    # Log final filtering summary
    filtered_count = original_count - len(out)
    if filtered_count > 0:
        LOG.info(
            "[TEMP] Filtered out %d of %d total transactions (%.1f%%)",
            filtered_count,
            original_count,
            (filtered_count / original_count) * 100,
        )

    # Log a sample of transactions that made it through filtering
    if not out.empty:
        LOG.info("[TEMP] Sample of transactions after filtering (first 3):")
        for _, row in out.head(3).iterrows():
            LOG.info(
                "  [TEMP] %s - %s - $%.2f",
                row["date"],
                (
                    (row["description"][:50] + "...")
                    if len(row["description"]) > 50
                    else row["description"]
                ),
                row["amount"],
            )

    LOG.info("[TEMP] Transaction filtering complete")

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
