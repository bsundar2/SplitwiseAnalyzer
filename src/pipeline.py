# Orchestrates the ETL pipeline

import os
import argparse
import pandas as pd
from datetime import datetime

from parse_statement import parse_any
from splitwise_client import SplitwiseClient
from utils import LOG, compute_import_id, load_state, save_state_atomic, merchant_slug, mkdir_p

CACHE_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "splitwise_cache.json")
PROCESSED_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "processed")


def process_statement(path, dry_run=True, limit=None):
    LOG.info("Processing statement %s (dry_run=%s)", path, dry_run)
    df = parse_any(path)
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
        merchant = row.get("description") or ""
        import_id = compute_import_id(date, amount, merchant)
        entry = {
            "row_index": int(idx),
            "date": date,
            "description": desc,
            "amount": float(amount),
            "import_id": import_id,
        }
        # check cache
        if import_id in cache:
            entry["status"] = "cached"
            LOG.info("Skipping cached txn %s %s %s", date, amount, desc)
            results.append(entry)
            continue
        # check remote (only if not dry_run and client exists)
        remote_found = None
        if client:
            try:
                remote_found = client.find_expense_by_import_id(import_id, merchant=merchant)
            except Exception as e:
                LOG.warning("Error searching remote for import_id %s: %s", import_id, str(e))
                remote_found = None
        if remote_found:
            entry["status"] = "remote_exists"
            entry["remote_id"] = remote_found.get("id")
            LOG.info("Found existing Splitwise expense for txn %s -> id %s", import_id, remote_found.get("id"))
            # save to cache for idempotency
            cache[import_id] = {
                "splitwise_id": remote_found.get("id"),
                "amount": amount,
                "date": date,
                "description": remote_found.get("description"),
                "added_at": datetime.utcnow().isoformat() + "Z",
            }
            results.append(entry)
            continue

        # create expense (unless dry_run)
        if dry_run:
            entry["status"] = "would_add"
            LOG.info("DRY RUN: would add txn %s %s %s", date, amount, desc)
            results.append(entry)
            continue

        try:
            sid = client.add_expense_from_txn({"date": date, "amount": amount, "description": desc, "merchant": merchant}, import_id)
            entry["status"] = "added"
            entry["splitwise_id"] = sid
            cache[import_id] = {
                "splitwise_id": sid,
                "amount": amount,
                "date": date,
                "description": desc,
                "added_at": datetime.utcnow().isoformat() + "Z",
            }
            save_state_atomic(CACHE_PATH, cache)
            LOG.info("Added expense to Splitwise id=%s for txn %s %s", sid, import_id)
            added += 1
        except Exception as e:
            entry["status"] = "error"
            entry["error"] = str(e)
            LOG.exception("Failed to add txn %s: %s", import_id, str(e))
        results.append(entry)

    # write processed CSV (with statuses)
    out_df = pd.DataFrame(results)
    base = os.path.basename(path)
    out_path = os.path.join(PROCESSED_DIR, base + ".processed.csv")
    out_df.to_csv(out_path, index=False)
    LOG.info("Wrote processed output to %s", out_path)
    return out_df


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Process a CSV statement and add new expenses to Splitwise")
    parser.add_argument("--statement", "-s", required=True, help="Path to CSV statement")
    parser.add_argument("--dry-run", action="store_true", help="Don't actually add to Splitwise; just show what would be done")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of expenses to add in a run")
    args = parser.parse_args()

    process_statement(args.statement, dry_run=args.dry_run, limit=args.limit)
