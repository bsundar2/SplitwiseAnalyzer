"""Migrate data directly from Splitwise API to database.

This script fetches expenses directly from the Splitwise API and imports them
into the local SQLite database. This is the cleanest way to get your historical
data without relying on cache files or Google Sheets.
"""

import os
import sys
from datetime import datetime, date
from typing import Dict, Any, List

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from src.database import DatabaseManager, Transaction
from src.database.models import ImportLog
from src.common.splitwise_client import SplitwiseClient
from src.constants.export_columns import ExportColumns


def parse_expense_to_transaction(row: Dict[str, Any]) -> Transaction:
    """Convert Splitwise dataframe row to Transaction object.

    Args:
        row: Row dictionary from SplitwiseClient.get_my_expenses_by_date_range()

    Returns:
        Transaction object
    """
    # Extract fields using ExportColumns constants
    expense_id = row.get(ExportColumns.ID)

    # Date - clean up if needed
    date_str = str(row.get(ExportColumns.DATE, ""))
    if "T" in date_str:
        date = date_str.split("T")[0]
    else:
        date = date_str

    description = row.get(ExportColumns.DESCRIPTION, "")
    merchant = description  # Use description as merchant
    details = row.get(ExportColumns.DETAILS, "")

    # Amounts
    total_cost = float(row.get(ExportColumns.AMOUNT, 0))
    my_paid = float(row.get(ExportColumns.MY_PAID, 0))
    my_owed = float(row.get(ExportColumns.MY_OWED, 0))
    my_net = float(
        row.get(ExportColumns.MY_NET, 0)
    )  # This is what we paid minus what we owe

    # Category
    category_name = row.get(ExportColumns.CATEGORY, "Uncategorized")

    # Split type
    split_type = row.get(ExportColumns.SPLIT_TYPE, "unknown")
    is_self = split_type == "self"

    # Participants
    participant_names = row.get(ExportColumns.PARTICIPANT_NAMES, "")

    # Determine if refund/payment
    is_refund = total_cost < 0

    # Build notes
    notes_parts = ["Imported from Splitwise API"]
    if my_paid > 0:
        notes_parts.append(f"Paid: ${my_paid:.2f}")
    if my_owed > 0:
        notes_parts.append(f"Owe: ${my_owed:.2f}")
    if participant_names:
        notes_parts.append(f"With: {participant_names}")
    notes = " | ".join(notes_parts)

    txn = Transaction(
        date=date,
        merchant=merchant,
        description=description,
        raw_description=f"{description} | {details}".strip(" |"),
        amount=my_net,  # Net: what you paid minus what you owe
        raw_amount=total_cost,  # Total expense cost
        source="splitwise",
        category=category_name,
        is_refund=is_refund,
        is_shared=not is_self,
        currency="USD",  # Default, API response doesn't include this in dataframe
        splitwise_id=expense_id,
        imported_at=datetime.utcnow().isoformat(),
        notes=notes,
    )

    return txn


def migrate_year(
    client: SplitwiseClient,
    db_manager: DatabaseManager,
    year: int,
    dry_run: bool = False,
) -> Dict[str, int]:
    """Migrate expenses for a specific year.

    Args:
        client: SplitwiseClient instance
        db_manager: DatabaseManager instance
        year: Year to migrate (e.g., 2025)
        dry_run: If True, don't insert into database

    Returns:
        Dictionary with import statistics
    """
    start_date = date(year, 1, 1)
    end_date = date(year, 12, 31)

    print(
        f"\n{'[DRY RUN] ' if dry_run else ''}Fetching expenses for {year} ({start_date} to {end_date})"
    )

    # Fetch expenses from API
    try:
        expenses_df = client.get_my_expenses_by_date_range(
            start_date=start_date, end_date=end_date
        )
    except Exception as e:
        print(f"❌ Error fetching expenses: {e}")
        import traceback

        traceback.print_exc()
        return {"attempted": 0, "imported": 0, "skipped": 0, "failed": 0}

    if expenses_df.empty:
        print(f"⚠️  No expenses found for {year}")
        return {"attempted": 0, "imported": 0, "skipped": 0, "failed": 0}

    # Convert to list of dicts
    expenses = expenses_df.to_dict("records")

    print(f"Found {len(expenses)} expenses from Splitwise API")

    stats = {"attempted": len(expenses), "imported": 0, "skipped": 0, "failed": 0}

    transactions_to_import = []

    for idx, expense in enumerate(expenses, start=1):
        try:
            expense_id = expense.get(ExportColumns.ID)

            # Check if already exists
            if expense_id:
                existing = db_manager.get_transaction_by_splitwise_id(expense_id)
                if existing:
                    if idx <= 5 or idx % 100 == 0:  # Only print occasionally
                        print(
                            f"  [{idx}/{len(expenses)}] ⏭️  Skipping duplicate: {expense_id}"
                        )
                    stats["skipped"] += 1
                    continue

            # Parse to Transaction
            txn = parse_expense_to_transaction(expense)

            if dry_run:
                if idx <= 10:  # Show first 10 in dry run
                    print(
                        f"  Would import: {txn.date} | {txn.merchant[:30]} | ${txn.amount:.2f} | {txn.category}"
                    )
            else:
                transactions_to_import.append(txn)

            stats["imported"] += 1

            # Progress indicator
            if not dry_run and idx % 100 == 0:
                print(f"  [{idx}/{len(expenses)}] Processed...")

        except Exception as e:
            print(
                f"❌ Error processing expense {expense.get(ExportColumns.ID, 'unknown')}: {e}"
            )
            stats["failed"] += 1

    # Batch insert
    if not dry_run and transactions_to_import:
        print(
            f"\nInserting {len(transactions_to_import)} transactions into database..."
        )
        db_manager.insert_transactions_batch(transactions_to_import)
        print(f"✅ Inserted {len(transactions_to_import)} transactions for {year}")

    return stats


def main():
    """Main migration script."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Migrate expenses from Splitwise API to database",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Migrate single year (dry-run)
  python scripts/migrate_from_splitwise_api.py --year 2025 --dry-run
  
  # Migrate single year (actual import)
  python scripts/migrate_from_splitwise_api.py --year 2025
  
  # Migrate multiple years
  python scripts/migrate_from_splitwise_api.py --years 2023 2024 2025 2026
  
  # Migrate everything from 2020 onwards
  python scripts/migrate_from_splitwise_api.py --year-range 2020 2026
        """,
    )

    # Year selection options
    year_group = parser.add_mutually_exclusive_group(required=True)
    year_group.add_argument(
        "--year", type=int, help="Single year to migrate (e.g., 2025)"
    )
    year_group.add_argument(
        "--years",
        type=int,
        nargs="+",
        help="Multiple years to migrate (e.g., 2023 2024 2025)",
    )
    year_group.add_argument(
        "--year-range",
        type=int,
        nargs=2,
        metavar=("START", "END"),
        help="Range of years (inclusive) to migrate (e.g., 2020 2026)",
    )

    parser.add_argument(
        "--dry-run", action="store_true", help="Preview without inserting into database"
    )
    parser.add_argument(
        "--db-path", help="Database path (default: data/transactions.db)"
    )

    args = parser.parse_args()

    # Determine years to process
    if args.year:
        years = [args.year]
    elif args.years:
        years = sorted(args.years)
    else:  # year_range
        start, end = args.year_range
        years = list(range(start, end + 1))

    # Initialize
    print("=" * 60)
    print("Splitwise API → Database Migration")
    print("=" * 60)
    print(f"Years to process: {', '.join(map(str, years))}")

    try:
        client = SplitwiseClient()
        current_user_id = client.get_current_user_id()
        print(f"Connected as user ID: {current_user_id}")
    except Exception as e:
        print(f"❌ Error connecting to Splitwise API: {e}")
        print("Make sure your API credentials are set in config/.env")
        return

    db_manager = DatabaseManager(db_path=args.db_path)

    # Migrate each year
    total_stats = {"attempted": 0, "imported": 0, "skipped": 0, "failed": 0}

    for year in years:
        stats = migrate_year(
            client=client, db_manager=db_manager, year=year, dry_run=args.dry_run
        )

        for key in total_stats:
            total_stats[key] += stats[key]

        # Log import (if not dry run and had some activity)
        if not args.dry_run and stats["attempted"] > 0:
            log = ImportLog(
                timestamp=datetime.utcnow().isoformat(),
                source_type="splitwise_api",
                source_identifier=f"year_{year}",
                records_attempted=stats["attempted"],
                records_imported=stats["imported"],
                records_skipped=stats["skipped"],
                records_failed=stats["failed"],
            )
            db_manager.log_import(log)

    # Print summary
    print("\n" + "=" * 60)
    print("MIGRATION SUMMARY")
    print("=" * 60)
    print(f"Total expenses processed: {total_stats['attempted']}")
    print(f"✅ Imported: {total_stats['imported']}")
    print(f"⏭️  Skipped (duplicates): {total_stats['skipped']}")
    print(f"❌ Failed: {total_stats['failed']}")

    if args.dry_run:
        print("\n⚠️  This was a DRY RUN - no data was inserted")
    else:
        print(f"\n✅ Migration complete!")

    # Show database stats
    if not args.dry_run and total_stats["imported"] > 0:
        print("\n" + "=" * 60)
        print("DATABASE STATS")
        print("=" * 60)
        db_stats = db_manager.get_stats()
        print(f"Total transactions: {db_stats['total_transactions']}")
        print(f"By source:")
        for source, count in db_stats["by_source"].items():
            print(f"  - {source}: {count}")
        print(f"In Splitwise: {db_stats['in_splitwise']}")
        print(f"Deleted in Splitwise: {db_stats['deleted_in_splitwise']}")
        print(
            f"Date range: {db_stats['date_range']['min']} to {db_stats['date_range']['max']}"
        )


if __name__ == "__main__":
    main()
