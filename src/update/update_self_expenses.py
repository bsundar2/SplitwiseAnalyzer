#!/usr/bin/env python3
"""Script to update all 'self' expenses in Splitwise to 100% owed instead of 50/50 split.

This corrects the accounting issue where self expenses were split 50/50 between
two self accounts, when they should be 100% owed to properly reflect the full expense.
"""

import argparse
import sys
from pathlib import Path
from datetime import datetime, timedelta
import pandas as pd
from splitwise import Expense
from splitwise.user import ExpenseUser

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.common.splitwise_client import SplitwiseClient
from src.constants.export_columns import ExportColumns
from src.constants.splitwise import SplitwiseUserId
from src.common.utils import LOG


def update_self_expense(
    client: SplitwiseClient, expense_id: int, amount: float, my_user_id: int
) -> bool:
    """Update a self expense to be 100% owed instead of 50/50 split.

    Args:
        client: SplitwiseClient instance
        expense_id: The Splitwise expense ID to update
        amount: The total expense amount
        my_user_id: The current user's Splitwise ID

    Returns:
        True if successful, False otherwise
    """
    try:
        # Get the expense object
        expense_obj = client.sObj.getExpense(expense_id)

        # Verify participants include current user and exactly one other
        users = expense_obj.getUsers() or []
        user_ids = [u.getId() for u in users]
        if my_user_id not in user_ids or len(users) != 2:
            LOG.warning(
                f"Skipping expense {expense_id}: unexpected participants (users: {user_ids})"
            )
            return False

        # Format amount to two decimals
        amt_str = f"{amount:.2f}"

        # Set shares so one participant owes the full amount (paid=0.00, owed=amount)
        # and the other is recorded as having paid the full amount (paid=amount, owed=0.00).
        for user in users:
            if user.getId() == my_user_id:
                user.setPaidShare("0.00")
                user.setOwedShare(amt_str)
            else:
                user.setPaidShare(amt_str)
                user.setOwedShare("0.00")

        # Update the expense
        result = client.sObj.updateExpense(expense_obj)

        LOG.info(f"Updated expense {expense_id}: ${amount}")
        return True

    except Exception as e:
        LOG.error(f"Failed to update expense {expense_id}: {str(e)}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Update self expenses in Splitwise to be 100% owed instead of 50/50 split"
    )
    parser.add_argument(
        "--start-date",
        type=str,
        help="Start date in YYYY-MM-DD format (default: 30 days ago)",
        default=None,
    )
    parser.add_argument(
        "--end-date",
        type=str,
        help="End date in YYYY-MM-DD format (default: today)",
        default=None,
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be updated without making changes",
    )
    parser.add_argument(
        "--use-csv",
        type=str,
        help="Use CSV file instead of fetching from API (path to splitwise_expenses.csv)",
        default=None,
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Limit number of expenses to update (useful for testing)",
        default=None,
    )
    parser.add_argument(
        "--expense-id",
        type=int,
        help="Specific Splitwise expense ID to update (updates only this transaction)",
        default=None,
    )

    args = parser.parse_args()

    # Initialize client
    client = SplitwiseClient()
    my_user_id = client.get_current_user_id()
    LOG.info(f"Current user ID: {my_user_id}")

    # Parse dates
    if args.end_date:
        end_date = datetime.strptime(args.end_date, "%Y-%m-%d").date()
    else:
        end_date = datetime.now().date()

    if args.start_date:
        start_date = datetime.strptime(args.start_date, "%Y-%m-%d").date()
    else:
        start_date = end_date - timedelta(days=30)

    LOG.info(f"Processing expenses from {start_date} to {end_date}")

    # If a specific expense ID was provided, operate only on that expense
    if args.expense_id:
        expense_id = int(args.expense_id)
        LOG.info(f"Fetching expense {expense_id} for single-update mode")
        try:
            expense_obj = client.sObj.getExpense(expense_id)
            amount = float(expense_obj.getCost())
        except Exception as e:
            LOG.error(f"Failed to fetch expense {expense_id}: {str(e)}")
            return

        if args.dry_run:
            LOG.info(
                "DRY RUN: would update expense %s to full-share format: Balaji|paid=0.00|owed=%s; Other|paid=%s|owed=0.00",
                expense_id,
                f"{amount:.2f}",
                f"{amount:.2f}",
            )
            return

        # Confirm with user before making change
        response = input(
            f"\nUpdate expense {expense_id} to full-share format? (yes/no): "
        )
        if response.lower() not in ["yes", "y"]:
            LOG.info("Update cancelled for expense %s", expense_id)
            return

        success = update_self_expense(client, expense_id, amount, my_user_id)
        if success:
            LOG.info("Updated expense %s", expense_id)
        else:
            LOG.info("Failed to update expense %s", expense_id)
        return

    # Get expenses
    if args.use_csv:
        LOG.info(f"Loading expenses from CSV: {args.use_csv}")
        df = pd.read_csv(args.use_csv)
    else:
        LOG.info("Fetching expenses from Splitwise API...")
        df = client.get_my_expenses_by_date_range(start_date, end_date)

    if df.empty:
        LOG.info("No expenses found in date range")
        return

    # Ensure amount column is numeric for aggregation and updates
    if ExportColumns.AMOUNT in df.columns:
        df[ExportColumns.AMOUNT] = pd.to_numeric(
            df[ExportColumns.AMOUNT], errors="coerce"
        )

    # Filter for expenses between current user and SELF_EXPENSE user only
    # These are the 50/50 self-split expenses we want to convert to 100%
    self_user_id = SplitwiseUserId.SELF_EXPENSE
    LOG.info(
        f"Filtering for expenses between user {my_user_id} and self-expense user {self_user_id}"
    )

    def is_self_split_expense(row):
        """Check if expense is between main user and self-expense user."""
        try:
            # Parse the friends_split field to get participant user IDs
            if pd.isna(row.get(ExportColumns.FRIENDS_SPLIT, "")):
                return False

            participants = row[ExportColumns.FRIENDS_SPLIT].split("; ")
            user_ids = set()

            for p in participants:
                # Format: "Name|paid=X|owed=Y"
                parts = p.split("|")
                if parts:
                    name = parts[0].strip()
                    # Check if this participant matches our known users
                    # Since we can't extract user_id from this format easily,
                    # we'll check if it's exactly 2 participants with same name
                    user_ids.add(name)

            # Self expenses have exactly 2 entries with the same name (or "Balaji, Balaji" pattern)
            participant_names = row.get(ExportColumns.PARTICIPANT_NAMES, "")
            return (
                row.get(ExportColumns.SPLIT_TYPE) == "self"
                and "," in participant_names
                and len(participant_names.split(",")) == 2
                and participant_names.split(",")[0].strip()
                == participant_names.split(",")[1].strip()
            )
        except Exception as e:
            LOG.debug(
                f"Error checking expense {row.get(ExportColumns.ID, 'unknown')}: {str(e)}"
            )
            return False

    self_expenses = df[df.apply(is_self_split_expense, axis=1)].copy()

    if self_expenses.empty:
        LOG.info("No self expenses found in date range")
        return

    LOG.info(f"Found {len(self_expenses)} self expenses to update")

    # Apply limit if specified
    if args.limit and len(self_expenses) > args.limit:
        LOG.info(f"Limiting to first {args.limit} expenses")
        self_expenses = self_expenses.head(args.limit)

    # Show summary
    total_amount = self_expenses[ExportColumns.AMOUNT].sum()
    LOG.info(f"Total amount in self expenses: ${total_amount:.2f}")

    if args.dry_run:
        LOG.info("\n=== DRY RUN MODE - No changes will be made ===\n")
        for _, expense in self_expenses.iterrows():
            LOG.info(
                f"Would update: ID={expense[ExportColumns.ID]}, "
                f"Date={expense[ExportColumns.DATE][:10]}, "
                f"Amount=${expense[ExportColumns.AMOUNT]:.2f}, "
                f"Description={expense[ExportColumns.DESCRIPTION]}"
            )
        LOG.info(f"\nTotal: {len(self_expenses)} expenses would be updated")
        return

    # Confirm with user
    response = input(f"\nUpdate {len(self_expenses)} self expenses? (yes/no): ")
    if response.lower() not in ["yes", "y"]:
        LOG.info("Update cancelled")
        return

    # Update expenses
    LOG.info("\nUpdating expenses...")
    success_count = 0
    fail_count = 0

    for _, expense in self_expenses.iterrows():
        expense_id = int(expense[ExportColumns.ID])
        amount = float(expense[ExportColumns.AMOUNT])

        if update_self_expense(client, expense_id, amount, my_user_id):
            success_count += 1
        else:
            fail_count += 1

    # Summary
    LOG.info(f"\n=== Update Complete ===")
    LOG.info(f"Successful: {success_count}")
    LOG.info(f"Failed: {fail_count}")
    LOG.info(f"Total: {len(self_expenses)}")


if __name__ == "__main__":
    main()
