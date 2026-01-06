#!/usr/bin/env python3
"""Fetch Splitwise expenses for a date range and write to Google Sheets.

Adds dedupe and append support. Tracks exported Splitwise IDs and fingerprints in data/splitwise_exported.json.
"""
# Standard library
import argparse
import json
import os
from datetime import datetime, date
from typing import List, Optional, Union

# Third-party
import pandas as pd
from dotenv import load_dotenv

# Load environment variables
load_dotenv("config/.env")

# Local application
from src.constants.config import STATE_PATH
from src.constants.gsheets import DEFAULT_WORKSHEET_NAME
from src.common.sheets_sync import write_to_sheets, read_from_sheets
from src.common.splitwise_client import SplitwiseClient
from src.common.utils import (
    load_state,
    save_state_atomic,
    compute_import_id,
    merchant_slug,
    LOG,
    generate_fingerprint,
    parse_date,
)
from src.constants.splitwise import ExcludedSplitwiseDescriptions
from src.constants.export_columns import ExportColumns


def load_exported_state() -> tuple[set, set]:
    """Load the set of previously exported Splitwise expense IDs and fingerprints.

    Returns:
        A tuple of (exported_ids, exported_fingerprints) as sets
    """
    try:
        state = load_state(STATE_PATH)
        return set(state.get("exported_ids", [])), set(
            state.get("exported_fingerprints", [])
        )
    except (FileNotFoundError, json.JSONDecodeError):
        return set(), set()


def save_exported_state(exported_ids: set, exported_fps: set) -> None:
    """Save the set of exported Splitwise expense IDs and fingerprints.

    Args:
        exported_ids: Set of exported expense IDs
        exported_fps: Set of exported fingerprints
    """
    state = {
        "exported_ids": list(exported_ids),
        "exported_fingerprints": list(exported_fps),
        "last_updated": datetime.now().isoformat(),
    }
    save_state_atomic(STATE_PATH, state)


def _read_existing_fingerprints(
    sheet_key: Optional[str] = None,
    worksheet_name: Optional[str] = None,
) -> Optional[List[str]]:
    """Read existing fingerprints from a Google Sheet.

    Args:
        sheet_key: Google Sheet key/ID
        worksheet_name: Name of the worksheet to read from

    Returns:
        List of fingerprints or None if the sheet couldn't be read
    """
    if not sheet_key or not worksheet_name:
        return None

    df = read_from_sheets(sheet_key, worksheet_name, numerize=False)
    if df is None or ExportColumns.FINGERPRINT not in df.columns:
        return None

    # Return non-empty fingerprints
    return [fp for fp in df[ExportColumns.FINGERPRINT].dropna() if fp]


def export_categories(sheet_key: str = None) -> Optional[str]:
    """Export all Splitwise categories to a 'Splitwise Categories' worksheet.

    Args:
        sheet_key: Google Sheet key/ID

    Returns:
        URL of the updated sheet or None if no categories found
    """
    client = SplitwiseClient()
    categories = client.get_categories()

    # Create a dictionary to hold categories and their subcategories
    category_dict = {}
    for category in categories:
        category_name = category.getName()
        subcategories = []
        if hasattr(category, "getSubcategories"):
            subcategories = [subcat.getName() for subcat in category.getSubcategories()]
        category_dict[category_name] = subcategories

    if not category_dict:
        LOG.warning("No categories found to export")
        return None

    # Find the maximum number of subcategories for any category
    max_subs = max(len(subs) for subs in category_dict.values())

    # Create a list of dictionaries for the DataFrame
    data = []
    for i in range(max_subs):
        row = {}
        for category, subcategories in category_dict.items():
            # Get the subcategory at index i, or empty string if none
            row[category] = subcategories[i] if i < len(subcategories) else ""
        data.append(row)

    # Create DataFrame from the list of dictionaries
    df = pd.DataFrame(data)

    # Reorder columns to match the original category order
    df = df[list(category_dict.keys())]

    # Write to Google Sheets
    url = write_to_sheets(
        df,
        worksheet_name="Splitwise Categories",
        spreadsheet_key=sheet_key,
        append=False,  # Always overwrite the categories sheet
    )
    LOG.info("Exported %d categories to Google Sheets", len(category_dict))
    return url


def fetch_and_write(
    start_date: Union[datetime, date, str],
    end_date: Union[datetime, date, str],
    sheet_key: Optional[str] = None,
    worksheet_name: str = DEFAULT_WORKSHEET_NAME,
    append: bool = True,
    export_categories_flag: bool = False,
) -> tuple[pd.DataFrame, Optional[str]]:
    """Fetch expenses, de-duplicate, and write to Google Sheets.

    Deduplication is always enabled. The function will fetch Splitwise
    expenses for the given date range, remove known exported IDs/fingerprints,
    and write the new rows to Google Sheets (or return them when no sheet is
    provided).

    Returns:
        Tuple of (DataFrame with expenses, URL of the updated sheet or None)
    """

    client = SplitwiseClient()
    df = client.get_my_expenses_by_date_range(start_date, end_date)

    # Filter out Splitwise-generated "Settle all balances" rows which are not useful for budgeting.
    # Match the exact phrase (case-insensitive, trimmed) instead of a fuzzy regex.
    if df is not None and not df.empty and ExportColumns.DESCRIPTION in df.columns:
        # explicit exact-match checks using pandas Series.eq for clarity
        settle_mask = (
            df[ExportColumns.DESCRIPTION]
            .astype(str)
            .str.strip()
            .str.lower()
            .eq(ExcludedSplitwiseDescriptions.SETTLE_ALL_BALANCES.value.lower())
        )

        num_settle = int(settle_mask.sum())
        if num_settle > 0:
            LOG.info(
                "Filtered out %d Splitwise 'Settle all balances' exact-match transactions from API export",
                num_settle,
            )
            df = df[~settle_mask].reset_index(drop=True)

        # Also filter out explicit 'Payment' rows (these are payments/settlements, not expenses).
        # Only target the description field; if a `category` column exists require it to be 'General'
        # to avoid removing other rows accidentally.
        desc_series = df[ExportColumns.DESCRIPTION].astype(str).str.strip()
        payment_exact = desc_series.str.lower().eq(
            ExcludedSplitwiseDescriptions.PAYMENT.value.lower()
        )
        payment_word = desc_series.str.contains(r"\bpayment\b", case=False, na=False)

        if ExportColumns.CATEGORY in df.columns:
            category_general = (
                df[ExportColumns.CATEGORY].astype(str).str.strip().eq("General")
            )
        else:
            category_general = pd.Series(True, index=df.index)

        payment_mask = (payment_exact | payment_word) & category_general
        num_pay = int(payment_mask.sum())
        if num_pay > 0:
            LOG.info(
                "Filtered out %d Splitwise 'Payment' transactions from API export",
                num_pay,
            )
            df = df[~payment_mask].reset_index(drop=True)
    if df is None or df.empty:
        LOG.info("No expenses found for the date range %s to %s", start_date, end_date)
        return pd.DataFrame(), None

    is_overwrite = not append

    # Ensure all columns are strings for consistency
    df = df.copy()
    for col in df.columns:
        df[col] = df[col].astype(str)

    # Generate fingerprints using the utility function
    df[ExportColumns.FINGERPRINT] = df.apply(
        lambda r: generate_fingerprint(
            r.get(ExportColumns.DATE),
            r.get(ExportColumns.AMOUNT),
            r.get(ExportColumns.DESCRIPTION) or r.get(ExportColumns.FRIENDS_SPLIT, ""),
        ),
        axis=1,
    )

    # In overwrite mode, we want a full refresh of the worksheet.
    # That means we should not filter anything out based on prior exported state.
    if is_overwrite:
        exported_ids, exported_fps = set(), set()
    else:
        # Always load existing exported state when not overwriting
        exported_ids, exported_fps = load_exported_state()
        # If appending to a live sheet, also read existing fingerprints from that worksheet to handle
        # cases where the local state file is missing or inconsistent.
        if sheet_key:
            sheet_existing_fps = _read_existing_fingerprints(sheet_key, worksheet_name)
            if sheet_existing_fps:
                exported_fps = set(exported_fps) | set(sheet_existing_fps)
                # Persist the discovered fingerprints so future runs don't recompute them each time
                save_exported_state(exported_ids, exported_fps)

    # Filter new rows: not in exported ids and not in exported fingerprints
    if not is_overwrite:
        mask_new = ~(
            (df[ExportColumns.ID].isin(exported_ids))
            | (df[ExportColumns.FINGERPRINT].isin(exported_fps))
        )
        new_df = df[mask_new].reset_index(drop=True)
        skipped_df = df[~mask_new].reset_index(drop=True)
    else:
        new_df = df
        skipped_df = pd.DataFrame()

    # Convert my_paid/my_owed to numeric and filter out expenses where the
    # user has no participation (both my_paid and my_owed are zero).
    # This prevents exporting rows where the current user is not involved.
    if (
        not new_df.empty
        and ExportColumns.MY_PAID in new_df.columns
        and ExportColumns.MY_OWED in new_df.columns
    ):
        # Coerce to numeric (invalid -> 0.0) then filter
        new_df = new_df.copy()
        new_df[ExportColumns.MY_PAID] = pd.to_numeric(
            new_df[ExportColumns.MY_PAID], errors="coerce"
        ).fillna(0.0)
        new_df[ExportColumns.MY_OWED] = pd.to_numeric(
            new_df[ExportColumns.MY_OWED], errors="coerce"
        ).fillna(0.0)

        before_count = len(new_df)
        # Keep rows where either my_paid or my_owed is non-zero
        participation_mask = (new_df[ExportColumns.MY_PAID] != 0.0) | (
            new_df[ExportColumns.MY_OWED] != 0.0
        )
        new_df = new_df[participation_mask].reset_index(drop=True)
        filtered_count = before_count - len(new_df)
        if filtered_count > 0:
            LOG.info(
                "Filtered out %d expenses where my_paid and my_owed were both zero (no participation)",
                filtered_count,
            )

    if new_df.empty:
        print(
            "No new Splitwise expenses to export (all rows already exported or no participation)."
        )
        return new_df, None

    # Coerce types for better Sheets formatting: date -> datetime objects, amount -> numeric
    if ExportColumns.DATE in new_df.columns:
        # parse and format as 'YYYY-MM-DD' (date-only) strings so Google Sheets will parse them as dates
        # Don't use utc=True to avoid timezone shifts - Splitwise dates are already in the correct format
        parsed = pd.to_datetime(new_df[ExportColumns.DATE], errors="coerce")
        # Format where parse succeeded; otherwise leave the original string
        new_df[ExportColumns.DATE] = parsed.dt.strftime("%Y-%m-%d").where(
            parsed.notna(), new_df[ExportColumns.DATE]
        )

    if ExportColumns.AMOUNT in new_df.columns:
        new_df[ExportColumns.AMOUNT] = pd.to_numeric(
            new_df[ExportColumns.AMOUNT], errors="coerce"
        )

    # Write to sheets
    if sheet_key:
        url = write_to_sheets(
            new_df,
            worksheet_name=worksheet_name,
            spreadsheet_key=sheet_key,
            append=append,
        )
    else:
        url = None
        print(new_df.head())

    # Update exported state
    if is_overwrite:
        updated_ids = set(new_df[ExportColumns.ID].tolist())
        updated_fps = set(new_df[ExportColumns.FINGERPRINT].tolist())
    else:
        updated_ids = set(exported_ids) | set(new_df[ExportColumns.ID].tolist())
        updated_fps = set(exported_fps) | set(
            new_df[ExportColumns.FINGERPRINT].tolist()
        )
    save_exported_state(updated_ids, updated_fps)

    # Export categories only when explicitly requested via flag
    if not append and export_categories_flag:
        LOG.info("Exporting categories due to --export-categories flag")
        export_categories(sheet_key=sheet_key)

    return new_df, url


def main():
    """Main entry point for the script."""
    parser = argparse.ArgumentParser(
        description="Export Splitwise expenses to Google Sheets"
    )
    parser.add_argument(
        "--start-date",
        default=os.getenv("START_DATE"),
        help="Start date (any parseable date string, e.g., '2023-01-01' or '3 months ago'). Defaults to START_DATE env var.",
    )
    parser.add_argument(
        "--end-date",
        default=os.getenv("END_DATE"),
        help="End date (any parseable date string, e.g., '2023-12-31' or 'today'). Defaults to END_DATE env var.",
    )
    parser.add_argument(
        "--worksheet-name",
        default=os.getenv("EXPENSES_WORKSHEET_NAME", DEFAULT_WORKSHEET_NAME),
        help=f"Worksheet name (default: EXPENSES_WORKSHEET_NAME env var or {DEFAULT_WORKSHEET_NAME})",
    )
    parser.add_argument(
        "--export-categories",
        dest="export_categories",
        action="store_true",
        help="Also export Splitwise categories to the 'Splitwise Categories' worksheet when using --no-append/--overwrite",
    )
    parser.add_argument(
        "--sheet-key",
        default=os.getenv("SPREADSHEET_KEY"),
        help="Spreadsheet key/ID (default: SPREADSHEET_KEY env var). Find this in your sheet URL.",
    )
    # --overwrite is an alias for --no-append for backward compatibility
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--no-append",
        dest="append",
        action="store_false",
        help="Overwrite the worksheet instead of appending to it (default: %(default)s)",
    )
    group.add_argument(
        "--overwrite",
        dest="append",
        action="store_false",
        help=argparse.SUPPRESS,  # Hidden alias for backward compatibility
    )
    # Deduplication is always enabled now; `--no-dedupe` removed.

    args = parser.parse_args()

    try:
        # Validate required arguments
        if not args.start_date:
            raise ValueError("--start-date is required (or set START_DATE env var)")
        if not args.end_date:
            raise ValueError("--end-date is required (or set END_DATE env var)")

        # Parse dates (use shared parse_date in src.utils)
        start_date = parse_date(args.start_date)
        end_date = parse_date(args.end_date)

        if start_date > end_date:
            raise ValueError(
                f"Start date ({start_date}) cannot be after end date ({end_date})"
            )

        # Ensure sheet_key is provided for writes
        if not args.sheet_key:
            raise ValueError(
                "--sheet-key must be provided (or set SPREADSHEET_KEY env var)"
            )

        LOG.info("Fetching expenses from %s to %s", start_date, end_date)
        new_df, url = fetch_and_write(
            start_date=start_date,
            end_date=end_date,
            sheet_key=args.sheet_key,
            worksheet_name=args.worksheet_name,
            append=args.append,
            export_categories_flag=args.export_categories,
        )

        if new_df is not None and not new_df.empty:
            print(f"Successfully processed {len(new_df)} expenses")
            if url:
                print(f"Updated sheet: {url}")

            if "status" in new_df.columns:
                print("\nSummary:")
                print(new_df["status"].value_counts().to_string())
        else:
            print("No expenses found or processed")

    except Exception as e:
        LOG.error("Error: %s", str(e), exc_info=True)
        print(f"Error: {str(e)}")
        return 1

    return 0


if __name__ == "__main__":
    exit(main())
