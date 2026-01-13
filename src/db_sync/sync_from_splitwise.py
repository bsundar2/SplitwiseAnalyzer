"""Sync database with Splitwise - handle updates and deletions.

This script fetches expenses from Splitwise and updates the local database
to reflect any changes made in Splitwise (edits, deletions, split changes).
"""

import argparse
import sys
from datetime import datetime
from typing import Dict, List, Set

from src.common.splitwise_client import SplitwiseClient
from src.database import DatabaseManager
from src.constants.export_columns import ExportColumns


def sync_from_splitwise(
    start_date: str,
    end_date: str,
    dry_run: bool = False,
    verbose: bool = False,
) -> Dict[str, int]:
    """Sync database with Splitwise expenses.

    Args:
        start_date: Start date for sync (YYYY-MM-DD)
        end_date: End date for sync (YYYY-MM-DD)
        dry_run: If True, show changes but don't apply them
        verbose: Print detailed information

    Returns:
        Dictionary with sync statistics
    """
    print(f"\n{'='*60}")
    print(f"Syncing database with Splitwise")
    print(f"Date range: {start_date} to {end_date}")
    print(f"Mode: {'DRY RUN' if dry_run else 'LIVE'}")
    print(f"{'='*60}\n")

    db = DatabaseManager()
    client = SplitwiseClient()

    # Stats tracking
    stats = {
        "checked": 0,
        "updated": 0,
        "marked_deleted": 0,
        "unchanged": 0,
        "not_in_db": 0,
        "errors": 0,
    }

    # Get all transactions from DB that have Splitwise IDs in this date range
    print(f"📊 Fetching transactions from database...")
    db_transactions = db.get_transactions_with_splitwise_ids(start_date, end_date)
    print(f"   Found {len(db_transactions)} transactions with Splitwise IDs\n")

    # Build lookup by splitwise_id
    db_by_splitwise_id = {txn.splitwise_id: txn for txn in db_transactions}

    # Fetch expenses from Splitwise
    print(f"📥 Fetching expenses from Splitwise API...")
    splitwise_df = client.get_my_expenses_by_date_range(
        start_date=start_date,
        end_date=end_date,
        use_cache=False,  # Always fetch fresh data for sync
    )
    print(f"   Found {len(splitwise_df)} expenses in Splitwise\n")

    # Get splitwise_ids that exist in Splitwise
    splitwise_ids_in_api: Set[int] = set()
    if not splitwise_df.empty and ExportColumns.ID in splitwise_df.columns:
        splitwise_ids_in_api = set(splitwise_df[ExportColumns.ID].dropna().astype(int))

    # Process each DB transaction
    print(f"🔄 Processing transactions...\n")

    for txn in db_transactions:
        stats["checked"] += 1
        splitwise_id = txn.splitwise_id

        # Check if expense still exists in Splitwise
        if splitwise_id not in splitwise_ids_in_api:
            # Expense deleted in Splitwise
            if not txn.splitwise_deleted_at:
                print(
                    f"  🗑️  DELETED: ID {splitwise_id} | {txn.date} | {txn.merchant} | ${txn.amount:.2f}"
                )
                if not dry_run:
                    db.mark_deleted_by_splitwise_id(splitwise_id)
                stats["marked_deleted"] += 1
            else:
                if verbose:
                    print(
                        f"  ⏭️  Already marked deleted: ID {splitwise_id} | {txn.merchant}"
                    )
                stats["unchanged"] += 1
            continue

        # Get current data from Splitwise
        expense_row = splitwise_df[splitwise_df[ExportColumns.ID] == splitwise_id].iloc[
            0
        ]

        # Compare and detect changes
        changes = []
        updates = {}

        # Check amount
        sw_amount = float(expense_row[ExportColumns.MY_NET])
        if abs(sw_amount - txn.amount) > 0.01:
            changes.append(f"amount: ${txn.amount:.2f} → ${sw_amount:.2f}")
            updates["amount"] = sw_amount

        # Check date
        sw_date = expense_row[ExportColumns.DATE]
        if sw_date != txn.date:
            changes.append(f"date: {txn.date} → {sw_date}")
            updates["date"] = sw_date

        # Check description/merchant
        sw_desc = expense_row[ExportColumns.DESCRIPTION]
        if sw_desc != txn.merchant:
            changes.append(f"merchant: '{txn.merchant}' → '{sw_desc}'")
            updates["merchant"] = sw_desc
            updates["description"] = sw_desc

        # Check category
        sw_category = expense_row.get(ExportColumns.CATEGORY)
        if sw_category and sw_category != txn.category:
            changes.append(f"category: '{txn.category}' → '{sw_category}'")
            updates["category"] = sw_category

        # Check subcategory
        sw_subcategory = expense_row.get(ExportColumns.SUBCATEGORY)
        if sw_subcategory and sw_subcategory != txn.subcategory:
            changes.append(f"subcategory: '{txn.subcategory}' → '{sw_subcategory}'")
            updates["subcategory"] = sw_subcategory

        if changes:
            print(
                f"  ✏️  UPDATED: ID {splitwise_id} | {txn.merchant} | {', '.join(changes)}"
            )
            if not dry_run:
                db.update_transaction(txn.id, updates)
            stats["updated"] += 1
        else:
            if verbose:
                print(f"  ✅ Unchanged: ID {splitwise_id} | {txn.merchant}")
            stats["unchanged"] += 1

    # Summary
    print(f"\n{'='*60}")
    print(f"Sync Summary {'(DRY RUN)' if dry_run else ''}")
    print(f"{'='*60}")
    print(f"  Transactions checked:    {stats['checked']}")
    print(f"  Updated:                 {stats['updated']}")
    print(f"  Marked as deleted:       {stats['marked_deleted']}")
    print(f"  Unchanged:               {stats['unchanged']}")
    print(f"  Errors:                  {stats['errors']}")
    print(f"{'='*60}\n")

    if dry_run:
        print(
            "💡 This was a dry run. Use --live to apply changes to the database.\n"
        )

    return stats


def main():
    parser = argparse.ArgumentParser(
        description="Sync database with Splitwise (handle updates and deletions)"
    )
    parser.add_argument(
        "--start-date",
        type=str,
        default="2025-01-01",
        help="Start date for sync (YYYY-MM-DD, default: 2025-01-01)",
    )
    parser.add_argument(
        "--end-date",
        type=str,
        default="2026-12-31",
        help="End date for sync (YYYY-MM-DD, default: 2026-12-31)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Show changes without applying them (default)",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Apply changes to database (overrides --dry-run)",
    )
    parser.add_argument(
        "--year",
        type=int,
        help="Sync specific year (sets start-date and end-date)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Show all transactions including unchanged",
    )

    args = parser.parse_args()

    # Handle year shortcut
    if args.year:
        args.start_date = f"{args.year}-01-01"
        args.end_date = f"{args.year}-12-31"

    # Determine if live mode
    is_live = args.live
    is_dry_run = not is_live

    try:
        stats = sync_from_splitwise(
            start_date=args.start_date,
            end_date=args.end_date,
            dry_run=is_dry_run,
            verbose=args.verbose,
        )

        # Exit with error code if there were errors
        if stats["errors"] > 0:
            sys.exit(1)

    except Exception as e:
        print(f"\n❌ Error: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
