#!/usr/bin/env python3
"""Bulk update Splitwise expense categories by merchant name or current category.

This script allows you to find expenses matching certain criteria (merchant name,
current category) and update them to a new category in bulk.
"""

import argparse
import os
import sys
from pathlib import Path
from datetime import datetime

from splitwise.category import Category

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.common.splitwise_client import SplitwiseClient
from src.common.utils import parse_date_string
from src.common.env import get_env
from src.constants.export_columns import ExportColumns
from src.constants.splitwise import SUBCATEGORY_IDS
from src.common.utils import LOG


# Alias the constant for backward compatibility
COMMON_SUBCATEGORIES = SUBCATEGORY_IDS


def find_expenses_to_update(
    client: SplitwiseClient,
    start_date: datetime,
    end_date: datetime,
    merchant_filter: str = None,
    current_category_filter: str = None,
    exclude_merchant: str = None,
):
    """Find expenses matching the specified filters.

    Args:
        client: SplitwiseClient instance
        start_date: Start date for expense search
        end_date: End date for expense search
        merchant_filter: Merchant name to filter by (case-insensitive substring match)
        current_category_filter: Current category to filter by (exact match)
        exclude_merchant: Merchant name to exclude (case-insensitive substring match)

    Returns:
        DataFrame of matching expenses
    """
    df = client.get_my_expenses_by_date_range(start_date, end_date)

    LOG.info(
        f"Retrieved {len(df)} total expenses from {start_date.date()} to {end_date.date()}"
    )

    # Apply filters
    filtered = df.copy()

    if merchant_filter:
        filtered = filtered[
            filtered[ExportColumns.DESCRIPTION].str.contains(
                merchant_filter, case=False, na=False
            )
        ]
        LOG.info(f"After merchant filter '{merchant_filter}': {len(filtered)} expenses")

    if exclude_merchant:
        filtered = filtered[
            ~filtered[ExportColumns.DESCRIPTION].str.contains(
                exclude_merchant, case=False, na=False
            )
        ]
        LOG.info(f"After excluding '{exclude_merchant}': {len(filtered)} expenses")

    if current_category_filter:
        # Support both "Category" and "Category - Subcategory" formats
        filtered = filtered[
            (filtered[ExportColumns.CATEGORY].str.strip() == current_category_filter)
            | (
                filtered[ExportColumns.CATEGORY].str.strip()
                == current_category_filter.replace(" > ", " - ")
            )
        ]
        LOG.info(
            f"After category filter '{current_category_filter}': {len(filtered)} expenses"
        )

    return filtered


def update_expenses(
    client: SplitwiseClient,
    expenses_df,
    new_subcategory_id: int,
    dry_run: bool = False,
):
    """Update expenses to the new category.

    Args:
        client: SplitwiseClient instance
        expenses_df: DataFrame of expenses to update
        new_subcategory_id: The subcategory ID to set
        dry_run: If True, only show what would be updated

    Returns:
        Number of expenses updated
    """
    if expenses_df.empty:
        LOG.info("No expenses to update")
        return 0

    if dry_run:
        LOG.info(f"DRY RUN: Would update {len(expenses_df)} expenses")
        return 0

    LOG.info(
        f"Updating {len(expenses_df)} expenses to subcategory ID {new_subcategory_id}"
    )

    updated_count = 0
    for idx, row in expenses_df.iterrows():
        exp_id = row[ExportColumns.ID]
        try:
            exp = client.sObj.getExpense(exp_id)

            # Set new category
            category = Category()
            category.id = new_subcategory_id
            exp.setCategory(category)

            client.sObj.updateExpense(exp)
            LOG.info(
                f"Updated expense {exp_id}: {row[ExportColumns.DESCRIPTION]} ({row[ExportColumns.DATE]})"
            )
            updated_count += 1
        except Exception as e:
            LOG.error(f"Failed to update expense {exp_id}: {str(e)}")

    return updated_count


def main():
    parser = argparse.ArgumentParser(
        description="Bulk update Splitwise expense categories by merchant or current category",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Update all SpotHero expenses to Transportation > Parking
  python src/update/bulk_update_categories.py --merchant "SpotHero" --subcategory-id 9
  
  # Update Amazon (excluding AWS) to Household supplies
  python src/update/bulk_update_categories.py --merchant "Amazon" --exclude "AWS" --subcategory-id 14
  
  # Update only Costco expenses currently in "Home - Other" to Household supplies
  python src/update/bulk_update_categories.py --merchant "Costco" --current-category "Home - Other" --subcategory-id 14
  
  # Use predefined subcategory names
  python src/update/bulk_update_categories.py --merchant "SpotHero" --subcategory parking

Common subcategory IDs:
  parking (9), household_supplies (14), home_other (28), medical (38)
  
See src/constants/splitwise.py for full list of available subcategory IDs.
        """,
    )
    parser.add_argument(
        "--start-date",
        type=str,
        help="Start date in YYYY-MM-DD format (default: from config/.env)",
        default=None,
    )
    parser.add_argument(
        "--end-date",
        type=str,
        help="End date in YYYY-MM-DD format (default: from config/.env)",
        default=None,
    )
    parser.add_argument(
        "--merchant",
        type=str,
        help="Filter by merchant name (case-insensitive substring match)",
        default=None,
    )
    parser.add_argument(
        "--exclude",
        type=str,
        help="Exclude expenses with this merchant name (case-insensitive substring match)",
        default=None,
    )
    parser.add_argument(
        "--current-category",
        type=str,
        help="Filter by current category (e.g., 'Home - Other')",
        default=None,
    )

    # Subcategory specification - either ID or name
    subcategory_group = parser.add_mutually_exclusive_group(required=True)
    subcategory_group.add_argument(
        "--subcategory-id",
        type=int,
        help="New subcategory ID to set",
    )
    subcategory_group.add_argument(
        "--subcategory",
        type=str,
        choices=list(COMMON_SUBCATEGORIES.keys()),
        help="New subcategory name (predefined mappings)",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be updated without making changes",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Skip confirmation prompt",
    )

    args = parser.parse_args()

    # Initialize client
    client = SplitwiseClient()

    # Parse dates
    if args.end_date:
        end_date = parse_date_string(args.end_date)
    else:
        end_date_str = get_env("END_DATE")
        end_date = parse_date_string(end_date_str) if end_date_str else datetime.now()

    if args.start_date:
        start_date = parse_date_string(args.start_date)
    else:
        start_date_str = get_env("START_DATE")
        start_date = (
            parse_date_string(start_date_str)
            if start_date_str
            else datetime(end_date.year, 1, 1)
        )

    # Determine subcategory ID
    if args.subcategory:
        new_subcategory_id = COMMON_SUBCATEGORIES[args.subcategory]
        LOG.info(
            f"Using predefined subcategory '{args.subcategory}' (ID: {new_subcategory_id})"
        )
    else:
        new_subcategory_id = args.subcategory_id

    # Find expenses to update
    LOG.info("Searching for expenses matching criteria...")
    expenses_to_update = find_expenses_to_update(
        client,
        start_date,
        end_date,
        merchant_filter=args.merchant,
        current_category_filter=args.current_category,
        exclude_merchant=args.exclude,
    )

    if expenses_to_update.empty:
        LOG.info("No expenses found matching the criteria")
        return 0

    # Display preview
    print(f"\nFound {len(expenses_to_update)} expenses to update:\n")
    print(
        expenses_to_update[
            [
                ExportColumns.DATE,
                ExportColumns.DESCRIPTION,
                ExportColumns.CATEGORY,
                ExportColumns.AMOUNT,
            ]
        ]
        .head(20)
        .to_string()
    )
    if len(expenses_to_update) > 20:
        print(f"\n... and {len(expenses_to_update) - 20} more")

    # Confirm unless --yes or --dry-run
    if not args.dry_run and not args.yes:
        response = input(
            f"\nUpdate {len(expenses_to_update)} expenses to subcategory ID {new_subcategory_id}? (yes/no): "
        )
        if response.lower() != "yes":
            LOG.info("Update cancelled")
            return 0

    # Perform update
    updated_count = update_expenses(
        client,
        expenses_to_update,
        new_subcategory_id,
        dry_run=args.dry_run,
    )

    if args.dry_run:
        LOG.info(f"DRY RUN: Would update {len(expenses_to_update)} expenses")
    else:
        LOG.info(f"Successfully updated {updated_count} expenses")

    return updated_count


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        LOG.info("\nOperation cancelled by user")
        sys.exit(1)
    except Exception as e:
        LOG.error(f"Error: {str(e)}")
        sys.exit(1)
