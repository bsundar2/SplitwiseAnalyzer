# Orchestrates the ETL pipeline

import argparse
import os
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

from src.constants.config import CACHE_PATH, PROCESSED_DIR
from src.parse_statement import parse_statement
from src.splitwise_client import SplitwiseClient
from src.utils import (
    LOG,
    load_state,
    save_state_atomic,
    now_iso,
    mkdir_p,
    infer_category,
)
from src.sheets_sync import write_to_sheets


def process_statement(
    path,
    dry_run=True,
    limit=None,
    sheet_key: str = None,
    worksheet_name: str = "Imported Transactions",
    no_sheet: bool = False,
):
    LOG.info("Processing statement %s (dry_run=%s)", path, dry_run)
    df = parse_statement(path)
    if df is None or df.empty:
        LOG.info("No transactions parsed from %s", path)
        return

    mkdir_p(PROCESSED_DIR)
    cache = load_state(CACHE_PATH)
    client = None
    if not dry_run:
        client = SplitwiseClient()

    results = []
    added = 0
    for idx, row in df.reset_index(drop=True).iterrows():
        if limit and added >= limit:
            break
        date = row.get("date")
        desc = row.get("description")
        amount = row.get("amount")
        detail = row.get("detail")
        merchant = row.get("description") or ""

        cc_reference_id = None
        if detail is not None:
            s = str(detail).strip()
            if s and s.lower() != "nan":
                cc_reference_id = s

        if not cc_reference_id:
            error_msg = f"Transaction is missing required cc_reference_id (date={date}, amount={amount}, description='{desc}')"
            raise ValueError(error_msg)

        entry = {
            "date": date,
            "description": desc,
            "amount": float(amount),
            "detail": cc_reference_id,
            "cc_reference_id": cc_reference_id,
        }
        # check cache
        if cc_reference_id in cache:
            entry["status"] = "cached"
            LOG.info("Skipping cached txn %s %s %s", date, amount, desc)
            results.append(entry)
            continue

        # check remote (only if not dry_run and client exists)
        remote_found = None
        if client:
            try:
                remote_found = client.find_expense_by_cc_reference(
                    cc_reference_id, merchant=merchant
                )
            except (RuntimeError, ValueError) as e:
                LOG.warning(
                    "Error searching remote for cc_reference_id %s: %s",
                    cc_reference_id,
                    str(e),
                )
                remote_found = None
        if remote_found:
            entry["status"] = "remote_exists"
            entry["remote_id"] = remote_found.get("id")
            LOG.info(
                "Found existing Splitwise expense for txn %s -> id %s",
                cc_reference_id,
                remote_found.get("id"),
            )
            # save to cache for idempotency
            cache[cc_reference_id] = {
                "splitwise_id": remote_found.get("id"),
                "amount": amount,
                "date": date,
                "description": remote_found.get("description"),
                "added_at": now_iso(),
            }
            results.append(entry)
            continue

        # Infer category for the transaction
        category_info = infer_category(
            {"description": desc, "merchant": merchant, "amount": amount}
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

        # create expense (unless dry_run)
        if dry_run:
            entry["status"] = "would_add"
            results.append(entry)
            continue

        try:
            sid = client.add_expense_from_txn(
                {
                    "date": date,
                    "amount": amount,
                    "description": desc,
                    "merchant": merchant,
                    "detail": cc_reference_id,
                },
                cc_reference_id,
            )
            entry["status"] = "added"
            entry["splitwise_id"] = sid
            cache[cc_reference_id] = {
                "splitwise_id": sid,
                "amount": amount,
                "date": date,
                "description": desc,
                "added_at": now_iso(),
            }
            save_state_atomic(CACHE_PATH, cache)
            LOG.info(
                "Added expense to Splitwise id=%s for txn %s (%s/%s)",
                sid,
                cc_reference_id,
                category_info.get("category_name", "Unknown"),
                category_info.get("subcategory_name", "Unknown"),
            )
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

    # If requested, push the processed output to Google Sheets
    if sheet_key and not no_sheet:
        try:
            LOG.info(
                "Pushing processed output to Google Sheets (key=%s)",
                sheet_key,
            )
            url = write_to_sheets(
                out_df,
                worksheet_name=worksheet_name,
                spreadsheet_key=sheet_key,
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
        "--limit",
        type=int,
        default=None,
        help="Limit number of expenses to add in a run",
    )
    parser.add_argument(
        "--sheet-key",
        type=str,
        default=None,
        help="Spreadsheet key/ID to write processed output to",
    )
    parser.add_argument(
        "--worksheet-name",
        type=str,
        default="Imported Transactions",
        help="Name of the worksheet/tab to write processed output into",
    )
    args = parser.parse_args()

    process_statement(
        args.statement,
        dry_run=args.dry_run,
        limit=args.limit,
        sheet_key=args.sheet_key,
        worksheet_name=args.worksheet_name,
        no_sheet=args.no_sheet,
    )
