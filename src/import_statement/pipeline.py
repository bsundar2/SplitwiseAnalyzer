"""Orchestrates the ETL pipeline for importing credit card statements to Splitwise."""

# Standard library
import argparse
import os
from datetime import datetime as dt

# Third-party
import pandas as pd
from dotenv import load_dotenv

# Load environment variables
load_dotenv("config/.env")

# Local application
from src.constants.config import PROCESSED_DIR
from src.constants.splitwise import SplitwiseUserId
from src.import_statement.parse_statement import parse_statement
from src.import_statement.process_refunds import RefundProcessor
from src.common.sheets_sync import write_to_sheets
from src.common.splitwise_client import SplitwiseClient
from src.database import DatabaseManager
from src.database.models import Transaction
from src.common.utils import (
    LOG,
    clean_merchant_name,
    infer_category,
    mkdir_p,
    now_iso,
)


def process_statement(
    path,
    dry_run=True,
    limit=None,
    sheet_key: str = None,
    worksheet_name: str = None,
    no_sheet: bool = False,
    start_date: str = None,
    end_date: str = None,
    append_to_sheet: bool = False,
    offset: int = 0,
    merchant_filter: str = None,
):
    # Use defaults from env vars if not provided
    if worksheet_name is None:
        worksheet_name = os.getenv("DRY_RUN_WORKSHEET_NAME", "Amex Imports")
    if start_date is None:
        start_date = os.getenv("START_DATE", "2026-01-01")
    if end_date is None:
        end_date = os.getenv("END_DATE", "2026-12-31")

    LOG.info("Processing statement %s (dry_run=%s)", path, dry_run)
    df = parse_statement(path)
    if df is None or df.empty:
        LOG.info("No transactions parsed from %s", path)
        return

    mkdir_p(PROCESSED_DIR)
    client = None
    db = DatabaseManager()  # Initialize database manager

    if not dry_run:
        client = SplitwiseClient()

        # Pre-fetch expenses for the specified date range to build disk cache
        # This ensures we can detect duplicates across the entire period
        LOG.info(
            f"Pre-fetching expenses from {start_date} to {end_date} to build disk cache..."
        )
        client.fetch_expenses_with_details(start_date, end_date, use_cache=True)
        LOG.info("Disk cache ready for duplicate detection")

    results = []
    added = 0
    attempted = 0
    skipped = 0
    for idx, row in df.reset_index(drop=True).iterrows():
        # Skip transactions before offset
        if skipped < offset:
            skipped += 1
            continue

        if limit and attempted >= limit:
            LOG.info(f"Reached limit of {limit} transactions, stopping")
            break
        attempted += 1
        date = row.get("date")
        desc = row.get("description")
        amount = row.get("amount")
        detail = row.get("detail")
        merchant = row.get("description") or ""

        # Check merchant filter if specified
        if merchant_filter:
            if merchant_filter.lower() not in merchant.lower():
                LOG.debug(
                    f"Skipping transaction (merchant filter '{merchant_filter}' not in '{merchant}')"
                )
                continue

        # Check date filter if specified (filter transactions by date range)
        if date:
            txn_date = (
                dt.strptime(date, "%Y-%m-%d").date() if isinstance(date, str) else date
            )
            start_date_obj = dt.strptime(start_date, "%Y-%m-%d").date()
            end_date_obj = dt.strptime(end_date, "%Y-%m-%d").date()
            if txn_date < start_date_obj or txn_date > end_date_obj:
                LOG.debug(
                    f"Skipping transaction outside date range: {date} (range: {start_date} to {end_date})"
                )
                continue

        # Clean description for Splitwise posting (keep raw for sheets)
        desc_clean = clean_merchant_name(desc)
        desc_raw = desc

        cc_reference_id = None
        if detail is not None:
            s = str(detail).strip()
            if s and s.lower() != "nan":
                cc_reference_id = s

        # Extract cc_reference_id from row if parsed (from detail column)
        if not cc_reference_id and "cc_reference_id" in row:
            cc_reference_id = row.get("cc_reference_id")

        if not cc_reference_id:
            error_msg = f"Transaction is missing required cc_reference_id (date={date}, amount={amount}, description='{desc}')"
            raise ValueError(error_msg)

        # Detect if this is a refund/credit (negative amount OR explicit is_credit flag)
        is_credit = row.get("is_credit", False) or float(amount) < 0
        
        # For refunds, use absolute value for amount
        amount_abs = abs(float(amount))

        entry = {
            "date": date,
            "description": desc_clean,  # Clean version for Splitwise
            "description_raw": desc_raw,  # Raw version for debugging in sheets
            "amount": amount_abs,
            "detail": cc_reference_id,
            "cc_reference_id": cc_reference_id,
            "is_credit": is_credit,
        }

        # Infer category for ALL transactions (needed for sheet reporting even if duplicate)
        is_credit = row.get("is_credit", False)
        if is_credit:
            # All credits should be categorized as Uncategorized > General
            category_info = {
                "category_id": 2,
                "category_name": "Uncategorized",
                "subcategory_id": 18,
                "subcategory_name": "General",
                "confidence": "credit_override",
            }
        else:
            category_info = infer_category(
                {
                    "description": desc,
                    "merchant": merchant,
                    "amount": amount,
                    "category": row.get("category"),  # Pass Amex category if available
                }
            )

        # Add category info to the entry
        entry.update(
            {
                "category_id": category_info.get("category_id"),
                "category_name": category_info.get("category_name"),
                "subcategory_id": category_info.get("subcategory_id"),
                "subcategory_name": category_info.get("subcategory_name"),
                "confidence": category_info.get("confidence"),
            }
        )

        # Check database for duplicate by cc_reference_id ONLY
        # Do NOT use fuzzy matching (date/merchant/amount) because legitimate separate
        # transactions can have identical details (e.g., 2 plane tickets on same day)
        db_found = None

        # Check by cc_reference_id in notes - this is the ONLY reliable duplicate detection
        if cc_reference_id:
            db_transactions = db.get_transactions_by_date_range(start_date, end_date)
            for txn in db_transactions:
                if txn.notes and f"cc_reference_id: {cc_reference_id}" in txn.notes:
                    db_found = txn
                    LOG.info(
                        "Found existing transaction by cc_reference_id in DB: %s (SW ID: %s)",
                        cc_reference_id,
                        txn.splitwise_id,
                    )
                    break

        if db_found:
            entry["status"] = "db_exists"
            entry["db_id"] = db_found.id
            entry["splitwise_id"] = db_found.splitwise_id
            results.append(entry)
            continue

        # check remote (only if not dry_run and client exists)
        remote_found = None
        if client:
            try:
                remote_found = client.find_expense_by_cc_reference(
                    cc_reference_id,
                    amount=amount,
                    date=date,
                    merchant=merchant,
                    use_detailed_search=True,
                    start_date=start_date,
                    end_date=end_date,
                )
            except (RuntimeError, ValueError) as e:
                LOG.warning(
                    "Error searching remote for cc_reference_id %s: %s",
                    cc_reference_id,
                    str(e),
                )
                remote_found = None

        # If found in remote, skip adding to Splitwise
        if remote_found:
            entry["status"] = "remote_exists"
            entry["splitwise_id"] = remote_found.get(
                "id"
            )  # Use splitwise_id for consistency
            entry["remote_id"] = remote_found.get(
                "id"
            )  # Keep remote_id for backward compatibility
            LOG.info(
                "Found existing Splitwise expense for txn %s -> id %s",
                cc_reference_id,
                remote_found.get("id"),
            )
            results.append(entry)
            continue

        # create expense (unless dry_run)
        if dry_run:
            entry["status"] = "would_add"
            results.append(entry)
            continue

        try:
            # Get current user ID
            current_user_id = client.get_current_user_id()

            # Create split based on whether this is a credit or debit
            # For credits (refunds/returns): current_user paid (received credit), SELF_EXPENSE owes
            # For debits (regular expenses): SELF_EXPENSE paid, current_user owes
            is_credit = entry.get("is_credit", False)

            if is_credit:
                # Credit: User received money back, SELF_EXPENSE account owes user
                users = [
                    {
                        "user_id": SplitwiseUserId.SELF_EXPENSE,
                        "paid_share": 0.0,
                        "owed_share": float(amount),
                    },
                    {
                        "user_id": current_user_id,
                        "paid_share": float(amount),
                        "owed_share": 0.0,
                    },
                ]
                LOG.info(
                    "Adding CREDIT: %s paid $%.2f, %s owes $%.2f",
                    current_user_id,
                    amount,
                    SplitwiseUserId.SELF_EXPENSE,
                    amount,
                )
            else:
                # Regular expense: SELF_EXPENSE paid, user owes
                users = [
                    {
                        "user_id": SplitwiseUserId.SELF_EXPENSE,
                        "paid_share": float(amount),
                        "owed_share": 0.0,
                    },
                    {
                        "user_id": current_user_id,
                        "paid_share": 0.0,
                        "owed_share": float(amount),
                    },
                ]

            # Build transaction dict with category info
            txn_dict = {
                "date": date,
                "amount": amount,
                "description": desc_clean,  # Use clean description for Splitwise
                "merchant": merchant,
                "detail": cc_reference_id,
                "category_id": entry.get("category_id"),
                "subcategory_id": entry.get("subcategory_id"),
                "category_name": entry.get("category_name"),
                "subcategory_name": entry.get("subcategory_name"),
            }

            sid = client.add_expense_from_txn(
                txn_dict,
                cc_reference_id,
                users=users,
            )
            entry["status"] = "added"
            entry["splitwise_id"] = sid
            LOG.info(
                "Added expense to Splitwise id=%s for txn %s (%s/%s)",
                sid,
                cc_reference_id,
                category_info.get("category_name", "Unknown"),
                category_info.get("subcategory_name", "Unknown"),
            )

            # Save to database after successful Splitwise creation
            try:
                db_txn = Transaction(
                    date=date,
                    merchant=merchant,
                    description=desc_clean,
                    raw_description=desc_raw,
                    amount=amount_abs,
                    raw_amount=float(amount),  # Store original signed amount
                    statement_date=date,
                    cc_reference_id=cc_reference_id,
                    source="amex",  # TODO: Make this configurable based on statement source
                    source_file=os.path.basename(path),
                    category=entry.get("category_name"),
                    subcategory=entry.get("subcategory_name"),
                    category_id=entry.get("category_id"),
                    subcategory_id=entry.get("subcategory_id"),
                    is_refund=is_credit,
                    is_shared=True,
                    splitwise_id=sid,
                    imported_at=now_iso(),
                    notes=f"cc_reference_id: {cc_reference_id}",
                    reconciliation_status="pending" if is_credit else "matched",
                )
                db_txn_id = db.insert_transaction(db_txn)
                entry["db_id"] = db_txn_id
                LOG.info(
                    "Saved transaction to database with ID %s (Splitwise ID: %s)%s",
                    db_txn_id,
                    sid,
                    " [REFUND - pending matching]" if is_credit else "",
                )
            except Exception as db_error:
                LOG.warning(
                    "Failed to save transaction to database: %s (Splitwise ID: %s)",
                    str(db_error),
                    sid,
                )
                entry["db_error"] = str(db_error)

            added += 1
        except (RuntimeError, ValueError) as e:
            entry["status"] = "error"
            entry["error"] = str(e)
            LOG.exception("Failed to add txn %s: %s", cc_reference_id, str(e))
        results.append(entry)

    # write processed CSV (with statuses)
    out_df = pd.DataFrame(results)
    base = os.path.basename(path)
    out_path = os.path.join(PROCESSED_DIR, base + ".processed.csv")
    out_df.to_csv(out_path, index=False)
    LOG.info("Wrote processed output to %s", out_path)

    # Process refunds (match to originals and create in Splitwise if needed)
    # Only process refunds if not in dry_run mode and we have transactions
    if not dry_run and client and added > 0:
        LOG.info("=" * 60)
        LOG.info("Processing refunds (matching to original transactions)...")
        LOG.info("=" * 60)
        
        refund_processor = RefundProcessor(db=db, client=client)
        refund_summary = refund_processor.process_all_pending_refunds(dry_run=False)
        
        LOG.info("Refund processing summary:")
        LOG.info("  Total pending refunds: %d", refund_summary["total"])
        LOG.info("  Successfully created: %d", refund_summary["created"])
        LOG.info("  Duplicates skipped: %d", refund_summary["duplicate"])
        LOG.info("  Unmatched (manual review): %d", refund_summary["unmatched"])
        LOG.info("  Errors: %d", refund_summary["errors"])
    elif dry_run:
        LOG.info("Skipping refund processing (dry-run mode)")

    # If requested, push the processed output to Google Sheets
    if sheet_key and not no_sheet:
        try:
            # If appending, only include non-cached entries (new additions from this batch)
            sheet_df = out_df
            if append_to_sheet:
                sheet_df = out_df[out_df["status"] != "cached"].copy()
                if sheet_df.empty:
                    LOG.info("No new transactions to append to sheet (all were cached)")
                else:
                    LOG.info(
                        "Appending %d new transactions to sheet (filtered out %d cached)",
                        len(sheet_df),
                        len(out_df) - len(sheet_df),
                    )

            if not sheet_df.empty or not append_to_sheet:
                LOG.info(
                    "Pushing processed output to Google Sheets (key=%s)",
                    sheet_key,
                )
                url = write_to_sheets(
                    sheet_df,
                    worksheet_name=worksheet_name,
                    spreadsheet_key=sheet_key,
                    append=append_to_sheet,
                )
                LOG.info("Wrote processed output to sheet: %s", url)
        except (RuntimeError, ValueError) as e:
            LOG.exception(
                "Failed to write processed output to Google Sheets: %s", str(e)
            )

    return out_df


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Process a CSV statement and add new expenses to Splitwise"
    )
    parser.add_argument(
        "--statement", "-s", required=True, help="Path to CSV statement"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Don't actually add to Splitwise; sheet writes will still occur unless you pass --no-sheet",
    )
    parser.add_argument(
        "--no-sheet",
        action="store_true",
        help="Do not write processed output to Google Sheets (useful for dry runs)",
    )
    parser.add_argument(
        "--append",
        action="store_true",
        help="Append to existing Google Sheet instead of overwriting (useful for batch imports)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit number of expenses to add in a run",
    )
    parser.add_argument(
        "--offset",
        type=int,
        default=0,
        help="Skip the first N transactions (useful for batch processing)",
    )
    parser.add_argument(
        "--merchant-filter",
        type=str,
        default=None,
        help="Only process transactions matching this merchant name (case-insensitive substring match)",
    )
    parser.add_argument(
        "--sheet-key",
        type=str,
        default=os.getenv("SPREADSHEET_KEY"),
        help="Spreadsheet key/ID to write processed output to (default: SPREADSHEET_KEY env var)",
    )
    parser.add_argument(
        "--worksheet-name",
        type=str,
        default=None,
        help="Name of the worksheet/tab to write processed output into (default: DRY_RUN_WORKSHEET_NAME env var for dry runs, 'Imported Transactions' otherwise)",
    )
    parser.add_argument(
        "--start-date",
        type=str,
        default=None,
        help="Start date for duplicate detection range (YYYY-MM-DD, default: START_DATE from .env or 2026-01-01)",
    )
    parser.add_argument(
        "--end-date",
        type=str,
        default=None,
        help="End date for duplicate detection range (YYYY-MM-DD, default: END_DATE from .env or 2026-12-31)",
    )
    args = parser.parse_args()

    # Validate sheet_key if we're going to write to sheets
    if not args.no_sheet and not args.sheet_key:
        parser.error(
            "--sheet-key is required (or set SPREADSHEET_KEY env var) unless --no-sheet is used"
        )

    process_statement(
        args.statement,
        dry_run=args.dry_run,
        limit=args.limit,
        sheet_key=args.sheet_key,
        worksheet_name=args.worksheet_name,
        no_sheet=args.no_sheet,
        start_date=args.start_date,
        end_date=args.end_date,
        append_to_sheet=args.append,
        offset=args.offset,
        merchant_filter=args.merchant_filter,
    )
