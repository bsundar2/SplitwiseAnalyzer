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
        # Match "Description" column specifically (not "Extended Details")
        if low == "description" or "merchant" in low:
            col_map["description"] = c
        if "amount" in low or "debit" in low or "credit" in low:
            col_map["amount"] = c
        # Match "Extended Details" or "Reference" for detail field
        if "extended" in low or "reference" in low or low == "ref":
            col_map["detail"] = c
        if low == "category" or low == "type":
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

    # Extract cc_reference_id from detail/reference column if available
    if "detail" in col_map:
        out["detail"] = df[col_map["detail"]].astype(str).str.strip()
        out["cc_reference_id"] = out["detail"].apply(extract_reference_id)
    else:
        out["cc_reference_id"] = None

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

    # Identify credits (negative amounts) but keep them instead of filtering
    # Credits will be handled differently in the pipeline (reversed split)
    out["is_credit"] = out["amount"] < 0
    
    # Identify refunds specifically (credits with refund/credit keywords, excluding payments)
    def is_likely_refund(row):
        """Check if transaction is likely a refund based on description."""
        if not row["is_credit"]:
            return False
        
        # Combine description and merchant for pattern matching
        combined_text = f"{row['description']} {out.loc[row.name, 'category'] if 'category' in out.columns else ''}".lower()
        
        # Exclude payment patterns
        payment_keywords = ['payment', 'autopay', 'thank you', 'settle']
        if any(kw in combined_text for kw in payment_keywords):
            return False
        
        # Look for refund indicators
        refund_keywords = ['refund', 'credit', 'return', 'reversal', 'chargeback']
        return any(kw in combined_text for kw in refund_keywords)
    
    out["is_refund"] = out.apply(is_likely_refund, axis=1)
    
    credits_count = out["is_credit"].sum()
    refunds_count = out["is_refund"].sum()
    
    if credits_count > 0:
        LOG.info(
            "Found %d credit transactions (amount < 0): %d refunds, %d other credits (payments)",
            credits_count,
            refunds_count,
            credits_count - refunds_count,
        )

    # Take absolute value of amounts (credits will be positive in Splitwise)
    out["amount"] = out["amount"].abs()

    # Filter out payment/autopay transactions only (not credits/refunds)
    payment_patterns = [
        r"\bAUTOPAY\b",
        r"\bPAYMENT\s*-\s*THANK\s*YOU\b",
        r"\bPOINTS\s+FOR\s+AMEX\b",
    ]

    before_payment_filter = len(out)
    # Combine patterns with non-capturing groups to avoid warning
    combined_pattern = "|".join(f"(?:{p})" for p in payment_patterns)
    payment_filter = out["description"].str.contains(
        combined_pattern, case=False, na=False, regex=True
    )
    filtered_payments = out[payment_filter]
    out = out[~payment_filter]
    payment_filtered = before_payment_filter - len(out)

    if payment_filtered > 0:
        LOG.info(
            "[TEMP] Filtered out %d payment/credit/reimbursement transactions",
            payment_filtered,
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


def extract_reference_id(detail_str):
    """Extract credit card reference/transaction ID from detail field.
    
    Handles various formats:
    - Pure numeric IDs (e.g., "123456789")
    - Alphanumeric IDs (e.g., "TXN123ABC456")
    - IDs with prefixes (e.g., "REF: 123456789")
    
    Returns:
        Cleaned reference ID string or None if not found/invalid
    """
    if pd.isna(detail_str) or detail_str in ["None", "null", "", "nan"]:
        return None
    
    detail_str = str(detail_str).strip()
    
    # Skip empty or placeholder values
    if not detail_str or detail_str.lower() in ["none", "null", "nan", "n/a"]:
        return None
    
    # Remove common prefixes
    for prefix in ["REF:", "REFERENCE:", "TXN:", "TRANS:", "ID:"]:
        if detail_str.upper().startswith(prefix):
            detail_str = detail_str[len(prefix):].strip()
    
    # Clean and validate (keep alphanumeric only)
    ref_id = "".join(c for c in detail_str if c.isalnum())
    
    # Must have at least 8 characters to be a valid reference
    if len(ref_id) >= 8:
        return ref_id
    
    return None
