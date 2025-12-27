#!/usr/bin/env python3
"""Fetch Splitwise expenses for a date range and write to Google Sheets.

Adds dedupe and append support. Tracks exported Splitwise IDs and fingerprints in data/splitwise_exported.json.
"""

import argparse
from datetime import datetime
import pandas as pd
from dateutil import parser as dateparser
import os

from src.sheets_sync import write_to_sheets
from src.utils import load_state, save_state_atomic, mkdir_p, compute_import_id, merchant_slug
from src.constants.gsheets import SHEETS_AUTHENTICATION_FILE

STATE_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "splitwise_exported.json")


def parse_date(s: str):
    return dateparser.parse(s).date()


def mock_expenses(start_date, end_date):
    # Small mock DataFrame matching get_expenses_by_date_range shape
    rows = [
        {"date": start_date.isoformat(), "amount": "97.01", "category": "Internet", "description": "Google Fit [Imported]", "friends_split": "Alice: 97.01", "id": "mock-1"},
        {"date": end_date.isoformat(), "amount": "2.99", "category": "Entertainment", "description": "Hulu [Imported]", "friends_split": "Alice: 2.99", "id": "mock-2"},
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
    """Return a set of fingerprints computed from existing worksheet rows (if any)."""
    try:
        import pygsheets
    except Exception:
        return set()
    try:
        gc = pygsheets.authorize(service_file=SHEETS_AUTHENTICATION_FILE)
        if sheet_key:
            sh = gc.open_by_key(sheet_key)
        else:
            sh = gc.open(sheet_name)
        try:
            wks = sh.worksheet_by_title(worksheet_name)
        except Exception:
            return set()
        try:
            exist_df = wks.get_as_df(has_header=True)
        except Exception:
            return set()
        if exist_df is None or exist_df.empty:
            return set()
        fps = set()
        for _, r in exist_df.iterrows():
            date_val = r.get("date") if "date" in r.index else r.get(0)
            amount_val = r.get("amount") if "amount" in r.index else r.get(1)
            desc_val = r.get("description") if "description" in r.index else r.get("friends_split") if "friends_split" in r.index else r.get(2)
            # normalize
            try:
                from dateutil import parser as _dp
                dnorm = _dp.parse(str(date_val)).date().isoformat()
            except Exception:
                dnorm = str(date_val)
            try:
                amt = float(amount_val)
            except Exception:
                try:
                    amt = float(str(amount_val).replace(',', '').replace('$', ''))
                except Exception:
                    amt = 0.0
            desc_norm = merchant_slug(desc_val)
            fp = compute_import_id(dnorm, amt, desc_norm)
            fps.add(fp)
        return fps
    except Exception:
        return set()


def fetch_and_write(start_date, end_date, sheet_key=None, sheet_name=None, worksheet_name="Splitwise Expenses", mock=False, append=False, dedupe=True):
    """Fetch expenses (real or mock), de-duplicate, and write to Google Sheets.

    Returns the DataFrame written and the sheet URL (or None on failure).
    """
    df = None
    url = None
    if mock:
        df = mock_expenses(start_date, end_date)
    else:
        try:
            # Import here to avoid requiring SplitwiseClient when mocking
            from src.splitwise_client import SplitwiseClient
            client = SplitwiseClient()
            df = client.get_expenses_by_date_range(start_date, end_date)
        except Exception as e:
            raise RuntimeError(f"Failed to fetch from Splitwise: {e}")

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
        date_val = r.get("date")
        # Normalize date to YYYY-MM-DD
        try:
            from dateutil import parser as _dp
            dnorm = _dp.parse(str(date_val)).date().isoformat()
        except Exception:
            dnorm = str(date_val)
        amount_val = r.get("amount")
        desc_val = r.get("description") or r.get("friends_split") or ""
        # Normalize description using merchant_slug for stable matching
        desc_norm = merchant_slug(desc_val)
        # Ensure amount numeric
        try:
            amt = float(amount_val)
        except Exception:
            try:
                amt = float(str(amount_val).replace(',', '').replace('$', ''))
            except Exception:
                amt = 0.0
        fp = compute_import_id(dnorm, amt, desc_norm)
        fps.append(fp)
    df["fingerprint"] = fps

    # Load existing exported state
    exported_ids, exported_fps = load_exported_state() if dedupe else (set(), set())
    # If appending to a live sheet, also read existing fingerprints from that worksheet to handle
    # cases where the local state file is missing or inconsistent.
    if dedupe and (sheet_key or sheet_name):
        sheet_existing_fps = _read_existing_fingerprints(sheet_key, sheet_name, worksheet_name)
        if sheet_existing_fps:
            exported_fps = set(exported_fps) | set(sheet_existing_fps)
            # Persist the discovered fingerprints so future runs don't recompute them each time
            try:
                save_exported_state(exported_ids, exported_fps)
            except Exception:
                pass

    # Filter new rows: not in exported ids and not in exported fingerprints
    if dedupe:
        mask_new = ~((df["id"].isin(exported_ids)) | (df["fingerprint"].isin(exported_fps)))
        new_df = df[mask_new].reset_index(drop=True)
    else:
        new_df = df

    if new_df.empty:
        print("No new Splitwise expenses to export (all rows already exported).")
        return new_df, None

    # Write to sheets
    if sheet_key or sheet_name:
        try:
            url = write_to_sheets(new_df, worksheet_name=worksheet_name, spreadsheet_name=sheet_name or "Splitwise Expenses", spreadsheet_key=sheet_key, append=append)
            print("Wrote Splitwise expenses to:", url)
        except Exception as e:
            print("Failed to write to Google Sheets:", str(e))
            raise
    else:
        print(new_df.head())

    # Update exported state
    updated_ids = set(exported_ids) | set(new_df["id"].tolist())
    updated_fps = set(exported_fps) | set(new_df["fingerprint"].tolist())
    save_exported_state(updated_ids, updated_fps)

    return new_df, url


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch Splitwise expenses and write to Google Sheets")
    parser.add_argument("--start-date", required=True, help="Start date (YYYY-MM-DD) or any parseable date")
    parser.add_argument("--end-date", required=True, help="End date (YYYY-MM-DD) or any parseable date")
    parser.add_argument("--sheet-key", default=None, help="Spreadsheet key to write to (preferred)")
    parser.add_argument("--sheet-name", default=None, help="Spreadsheet name to write to (fallback)")
    parser.add_argument("--worksheet-name", default="Splitwise Expenses", help="Worksheet/tab name to write into")
    parser.add_argument("--append", action="store_true", help="Append to existing worksheet instead of overwriting")
    parser.add_argument("--no-dedupe", action="store_true", help="Do not deduplicate; export all rows")
    parser.add_argument("--mock", action="store_true", help="Use mock data instead of calling Splitwise (for testing)")

    args = parser.parse_args()

    sd = parse_date(args.start_date)
    ed = parse_date(args.end_date)

    new_df, url = fetch_and_write(sd, ed, sheet_key=args.sheet_key, sheet_name=args.sheet_name, worksheet_name=args.worksheet_name, mock=args.mock, append=args.append, dedupe=not args.no_dedupe)
    if new_df is not None:
        print(f"Exported {len(new_df)} rows")
    if url:
        print(url)
