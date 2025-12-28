#!/usr/bin/env python3
"""Fetch Splitwise expenses for a date range and write to Google Sheets.

Adds dedupe and append support. Tracks exported Splitwise IDs and fingerprints in data/splitwise_exported.json.
"""
# Standard library
import argparse
import json
from datetime import datetime
from typing import List, Optional, Union

# Third-party
import dateparser
import pandas as pd
import pygsheets

# Local application
from src.constants.config import STATE_PATH
from src.constants.gsheets import SHEETS_AUTHENTICATION_FILE, SPLITWISE_EXPENSES_WORKSHEET, DEFAULT_SPREADSHEET_NAME
from src.sheets_sync import write_to_sheets
from src.splitwise_client import SplitwiseClient
from src.utils import load_state, save_state_atomic, compute_import_id, merchant_slug, LOG, generate_fingerprint

# Column names for the export
class ExportColumns:
    """Column names used in the exported data."""
    DATE = "date"
    AMOUNT = "amount"
    DESCRIPTION = "description"
    FINGERPRINT = "fingerprint"
    ID = "id"


def parse_date(s: str):
    return dateparser.parse(s).date()


def mock_expenses(start_date, end_date):
    """Generate mock expense data for testing.
    
    Args:
        start_date: Start date for mock data
        end_date: End date for mock data
        
    Returns:
        DataFrame with mock expense data
    """
    # Small mock DataFrame matching get_expenses_by_date_range shape
    rows = [
        {
            ExportColumns.DATE: start_date.isoformat(),
            ExportColumns.AMOUNT: "97.01",
            "category": "Internet",
            ExportColumns.DESCRIPTION: "Google Fit [Imported]",
            "friends_split": "Alice: 97.01",
            ExportColumns.ID: "mock-1"
        },
        {
            ExportColumns.DATE: end_date.isoformat(),
            ExportColumns.AMOUNT: "2.99",
            "category": "Entertainment",
            ExportColumns.DESCRIPTION: "Hulu [Imported]",
            "friends_split": "Alice: 2.99",
            ExportColumns.ID: "mock-2"
        },
    ]
    df = pd.DataFrame(rows)
    
    # Generate fingerprints using the same logic as the client
    df[ExportColumns.FINGERPRINT] = df.apply(
        lambda r: compute_import_id(
            r[ExportColumns.DATE],
            float(str(r[ExportColumns.AMOUNT]).replace(',', '').replace('$', '') or 0),
            merchant_slug(r.get(ExportColumns.DESCRIPTION) or r.get("friends_split", ""))
        ),
        axis=1
    )
    return df


def load_exported_state() -> tuple[set, set]:
    """Load the set of previously exported Splitwise expense IDs and fingerprints.
    
    Returns:
        A tuple of (exported_ids, exported_fingerprints) as sets
    """
    try:
        state = load_state(STATE_PATH)
        return set(state.get("exported_ids", [])), set(state.get("exported_fingerprints", []))
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
    sheet_name: Optional[str] = None, 
    worksheet_name: Optional[str] = None
) -> Optional[List[str]]:
    """Read existing fingerprints from a Google Sheet.
    
    Args:
        sheet_key: Google Sheet key (takes precedence over sheet_name)
        sheet_name: Google Sheet name (used if sheet_key not provided)
        worksheet_name: Name of the worksheet to read from
        
    Returns:
        List of fingerprints or None if the sheet couldn't be read
    """
    if not (sheet_key or sheet_name) or not worksheet_name:
        return None
    
    gc = pygsheets.authorize(service_file=SHEETS_AUTHENTICATION_FILE)

    # Open the spreadsheet by key or name
    sh = gc.open_by_key(sheet_key) if sheet_key else gc.open(sheet_name)

    # Get the worksheet
    try:
        wks = sh.worksheet_by_title(worksheet_name)
    except pygsheets.WorksheetNotFound:
        return None

    # Read the data
    df = wks.get_as_df(numerize=False, empty_value=None)
    if df.empty or ExportColumns.FINGERPRINT not in df.columns:
        return None

    # Return non-empty fingerprints
    return [fp for fp in df[ExportColumns.FINGERPRINT].dropna() if fp]


def export_categories(sheet_key: str = None, sheet_name: str = None) -> str:
    """Export all Splitwise categories to a 'Splitwise Categories' worksheet.
    
    Args:
        sheet_key: Google Sheet key (takes precedence over sheet_name)
        sheet_name: Google Sheet name (used if sheet_key not provided)
        
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
        if hasattr(category, 'getSubcategories'):
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
        spreadsheet_name=sheet_name,
        spreadsheet_key=sheet_key,
        append=False  # Always overwrite the categories sheet
    )
    LOG.info("Exported %d categories to Google Sheets", len(category_dict))
    return url


def fetch_and_write(
    start_date: Union[datetime, str],
    end_date: Union[datetime, str],
    sheet_key: Optional[str] = None,
    sheet_name: Optional[str] = None, 
    worksheet_name: str = SPLITWISE_EXPENSES_WORKSHEET,
    mock: bool = False,
    append: bool = True,
    dedupe: bool = True,
    show_skipped: bool = False
) -> tuple[pd.DataFrame, Optional[str]]:
    """Fetch expenses (real or mock), de-duplicate, and write to Google Sheets.

    Args:
        start_date: Start date for expense retrieval
        end_date: End date for expense retrieval
        sheet_key: Optional Google Sheet key (takes precedence over sheet_name)
        sheet_name: Optional Google Sheet name (used if sheet_key not provided)
        worksheet_name: Name of the worksheet to write to
        mock: If True, use mock data instead of real API calls
        append: If True, append to existing sheet; otherwise overwrite
        dedupe: If True, deduplicate expenses based on fingerprint
        show_skipped: If True, include skipped expenses in output

    Returns:
        Tuple of (DataFrame with expenses, URL of the updated sheet or None)
    """
    client = None
    if not mock:
        client = SplitwiseClient()
        df = client.get_my_expenses_by_date_range(start_date, end_date)
    else:
        df = mock_expenses(start_date, end_date)

    # Filter out Splitwise-generated "Settle all balances" rows which are not useful for budgeting.
    # Match the exact phrase (case-insensitive, trimmed) instead of a fuzzy regex.
    if df is not None and not df.empty and ExportColumns.DESCRIPTION in df.columns:
        settle_mask = df[ExportColumns.DESCRIPTION].astype(str).str.strip().str.lower() == "settle all balances"

        num_settle = int(settle_mask.sum())
        if num_settle > 0:
            LOG.info("Filtered out %d Splitwise 'Settle all balances' exact-match transactions from API export", num_settle)
            # Log up to 3 sample rows (date, amount, description)
            sample = df[settle_mask].head(3)
            for _, r in sample.iterrows():
                LOG.info("  Sample settle-row: %s | %s | %s", r.get(ExportColumns.DATE), r.get(ExportColumns.AMOUNT), (r.get(ExportColumns.DESCRIPTION) or '')[:120])
            # Drop those rows from the DataFrame
            df = df[~settle_mask].reset_index(drop=True)

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
            r.get(ExportColumns.DESCRIPTION) or r.get("friends_split", "")
        ),
        axis=1
    )

    # In overwrite mode, we want a full refresh of the worksheet.
    # That means we should not filter anything out based on prior exported state.
    if is_overwrite:
        exported_ids, exported_fps = set(), set()
    else:
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
    if dedupe and not is_overwrite:
        mask_new = ~((df[ExportColumns.ID].isin(exported_ids)) | (df[ExportColumns.FINGERPRINT].isin(exported_fps)))
        new_df = df[mask_new].reset_index(drop=True)
        skipped_df = df[~mask_new].reset_index(drop=True)
    else:
        new_df = df
        skipped_df = pd.DataFrame()

    if show_skipped and not skipped_df.empty:
        # annotate skip reason
        reasons = []
        for _, r in skipped_df.iterrows():
            rid = r.get(ExportColumns.ID)
            fp = r.get(ExportColumns.FINGERPRINT)
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
    if ExportColumns.DATE in new_df.columns:
        # parse and format as 'YYYY-MM-DD' (date-only) strings so Google Sheets will parse them as dates
        parsed = pd.to_datetime(new_df[ExportColumns.DATE], errors="coerce", utc=True)
        # Format where parse succeeded; otherwise leave the original string
        new_df[ExportColumns.DATE] = parsed.dt.strftime('%Y-%m-%d').where(parsed.notna(), new_df[ExportColumns.DATE])

    if ExportColumns.AMOUNT in new_df.columns:
        new_df[ExportColumns.AMOUNT] = pd.to_numeric(new_df[ExportColumns.AMOUNT], errors="coerce")

    # Write to sheets
    if sheet_key or sheet_name:
        url = write_to_sheets(new_df, worksheet_name=worksheet_name, spreadsheet_name=sheet_name or DEFAULT_SPREADSHEET_NAME, spreadsheet_key=sheet_key, append=append)
    else:
        print(new_df.head())

    # Update exported state
    if is_overwrite:
        updated_ids = set(new_df[ExportColumns.ID].tolist())
        updated_fps = set(new_df[ExportColumns.FINGERPRINT].tolist())
    else:
        updated_ids = set(exported_ids) | set(new_df[ExportColumns.ID].tolist())
        updated_fps = set(exported_fps) | set(new_df[ExportColumns.FINGERPRINT].tolist())
    save_exported_state(updated_ids, updated_fps)

    # Export categories if we're in overwrite mode (not appending)
    if not append and not mock:
        LOG.info("Exporting categories due to overwrite mode")
        export_categories(sheet_key=sheet_key, sheet_name=sheet_name)

    return new_df, url


def parse_date_arg(date_str: str) -> datetime.date:
    """Parse a date string from command line arguments.
    
    Args:
        date_str: Date string to parse
        
    Returns:
        Parsed date object
        
    Raises:
        ValueError: If date cannot be parsed
    """
    parsed = dateparser.parse(date_str)
    if not parsed:
        raise ValueError(f"Could not parse date: {date_str}")
    return parsed.date()


def main():
    """Main entry point for the script."""
    parser = argparse.ArgumentParser(description="Export Splitwise expenses to Google Sheets")
    parser.add_argument(
        "--start-date", 
        required=True, 
        help="Start date (any parseable date string, e.g., '2023-01-01' or '3 months ago')"
    )
    parser.add_argument(
        "--end-date", 
        required=True, 
        help="End date (any parseable date string, e.g., '2023-12-31' or 'today')"
    )
    parser.add_argument(
        "--sheet-key", 
        help="Google Sheet key (takes precedence over --sheet-name). "
             "Find in the sheet URL: https://docs.google.com/spreadsheets/d/<key>/edit"
    )
    parser.add_argument(
        "--sheet-name", 
        help="Google Sheet name (used if --sheet-key not provided). "
             "Must be unique in your Google Drive."
    )
    parser.add_argument(
        "--worksheet-name", 
        default=SPLITWISE_EXPENSES_WORKSHEET,
        help=f"Worksheet name (default: {SPLITWISE_EXPENSES_WORKSHEET})"
    )
    parser.add_argument(
        "--mock", 
        action="store_true", 
        help="Use mock data instead of making real API calls to Splitwise"
    )
    # --overwrite is an alias for --no-append for backward compatibility
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--no-append", 
        dest="append", 
        action="store_false",
        help="Overwrite the worksheet instead of appending to it (default: %(default)s)"
    )
    group.add_argument(
        "--overwrite",
        dest="append",
        action="store_false",
        help=argparse.SUPPRESS  # Hidden alias for backward compatibility
    )
    parser.add_argument(
        "--no-dedupe", 
        dest="dedupe", 
        action="store_false",
        default=True,
        help="Skip deduplication of expenses (not recommended, default: %(default)s)"
    )
    parser.add_argument(
        "--show-skipped", 
        action="store_true", 
        help="Show skipped expenses in the output"
    )

    args = parser.parse_args()

    try:
        # Parse dates
        start_date = parse_date_arg(args.start_date)
        end_date = parse_date_arg(args.end_date)
        
        if start_date > end_date:
            raise ValueError(f"Start date ({start_date}) cannot be after end date ({end_date})")

        # Ensure at least one of sheet_key or sheet_name is provided
        if not (args.sheet_key or args.sheet_name):
            raise ValueError("Either --sheet-key or --sheet-name must be provided")

        LOG.info("Fetching expenses from %s to %s", start_date, end_date)
        new_df, url = fetch_and_write(
            start_date=start_date,
            end_date=end_date,
            sheet_key=args.sheet_key,
            sheet_name=args.sheet_name,
            worksheet_name=args.worksheet_name,
            mock=args.mock,
            append=args.append,
            dedupe=args.dedupe,
            show_skipped=args.show_skipped
        )

        if new_df is not None and not new_df.empty:
            print(f"Successfully processed {len(new_df)} expenses")
            if url:
                print(f"Updated sheet: {url}")
            
            if args.show_skipped and 'status' in new_df.columns:
                print("\nSummary:")
                print(new_df['status'].value_counts().to_string())
        else:
            print("No expenses found or processed")
            
    except Exception as e:
        LOG.error("Error: %s", str(e), exc_info=True)
        print(f"Error: {str(e)}")
        return 1
        
    return 0


if __name__ == "__main__":
    exit(main())
