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

from src.utils import LOG

PROJECT_ROOT = Path(__file__).parent.parent
PROCESSED_CSV = PROJECT_ROOT / "data" / "processed" / "amex2025.csv.processed.csv"
REVIEW_FILE = PROJECT_ROOT / "data" / "processed" / "merchant_names_for_review.csv"
FULL_REVIEW_FILE = PROJECT_ROOT / "data" / "processed" / "merchant_names_full_review.csv"
MERCHANT_LOOKUP = PROJECT_ROOT / "config" / "merchant_category_lookup.json"


def generate_review_file(include_known: bool = False):
    """Generate the merchant review file.
    
    Args:
        include_known: If True, include all merchants (even those in lookup).
                      If False, only include merchants not yet in lookup.
    """
    # Load processed transactions
    if not PROCESSED_CSV.exists():
        LOG.error(f"Processed CSV not found: {PROCESSED_CSV}")
        LOG.error("Run the pipeline first: python src/pipeline.py --statement data/raw/amex2025.csv --dry-run")
        return False
    
    df_proc = pd.read_csv(PROCESSED_CSV)
    LOG.info(f"Loaded {len(df_proc)} processed transactions")
    
    # Load merchant lookup
    merchant_lookup = {}
    if MERCHANT_LOOKUP.exists():
        with open(MERCHANT_LOOKUP, 'r') as f:
            merchant_lookup = json.load(f)
        LOG.info(f"Loaded {len(merchant_lookup)} merchants from lookup")
    
    # Get unique merchants
    unique_merchants = df_proc[['date', 'amount', 'description', 'description_raw', 
                                  'category_name', 'subcategory_name']].copy()
    unique_merchants = unique_merchants.drop_duplicates(subset=['description'])
    LOG.info(f"Found {len(unique_merchants)} unique merchants")
    
    # Create review data
    review_data = []
    for _, row in unique_merchants.iterrows():
        merchant_lower = str(row['description']).lower()
        in_lookup = merchant_lower in merchant_lookup
        
        if include_known or not in_lookup:
            review_data.append({
                'date': row['date'],
                'amount': row['amount'],
                'description': row['description'],
                'expected_merchant': '',
                'category_name': row['category_name'],
                'expected_category': row['category_name'],
                'subcategory_name': row['subcategory_name'],
                'expected_subcategory': row['subcategory_name'],
                'description_raw': row['description_raw']
            })
    
    review_df = pd.DataFrame(review_data)
    
    # Save to file
    output_file = FULL_REVIEW_FILE if include_known else REVIEW_FILE
    review_df.to_csv(output_file, index=False)
    
    already_known = len(unique_merchants) - len(review_df)
    LOG.info(f"Created {output_file}")
    LOG.info(f"  Total merchants: {len(review_df)}")
    if not include_known:
        LOG.info(f"  Already in lookup: {already_known}")
    
    return True


def main():
    parser = argparse.ArgumentParser(
        description="Generate merchant review file from processed transactions"
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Include all merchants (even those already in lookup)"
    )
    
    args = parser.parse_args()
    
    success = generate_review_file(include_known=args.all)
    
    if success:
        if args.all:
            print(f"\n✓ Generated full review file: {FULL_REVIEW_FILE}")
        else:
            print(f"\n✓ Generated review file: {REVIEW_FILE}")
        print("\nTo start reviewing:")
        print("  python src/review_merchants.py --batch 30")
    else:
        print("\n✗ Failed to generate review file")
        return 1
    
    return 0


if __name__ == "__main__":
    exit(main())
