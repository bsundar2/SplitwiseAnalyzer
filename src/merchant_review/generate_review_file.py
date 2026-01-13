#!/usr/bin/env python3
"""Generate merchant review file from processed transactions.

This script creates merchant_names_for_review.csv from the processed
transaction data, filtering out merchants that are already in the lookup.
"""

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.common.utils import LOG

PROJECT_ROOT = Path(__file__).parent.parent.parent
DEFAULT_PROCESSED_CSV = "jan2026.csv.processed.csv"
DEFAULT_REVIEW_FILE = "merchant_names_for_review.csv"
DEFAULT_FULL_REVIEW_FILE = "merchant_names_full_review.csv"


def generate_review_file(
    processed_csv: str, include_known: bool = False, output_file: str = None
):
    """Generate the merchant review file.

    Args:
        processed_csv: Path to the processed CSV file (relative to data/processed/ or absolute)
        include_known: If True, include all merchants (even those in lookup).
                      If False, only include merchants not yet in lookup.
        output_file: Optional custom output path. If None, uses default based on include_known.
    """
    # Resolve processed CSV path
    processed_path = Path(processed_csv)
    if not processed_path.is_absolute():
        processed_path = PROJECT_ROOT / "data" / "processed" / processed_csv

    if not processed_path.exists():
        LOG.error(f"Processed CSV not found: {processed_path}")
        LOG.error(
            "Run the pipeline first: python src/import_statement/pipeline.py --statement <path> --dry-run"
        )
        return False

    # Resolve output file path
    if output_file:
        output_path = Path(output_file)
        if not output_path.is_absolute():
            output_path = PROJECT_ROOT / "data" / "processed" / output_file
    else:
        default_name = (
            DEFAULT_FULL_REVIEW_FILE if include_known else DEFAULT_REVIEW_FILE
        )
        output_path = PROJECT_ROOT / "data" / "processed" / default_name

    # Load merchant lookup
    merchant_lookup_path = PROJECT_ROOT / "config" / "merchant_category_lookup.json"
    merchant_lookup = {}
    if merchant_lookup_path.exists():
        with open(merchant_lookup_path, "r") as f:
            merchant_lookup = json.load(f)
        LOG.info(f"Loaded {len(merchant_lookup)} merchants from lookup")

    # Load processed transactions
    df_proc = pd.read_csv(processed_path)
    LOG.info(f"Loaded {len(df_proc)} processed transactions")

    # Load merchant lookup
    merchant_lookup_path = PROJECT_ROOT / "config" / "merchant_category_lookup.json"
    merchant_lookup = {}
    if merchant_lookup_path.exists():
        with open(merchant_lookup_path, "r") as f:
            merchant_lookup = json.load(f)
        LOG.info(f"Loaded {len(merchant_lookup)} merchants from lookup")

    # Get unique merchants
    unique_merchants = df_proc[
        [
            "date",
            "amount",
            "description",
            "description_raw",
            "category_name",
            "subcategory_name",
        ]
    ].copy()
    unique_merchants = unique_merchants.drop_duplicates(subset=["description"])
    LOG.info(f"Found {len(unique_merchants)} unique merchants")

    # Create review data
    review_data = []
    for _, row in unique_merchants.iterrows():
        merchant_lower = str(row["description"]).lower()
        in_lookup = merchant_lower in merchant_lookup

        if include_known or not in_lookup:
            review_data.append(
                {
                    "date": row["date"],
                    "amount": row["amount"],
                    "description": row["description"],
                    "expected_merchant": "",
                    "category_name": row["category_name"],
                    "expected_category": row["category_name"],
                    "subcategory_name": row["subcategory_name"],
                    "expected_subcategory": row["subcategory_name"],
                    "description_raw": row["description_raw"],
                }
            )

    review_df = pd.DataFrame(review_data)

    # Save to file
    review_df.to_csv(output_path, index=False)

    already_known = len(unique_merchants) - len(review_df)
    LOG.info(f"Created {output_path}")
    LOG.info(f"  Total merchants: {len(review_df)}")
    if not include_known:
        LOG.info(f"  Already in lookup: {already_known}")

    return True


def main():
    parser = argparse.ArgumentParser(
        description="Generate merchant review file from processed transactions"
    )
    parser.add_argument(
        "--processed-csv",
        "-i",
        required=True,
        help="Path to processed CSV file (relative to data/processed/ or absolute path)",
    )
    parser.add_argument(
        "--output",
        "-o",
        required=True,
        help="Output file path (relative to data/processed/ or absolute path)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Include all merchants (even those already in lookup)",
    )

    args = parser.parse_args()

    success = generate_review_file(
        processed_csv=args.processed_csv,
        include_known=args.all,
        output_file=args.output,
    )

    if success:
        print(f"\n✓ Generated review file: {args.output}")
        print("\nTo start reviewing:")
        print("  python src/merchant_review/review_merchants.py --batch 30")
    else:
        print("\n✗ Failed to generate review file")
        return 1

    return 0


if __name__ == "__main__":
    exit(main())
