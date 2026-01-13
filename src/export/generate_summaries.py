#!/usr/bin/env python3
"""Generate budget summary and analysis sheets from transaction data.

Creates multiple analysis tabs:
1. Monthly Summary - Total spending by month with trends
2. Category Breakdown - Spending by category with percentages
3. Budget vs Actual - Compare actual spending against budget targets
4. Monthly Trends - Rolling averages and spending patterns
"""

import argparse
import os
from typing import Dict

import pandas as pd
import pygsheets
from dotenv import load_dotenv

load_dotenv("config/.env")

from src.common.sheets_sync import write_to_sheets
from src.common.utils import LOG
from src.constants.gsheets import (
    SHEETS_AUTHENTICATION_FILE,
    WORKSHEET_MONTHLY_SUMMARY,
    WORKSHEET_CATEGORY_BREAKDOWN,
    WORKSHEET_BUDGET_VS_ACTUAL,
    WORKSHEET_MONTHLY_TRENDS,
)
from src.database import DatabaseManager

# Constants
DEFAULT_BUDGET_FILE = "config/budget_2026.json"


def fetch_transactions_for_analysis(year: int) -> pd.DataFrame:
    """Fetch all transactions for the specified year from database.

    Args:
        year: Year to analyze

    Returns:
        DataFrame with transaction data
    """
    LOG.info(f"Fetching transactions for {year}...")

    db = DatabaseManager()
    start_date = f"{year}-01-01"
    end_date = f"{year}-12-31"

    # Get all transactions for analysis
    transactions = db.get_transactions_with_splitwise_ids(
        start_date=start_date, end_date=end_date
    )

    if not transactions:
        LOG.warning(f"No transactions found for {year}")
        return pd.DataFrame()

    # Convert to DataFrame
    data = []
    for txn in transactions:
        # Parse notes field to extract payment info
        my_paid = 0.0
        my_owed = 0.0

        if txn.notes:
            import re

            paid_match = re.search(r"Paid: \$?([\d,]+\.?\d*)", txn.notes)
            owe_match = re.search(r"Owe: \$?([\d,]+\.?\d*)", txn.notes)

            if paid_match:
                my_paid = float(paid_match.group(1).replace(",", ""))
            if owe_match:
                my_owed = float(owe_match.group(1).replace(",", ""))

        my_net = my_paid - my_owed

        data.append(
            {
                "date": txn.date,
                "amount": txn.amount,
                "category": txn.category or "Uncategorized",
                "description": txn.description,
                "my_paid": my_paid,
                "my_owed": my_owed,
                "my_net": my_net,
                "is_shared": txn.is_shared,
                "is_deleted": bool(txn.splitwise_deleted_at),
            }
        )

    df = pd.DataFrame(data)

    # Filter out deleted and payment transactions
    df = df[~df["is_deleted"]]
    df = df[
        ~((df["description"].str.lower() == "payment") & (df["category"] == "General"))
    ]

    # Convert date to datetime
    df["date"] = pd.to_datetime(df["date"])
    df["year_month"] = df["date"].dt.to_period("M")
    df["month"] = df["date"].dt.month
    df["month_name"] = df["date"].dt.strftime("%B")

    LOG.info(f"Found {len(df)} transactions for analysis")
    return df


def generate_monthly_summary(df: pd.DataFrame, year: int) -> pd.DataFrame:
    """Generate monthly spending summary.

    Args:
        df: Transaction DataFrame
        year: Year being analyzed

    Returns:
        DataFrame with monthly summary
    """
    if df.empty:
        return pd.DataFrame()

    # Group by month
    monthly = (
        df.groupby("year_month")
        .agg({"my_net": ["sum", "mean", "count"], "my_paid": "sum", "my_owed": "sum"})
        .reset_index()
    )

    # Flatten column names
    monthly.columns = [
        "Month",
        "Total Spent (Net)",
        "Avg Transaction",
        "Transaction Count",
        "Total Paid",
        "Total Owed",
    ]

    # Format month as YYYY-MM
    monthly["Month"] = monthly["Month"].astype(str)

    # Calculate cumulative spending
    monthly["Cumulative Spending"] = monthly["Total Spent (Net)"].cumsum()

    # Calculate month-over-month change
    monthly["MoM Change"] = monthly["Total Spent (Net)"].pct_change() * 100
    monthly["MoM Change"] = monthly["MoM Change"].fillna(0)

    # Round numeric columns
    numeric_cols = [
        "Total Spent (Net)",
        "Avg Transaction",
        "Total Paid",
        "Total Owed",
        "Cumulative Spending",
        "MoM Change",
    ]
    for col in numeric_cols:
        monthly[col] = monthly[col].round(2)

    return monthly


def generate_category_breakdown(df: pd.DataFrame, year: int) -> pd.DataFrame:
    """Generate spending breakdown by category.

    Args:
        df: Transaction DataFrame
        year: Year being analyzed

    Returns:
        DataFrame with category breakdown
    """
    if df.empty:
        return pd.DataFrame()

    # Group by category
    category = (
        df.groupby("category").agg({"my_net": ["sum", "mean", "count"]}).reset_index()
    )

    # Flatten column names
    category.columns = [
        "Category",
        "Total Spent",
        "Avg Transaction",
        "Transaction Count",
    ]

    # Calculate percentage of total
    total_spent = category["Total Spent"].sum()
    category["% of Total"] = (category["Total Spent"] / total_spent * 100).round(2)

    # Sort by total spent (descending)
    category = category.sort_values("Total Spent", ascending=False)

    # Round numeric columns
    category["Total Spent"] = category["Total Spent"].round(2)
    category["Avg Transaction"] = category["Avg Transaction"].round(2)

    # Add total row
    total_row = pd.DataFrame(
        [
            {
                "Category": "TOTAL",
                "Total Spent": total_spent,
                "Avg Transaction": df["my_net"].mean(),
                "Transaction Count": len(df),
                "% of Total": 100.0,
            }
        ]
    )

    category = pd.concat([category, total_row], ignore_index=True)

    return category


def generate_monthly_trends(df: pd.DataFrame, year: int) -> pd.DataFrame:
    """Generate monthly trends with rolling averages.

    Args:
        df: Transaction DataFrame
        year: Year being analyzed

    Returns:
        DataFrame with monthly trends
    """
    if df.empty:
        return pd.DataFrame()

    # Monthly spending
    monthly = df.groupby("year_month").agg({"my_net": "sum"}).reset_index()

    monthly.columns = ["Month", "Total Spent"]
    monthly["Month"] = monthly["Month"].astype(str)

    # Calculate rolling averages (3-month)
    monthly["3-Month Avg"] = (
        monthly["Total Spent"].rolling(window=3, min_periods=1).mean()
    )

    # Calculate YTD average
    monthly["YTD Avg"] = monthly["Total Spent"].expanding().mean()

    # Round numeric columns
    numeric_cols = ["Total Spent", "3-Month Avg", "YTD Avg"]
    for col in numeric_cols:
        monthly[col] = monthly[col].round(2)

    return monthly


def generate_category_monthly_breakdown(df: pd.DataFrame, year: int) -> pd.DataFrame:
    """Generate spending by category and month (pivot table).

    Args:
        df: Transaction DataFrame
        year: Year being analyzed

    Returns:
        DataFrame with category x month breakdown
    """
    if df.empty:
        return pd.DataFrame()

    # Pivot: categories as rows, months as columns
    pivot = df.pivot_table(
        values="my_net",
        index="category",
        columns="month_name",
        aggfunc="sum",
        fill_value=0,
    )

    # Order months chronologically
    month_order = [
        "January",
        "February",
        "March",
        "April",
        "May",
        "June",
        "July",
        "August",
        "September",
        "October",
        "November",
        "December",
    ]

    # Keep only months that exist in the data
    existing_months = [m for m in month_order if m in pivot.columns]
    pivot = pivot[existing_months]

    # Add total column
    pivot["Total"] = pivot.sum(axis=1)

    # Sort by total (descending)
    pivot = pivot.sort_values("Total", ascending=False)

    # Round to 2 decimals
    pivot = pivot.round(2)

    # Add total row
    total_row = pivot.sum().to_frame().T
    total_row.index = ["TOTAL"]
    pivot = pd.concat([pivot, total_row])

    # Reset index to make category a column
    pivot = pivot.reset_index()
    pivot.columns.name = None

    return pivot


def load_budget(budget_file: str) -> Dict[str, float]:
    """Load budget targets from JSON file.

    Args:
        budget_file: Path to budget JSON file

    Returns:
        Dictionary mapping category to budget amount
    """
    import json

    if not os.path.exists(budget_file):
        LOG.warning(f"Budget file not found: {budget_file}")
        return {}

    with open(budget_file, "r") as f:
        budget = json.load(f)
    LOG.info(f"Loaded budget from {budget_file}")
    return budget


def generate_budget_vs_actual(
    df: pd.DataFrame, year: int, budget: Dict[str, float]
) -> pd.DataFrame:
    """Generate budget vs actual comparison.

    Args:
        df: Transaction DataFrame
        year: Year being analyzed
        budget: Dictionary mapping category to budget amount

    Returns:
        DataFrame with budget vs actual comparison
    """
    if df.empty:
        return pd.DataFrame()

    # Get actual spending by category
    actual = df.groupby("category")["my_net"].sum().to_dict()

    # Map common category names to budget categories
    category_mapping = {
        "Rent": "Home - Rent",
        "Dining out": "Food and drink - Dining out",
        "Groceries": "Food and drink - Groceries",
        "Liquor": "Food and drink - Liquor",
        "Gas/fuel": "Transportation - Gas/fuel",
        "Taxi": "Transportation - Taxi",
        "Plane": "Transportation - Plane",
        "Bus/train": "Transportation - Bus/train",
        "Bicycle": "Transportation - Bicycle",
        "Car": "Transportation - Car",
        "Parking": "Transportation - Parking",
        "Hotel": "Transportation - Hotel",
        "Clothing": "Life - Clothing",
        "Medical expenses": "Life - Medical expenses",
        "Insurance": "Life - Insurance",
        "Taxes": "Life - Taxes",
        "Gifts": "Life - Gifts",
        "Electronics": "Home - Electronics",
        "Furniture": "Home - Furniture",
        "Household supplies": "Home - Household supplies",
        "Services": "Home - Services",
        "Movies": "Entertainment - Movies",
        "Music": "Entertainment - Music",
        "Sports": "Entertainment - Sports",
        "Games": "Entertainment - Games",
        "General": "Uncategorized - General",
    }

    # Normalize actual spending to match budget categories
    normalized_actual = {}
    for category, amount in actual.items():
        # Check if it needs mapping
        budget_category = category_mapping.get(category, category)
        if budget_category in normalized_actual:
            normalized_actual[budget_category] += amount
        else:
            normalized_actual[budget_category] = amount

    # Combine budget and actual
    all_categories = set(list(budget.keys()) + list(normalized_actual.keys()))

    data = []
    for category in sorted(all_categories):
        budget_amt = budget.get(category, 0.0)
        actual_amt = normalized_actual.get(category, 0.0)

        variance = actual_amt - budget_amt
        variance_pct = (variance / budget_amt * 100) if budget_amt > 0 else 0.0

        status = "✓ Under Budget" if variance <= 0 else "✗ Over Budget"

        data.append(
            {
                "Category": category,
                "Budget": budget_amt,
                "Actual": actual_amt,
                "Variance": variance,
                "Variance %": variance_pct,
                "Status": status,
            }
        )

    result = pd.DataFrame(data)

    # Round numeric columns
    result["Budget"] = result["Budget"].round(2)
    result["Actual"] = result["Actual"].round(2)
    result["Variance"] = result["Variance"].round(2)
    result["Variance %"] = result["Variance %"].round(2)

    # Sort by variance (most over budget first)
    result = result.sort_values("Variance", ascending=False)

    # Add total row
    total_budget = result["Budget"].sum()
    total_actual = result["Actual"].sum()
    total_variance = total_actual - total_budget
    total_variance_pct = (
        (total_variance / total_budget * 100) if total_budget > 0 else 0.0
    )

    total_row = pd.DataFrame(
        [
            {
                "Category": "TOTAL",
                "Budget": total_budget,
                "Actual": total_actual,
                "Variance": total_variance,
                "Variance %": total_variance_pct,
                "Status": "✓ Under Budget" if total_variance <= 0 else "✗ Over Budget",
            }
        ]
    )

    result = pd.concat([result, total_row], ignore_index=True)

    return result


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Generate budget summary and analysis sheets",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate all summaries for 2026
  python src/export/generate_summaries.py --year 2026
  
  # With custom budget file
  python src/export/generate_summaries.py --year 2026 --budget config/budget_2026.json
  
  # Dry run to preview
  python src/export/generate_summaries.py --year 2026 --dry-run
        """,
    )

    parser.add_argument(
        "--year", type=int, required=True, help="Year to analyze (e.g., 2026)"
    )
    parser.add_argument(
        "--budget",
        default=DEFAULT_BUDGET_FILE,
        help=f"Path to budget JSON file (default: {DEFAULT_BUDGET_FILE})",
    )
    parser.add_argument(
        "--sheet-key",
        default=os.getenv("SPREADSHEET_KEY"),
        help="Google Sheets spreadsheet key (defaults to SPREADSHEET_KEY env var)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview summaries without writing to sheets",
    )

    args = parser.parse_args()

    if not args.sheet_key and not args.dry_run:
        raise ValueError(
            "--sheet-key must be provided (or set SPREADSHEET_KEY env var)"
        )

    # Fetch transaction data
    df = fetch_transactions_for_analysis(args.year)

    if df.empty:
        print(f"No transactions found for {args.year}")
        return 1

    print(f"\n{'='*60}")
    print(f"Generating Budget Summaries for {args.year}")
    print(f"{'='*60}\n")

    # Generate summaries
    monthly_summary = generate_monthly_summary(df, args.year)
    category_breakdown = generate_category_breakdown(df, args.year)
    monthly_trends = generate_monthly_trends(df, args.year)
    category_monthly = generate_category_monthly_breakdown(df, args.year)

    # Load budget and generate budget vs actual
    budget = load_budget(args.budget)
    budget_vs_actual = generate_budget_vs_actual(df, args.year, budget)

    if args.dry_run:
        print("\n" + "=" * 60)
        print("DRY RUN MODE - Preview Only")
        print("=" * 60)

        print(f"\n{WORKSHEET_MONTHLY_SUMMARY}:")
        print(monthly_summary.to_string(index=False))

        print(f"\n{WORKSHEET_CATEGORY_BREAKDOWN}:")
        print(category_breakdown.to_string(index=False))

        print(f"\n{WORKSHEET_MONTHLY_TRENDS}:")
        print(monthly_trends.to_string(index=False))

        print(f"\nCategory x Month Breakdown:")
        print(category_monthly.to_string(index=False))

        if not budget_vs_actual.empty:
            print(f"\n{WORKSHEET_BUDGET_VS_ACTUAL}:")
            print(budget_vs_actual.to_string(index=False))

        print("\n" + "=" * 60)
        return 0

    # Write to Google Sheets (update existing months, append new ones)
    print("Writing summaries to Google Sheets...\n")

    db = DatabaseManager()
    updated_count = 0
    appended_count = 0
    unchanged_count = 0

    # Process each month in the summary
    gc = None
    worksheet = None

    for _, row in monthly_summary.iterrows():
        year_month = str(row["Month"])

        # Get existing summary from database
        existing = db.get_monthly_summary(year_month)

        # Check if data changed
        data_changed = False
        if existing:
            # Compare numeric values with tolerance
            if (
                abs(existing["total_spent_net"] - row["Total Spent (Net)"]) > 0.01
                or abs(existing["avg_transaction"] - row["Avg Transaction"]) > 0.01
                or existing["transaction_count"] != row["Transaction Count"]
                or abs(existing["total_paid"] - row["Total Paid"]) > 0.01
                or abs(existing["total_owed"] - row["Total Owed"]) > 0.01
                or abs(existing["cumulative_spending"] - row["Cumulative Spending"])
                > 0.01
                or abs(existing["mom_change"] - row["MoM Change"]) > 0.01
            ):
                data_changed = True
        else:
            # New month
            data_changed = True

        if data_changed:
            # Save to database
            db.save_monthly_summary(
                year_month=year_month,
                total_spent_net=row["Total Spent (Net)"],
                avg_transaction=row["Avg Transaction"],
                transaction_count=int(row["Transaction Count"]),
                total_paid=row["Total Paid"],
                total_owed=row["Total Owed"],
                cumulative_spending=row["Cumulative Spending"],
                mom_change=row["MoM Change"],
                written_to_sheet=False,
            )

            # Update or append to sheets
            if not gc:
                gc = pygsheets.authorize(service_file=SHEETS_AUTHENTICATION_FILE)
                sheet = gc.open_by_key(args.sheet_key)
                try:
                    worksheet = sheet.worksheet_by_title(WORKSHEET_MONTHLY_SUMMARY)
                except pygsheets.WorksheetNotFound:
                    # Create worksheet if it doesn't exist
                    worksheet = sheet.add_worksheet(WORKSHEET_MONTHLY_SUMMARY)
                    # Write header
                    worksheet.update_row(1, list(monthly_summary.columns))

            # Check if month exists in sheet
            all_months = worksheet.get_col(1, include_tailing_empty=False)[
                1:
            ]  # Skip header

            if year_month in all_months:
                # Update existing row
                row_idx = (
                    all_months.index(year_month) + 2
                )  # +1 for 0-index, +1 for header
                row_values = [row[col] for col in monthly_summary.columns]
                worksheet.update_row(row_idx, row_values)
                updated_count += 1
            else:
                # Append new row
                row_values = [row[col] for col in monthly_summary.columns]
                worksheet.append_table(
                    values=[row_values], start="A1", end=None, dimension="ROWS"
                )
                appended_count += 1

            # Mark as written in database
            db.mark_monthly_summary_written(year_month)
        else:
            unchanged_count += 1

    # Summary message
    if updated_count > 0 or appended_count > 0:
        msg_parts = []
        if updated_count > 0:
            msg_parts.append(f"{updated_count} updated")
        if appended_count > 0:
            msg_parts.append(f"{appended_count} appended")
        if unchanged_count > 0:
            msg_parts.append(f"{unchanged_count} unchanged")
        print(f"✓ {WORKSHEET_MONTHLY_SUMMARY}: {', '.join(msg_parts)}")
    else:
        print(
            f"✓ {WORKSHEET_MONTHLY_SUMMARY}: No changes needed ({unchanged_count} unchanged)"
        )

    url = f"https://docs.google.com/spreadsheets/d/{args.sheet_key}"
    print(f"   {url}")

    print(f"\n{'='*60}")
    print("Summary generation complete!")
    print(f"{'='*60}\n")

    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
