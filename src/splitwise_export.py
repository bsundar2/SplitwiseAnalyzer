#!/usr/bin/env python3
"""Fetch Splitwise expenses for a date range and write to Google Sheets.

Adds dedupe and append support. Tracks exported Splitwise IDs and fingerprints in data/splitwise_exported.json.
"""

import argparse
import pandas as pd
from dateutil import parser as dateparser
import os

from src.sheets_sync import write_to_sheets
from src.utils import load_state, save_state_atomic, mkdir_p, compute_import_id, merchant_slug
from src.constants.gsheets import SHEETS_AUTHENTICATION_FILE

STATE_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "splitwise_exported.json")

# Constants / magic strings
DEFAULT_SPREADSHEET_NAME = "test_expenses"
DEFAULT_WORKSHEET_NAME = "Splitwise Expenses"
IMPORTED_ID_MARKER = "[ImportedID:"  # marker prefix used when creating Splitwise description markers
COL_DATE = "date"
COL_AMOUNT = "amount"
COL_DESCRIPTION = "description"
COL_FINGERPRINT = "fingerprint"
COL_ID = "id"


def parse_date(s: str):
    return dateparser.parse(s).date()


def mock_expenses(start_date, end_date):
    # Small mock DataFrame matching get_expenses_by_date_range shape
    rows = [
        {COL_DATE: start_date.isoformat(), COL_AMOUNT: "97.01", "category": "Internet", COL_DESCRIPTION: "Google Fit [Imported]", "friends_split": "Alice: 97.01", COL_ID: "mock-1"},
        {COL_DATE: end_date.isoformat(), COL_AMOUNT: "2.99", "category": "Entertainment", COL_DESCRIPTION: "Hulu [Imported]", "friends_split": "Alice: 2.99", COL_ID: "mock-2"},
    ]
    return pd.DataFrame(rows)


def load_exported_state(path=STATE_PATH):
    mkdir_p(os.path.dirname(path))
    state = load_state(path)
    exported_ids = set(state.get("exported_ids", []))
    exported_fps = set(state.get("exported_fingerprints", []))
    return exported_ids, exported_fps


def save_exported_state(exported_ids, exported_fps, path=STATE_PATH):
    mkdir_p(os.path.dirname(path))
    state = {
        "exported_ids": sorted(list(exported_ids)),
        "exported_fingerprints": sorted(list(exported_fps)),
    }
    save_state_atomic(path, state)


def _read_existing_fingerprints(sheet_key, sheet_name, worksheet_name):
    """Return a set of fingerprints computed from existing worksheet rows (if any).

    Requires `pygsheets` to be installed; ImportError will propagate if missing.
    """
    import pygsheets

    gc = pygsheets.authorize(service_file=SHEETS_AUTHENTICATION_FILE)
    if sheet_key:
        sh = gc.open_by_key(sheet_key)
    else:
        sh = gc.open(sheet_name)

    wks = sh.worksheet_by_title(worksheet_name)
    exist_df = wks.get_as_df(has_header=True)
    if exist_df is None or exist_df.empty:
        return set()

    fps = set()
    for _, r in exist_df.iterrows():
        date_val = r.get(COL_DATE) if COL_DATE in r.index else r.get(0)
        amount_val = r.get(COL_AMOUNT) if COL_AMOUNT in r.index else r.get(1)
        desc_val = r.get(COL_DESCRIPTION) if COL_DESCRIPTION in r.index else r.get("friends_split") if "friends_split" in r.index else r.get(2)
        # normalize
        try:
            from dateutil import parser as _dp
            dnorm = _dp.parse(str(date_val)).date().isoformat()
        except (ValueError, TypeError, OverflowError):
            dnorm = str(date_val)
        try:
            amt = float(amount_val)
        except (ValueError, TypeError):
            try:
                amt = float(str(amount_val).replace(',', '').replace('$', ''))
            except (ValueError, TypeError):
                amt = 0.0
        desc_norm = merchant_slug(desc_val)
        fp = compute_import_id(dnorm, amt, desc_norm)
        fps.add(fp)
    return fps


def fetch_and_write(start_date, end_date, sheet_key=None, sheet_name=None, worksheet_name=DEFAULT_WORKSHEET_NAME, mock=False, append=True, dedupe=True, show_skipped=False):
    """Fetch expenses (real or mock), de-duplicate, and write to Google Sheets.

    Returns the DataFrame written and the sheet URL (or None on failure).
    """
    df = None
    url = None
    if mock:
        df = mock_expenses(start_date, end_date)
    else:
        # Import here to avoid requiring SplitwiseClient when mocking; allow ImportError to propagate if missing
        from src.splitwise_client import SplitwiseClient
        client = SplitwiseClient()
        df = client.get_expenses_by_date_range(start_date, end_date)

    if df is None or df.empty:
        print("No Splitwise expenses found for the given range.")
        return df, None

    # Normalize columns to strings
    df = df.copy()
    for c in df.columns:
        df[c] = df[c].astype(str)

    # Compute stable fingerprint for each row using date (YYYY-MM-DD), amount, and normalized description
    fps = []
    for _, r in df.iterrows():
        date_val = r.get(COL_DATE)
        # Normalize date to YYYY-MM-DD
        try:
            from dateutil import parser as _dp
            dnorm = _dp.parse(str(date_val)).date().isoformat()
        except (ValueError, TypeError, OverflowError):
            dnorm = str(date_val)
        amount_val = r.get(COL_AMOUNT)
        desc_val = r.get(COL_DESCRIPTION) or r.get("friends_split") or ""
        # Normalize description using merchant_slug for stable matching
        desc_norm = merchant_slug(desc_val)
        # Ensure amount numeric
        try:
            amt = float(amount_val)
        except (ValueError, TypeError):
            try:
                amt = float(str(amount_val).replace(',', '').replace('$', ''))
            except (ValueError, TypeError):
                amt = 0.0
        fp = compute_import_id(dnorm, amt, desc_norm)
        fps.append(fp)
    df[COL_FINGERPRINT] = fps

    # Load existing exported state
    exported_ids, exported_fps = load_exported_state() if dedupe else (set(), set())
    # If appending to a live sheet, also read existing fingerprints from that worksheet to handle
    # cases where the local state file is missing or inconsistent.
    if dedupe and (sheet_key or sheet_name):
        sheet_existing_fps = _read_existing_fingerprints(sheet_key, sheet_name, worksheet_name)
        if sheet_existing_fps:
            exported_fps = set(exported_fps) | set(sheet_existing_fps)
            # Persist the discovered fingerprints so future runs don't recompute them each time
            save_exported_state(exported_ids, exported_fps)

    # Filter new rows: not in exported ids and not in exported fingerprints
    if dedupe:
        mask_new = ~((df[COL_ID].isin(exported_ids)) | (df[COL_FINGERPRINT].isin(exported_fps)))
        new_df = df[mask_new].reset_index(drop=True)
        skipped_df = df[~mask_new].reset_index(drop=True)
    else:
        new_df = df
        skipped_df = pd.DataFrame()

    if show_skipped and not skipped_df.empty:
        # annotate skip reason
        reasons = []
        for _, r in skipped_df.iterrows():
            rid = r.get(COL_ID)
            fp = r.get(COL_FINGERPRINT)
            reason_parts = []
            if rid in exported_ids:
                reason_parts.append("id")
            if fp in exported_fps:
                reason_parts.append("fingerprint")
            reasons.append(" & ".join(reason_parts) if reason_parts else "unknown")
        skipped_df = skipped_df.copy()
        skipped_df["skip_reason"] = reasons
        print(f"Skipped {len(skipped_df)} rows (dedupe). Showing up to 20:")
        print(skipped_df.head(20).to_string())

    if new_df.empty:
        print("No new Splitwise expenses to export (all rows already exported).")
        return new_df, None

    # Coerce types for better Sheets formatting: date -> datetime objects, amount -> numeric
    if COL_DATE in new_df.columns:
        # parse and format as 'YYYY-MM-DD' (date-only) strings so Google Sheets will parse them as dates
        parsed = pd.to_datetime(new_df[COL_DATE], errors="coerce", utc=True)
        # Format where parse succeeded; otherwise leave the original string
        new_df[COL_DATE] = parsed.dt.strftime('%Y-%m-%d').where(parsed.notna(), new_df[COL_DATE])

    if COL_AMOUNT in new_df.columns:
        new_df[COL_AMOUNT] = pd.to_numeric(new_df[COL_AMOUNT], errors="coerce")

    # Write to sheets
    if sheet_key or sheet_name:
        url = write_to_sheets(new_df, worksheet_name=worksheet_name, spreadsheet_name=sheet_name or DEFAULT_SPREADSHEET_NAME, spreadsheet_key=sheet_key, append=append)
    else:
        print(new_df.head())

    # Update exported state
    updated_ids = set(exported_ids) | set(new_df[COL_ID].tolist())
    updated_fps = set(exported_fps) | set(new_df[COL_FINGERPRINT].tolist())
    save_exported_state(updated_ids, updated_fps)

    return new_df, url


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch Splitwise expenses and write to Google Sheets")
    parser.add_argument("--start-date", required=True, help="Start date (YYYY-MM-DD) or any parseable date")
    parser.add_argument("--end-date", required=True, help="End date (YYYY-MM-DD) or any parseable date")
    parser.add_argument("--sheet-key", default=None, help="Spreadsheet key to write to (preferred)")
    parser.add_argument("--sheet-name", default=None, help="Spreadsheet name to write to (fallback)")
    parser.add_argument("--worksheet-name", default=DEFAULT_WORKSHEET_NAME, help="Worksheet/tab name to write into")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite the entire worksheet and skip dedupe (default is append)")
    parser.add_argument("--no-dedupe", action="store_true", help="Do not deduplicate; export all rows")
    parser.add_argument("--show-skipped", action="store_true", help="Show rows that were skipped due to dedupe and reasons")
    parser.add_argument("--mock", action="store_true", help="Use mock data instead of calling Splitwise (for testing)")

    args = parser.parse_args()

    sd = parse_date(args.start_date)
    ed = parse_date(args.end_date)

    # Decide append/dedupe behavior: default is append; explicit --overwrite will force overwrite and disable dedupe
    append_flag = not args.overwrite
    dedupe_flag = not args.no_dedupe
    if args.overwrite:
        # When overwriting we skip dedupe checks entirely
        dedupe_flag = False

    new_df, url = fetch_and_write(sd, ed, sheet_key=args.sheet_key, sheet_name=args.sheet_name, worksheet_name=args.worksheet_name, mock=args.mock, append=append_flag, dedupe=dedupe_flag, show_skipped=args.show_skipped)
    if new_df is not None:
        print(f"Exported {len(new_df)} rows")
    if url:
        print(url)
