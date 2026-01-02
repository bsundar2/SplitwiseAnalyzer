#!/usr/bin/env python3
"""
Interactive review tool for merchant names and categories.

Loads the merchant_names_for_review.csv and allows you to:
1. Approve the extracted merchant name and category
2. Correct the merchant name and/or category
3. Skip to the next entry

Your feedback is saved to merchant_review_feedback.json which can be used to:
- Update merchant_category_lookup.json with your corrections
- Improve the extraction algorithm
"""

import os
import json
import pandas as pd
from pathlib import Path
from typing import Optional, Dict, List, Tuple
from src.utils import LOG, PROJECT_ROOT

# File paths
REVIEW_FILE = Path(PROJECT_ROOT) / "data" / "processed" / "merchant_names_for_review.csv"
FEEDBACK_FILE = Path(PROJECT_ROOT) / "data" / "processed" / "merchant_review_feedback.json"
DONE_REVIEW_FILE = Path(PROJECT_ROOT) / "data" / "processed" / "done_merchant_names_for_review.csv"
MERCHANT_LOOKUP_FILE = Path(PROJECT_ROOT) / "config" / "merchant_category_lookup.json"
AMEX_CATEGORY_MAPPING_FILE = Path(PROJECT_ROOT) / "config" / "amex_category_mapping.json"

# Valid category/subcategory combinations
VALID_CATEGORY_SUBCATEGORIES = {
    "Transportation": ["Taxi", "Bus/train", "Car", "Gas/fuel", "Plane", "Parking", "Hotel", "Other"],
    "Food and drink": ["Groceries", "Dining out"],
    "Utilities": ["TV/Phone/Internet"],
    "Life": ["Medical expenses", "Clothing", "Insurance", "Gifts", "Education", "Other"],
    "Entertainment": ["Movies", "Sports", "Other"],
    "Home": ["Electronics", "Household supplies", "Furniture", "Services", "Other"],
    "Uncategorized": ["General"],
    "General": ["General"],
    "Other": ["Other"]
}


def load_review_data() -> pd.DataFrame:
    """Load the merchant names for review."""
    if not REVIEW_FILE.exists():
        LOG.error(f"Review file not found: {REVIEW_FILE}")
        LOG.info("Run the pipeline first to generate merchant review data")
        return pd.DataFrame()
    
    df = pd.read_csv(REVIEW_FILE)
    LOG.info(f"Loaded {len(df)} transactions for review")
    return df


def load_feedback() -> Dict:
    """Load existing feedback if available."""
    if FEEDBACK_FILE.exists():
        with open(FEEDBACK_FILE, "r") as f:
            return json.load(f)
    return {"approved": [], "corrected": [], "skipped": []}


def save_feedback(feedback: Dict):
    """Save feedback to JSON file."""
    with open(FEEDBACK_FILE, "w") as f:
        json.dump(feedback, f, indent=2)
    LOG.info(f"Saved feedback to {FEEDBACK_FILE}")


def load_merchant_lookup() -> Dict:
    """Load merchant category lookup."""
    if MERCHANT_LOOKUP_FILE.exists():
        with open(MERCHANT_LOOKUP_FILE, "r") as f:
            return json.load(f)
    return {}


def validate_category_subcategory(category: str, subcategory: str) -> Tuple[bool, Optional[str]]:
    """Validate that subcategory belongs to the category.
    
    Returns:
        Tuple of (is_valid, error_message)
    """
    if category not in VALID_CATEGORY_SUBCATEGORIES:
        return False, f"Invalid category: '{category}'"
    
    valid_subcats = VALID_CATEGORY_SUBCATEGORIES[category]
    if subcategory not in valid_subcats:
        return False, f"'{subcategory}' is not valid for category '{category}'. Valid options: {', '.join(valid_subcats)}"
    
    return True, None


def detect_lodging_in_description(description_raw: str) -> bool:
    """Detect if LODGING appears in the Amex statement description."""
    return "LODGING" in description_raw.upper()


def display_transaction(row: pd.Series, index: int, total: int):
    """Display a transaction for review."""
    print("\n" + "="*80)
    print(f"Transaction {index + 1} of {total}")
    print("="*80)
    print(f"\nDate:        {row['date']}")
    print(f"Amount:      ${row['amount']:.2f}")
    print(f"\nRaw Description:\n{row['description_raw'][:200]}")
    if len(row['description_raw']) > 200:
        print("... (truncated)")
    print(f"\n{'─'*80}")
    print(f"Extracted Merchant:  {row['expected_merchant']}")
    print(f"Current Category:    {row['category_name']}")
    print(f"Current Subcategory: {row['subcategory_name']}")
    
    # Validate category/subcategory combination
    is_valid, error_msg = validate_category_subcategory(row['category_name'], row['subcategory_name'])
    if not is_valid:
        print(f"\n⚠️  WARNING: {error_msg}")
    
    # Check if LODGING should be categorized as Hotel
    if detect_lodging_in_description(row['description_raw']):
        if row['subcategory_name'] != "Hotel":
            print(f"\n💡 SUGGESTION: This appears to be LODGING - should be 'Transportation > Hotel'")
    
    print("="*80)


def get_user_input(prompt: str, options: Optional[List[str]] = None) -> str:
    """Get validated user input."""
    while True:
        response = input(prompt).strip()
        if not options or response in options:
            return response
        print(f"Invalid input. Please choose from: {', '.join(options)}")


def interactive_review(start_index: int = 0, batch_size: Optional[int] = None):
    """Start interactive review session."""
    df = load_review_data()
    if df.empty:
        return
    
    feedback = load_feedback()
    
    # Filter out already reviewed items
    reviewed_descriptions = set()
    for item in feedback["approved"] + feedback["corrected"] + feedback["skipped"]:
        reviewed_descriptions.add(item.get("description_raw", ""))
    
    # Get unique merchants to review (group by expected_merchant and description_raw)
    df_unique = df.drop_duplicates(subset=["expected_merchant", "description_raw"])
    
    # Filter out already reviewed
    df_to_review = df_unique[~df_unique["description_raw"].isin(reviewed_descriptions)]
    
    total = len(df_to_review)
    if total == 0:
        print("\n✓ All transactions have been reviewed!")
        print(f"Total reviewed: {len(feedback['approved']) + len(feedback['corrected'])} transactions")
        print(f"  - Approved: {len(feedback['approved'])}")
        print(f"  - Corrected: {len(feedback['corrected'])}")
        print(f"  - Skipped: {len(feedback['skipped'])}")
        return
    
    LOG.info(f"Found {total} unique merchants to review")
    LOG.info(f"Already reviewed: {len(reviewed_descriptions)} merchants")
    
    # Apply batch size if specified
    end_index = min(start_index + batch_size, total) if batch_size else total
    
    print(f"\n{'='*80}")
    print(f"MERCHANT REVIEW SESSION")
    print(f"{'='*80}")
    print(f"\nReviewing transactions {start_index + 1} to {end_index} of {total}")
    print("\nInstructions:")
    print("  [a] Approve - The extracted merchant and category are correct")
    print("  [c] Correct - Fix the merchant name and/or category")
    print("  [s] Skip - Skip this transaction for now")
    print("  [q] Quit - Save progress and exit")
    print("  [h] Help - Show these instructions again")
    
    for idx in range(start_index, end_index):
        row = df_to_review.iloc[idx]
        
        display_transaction(row, idx, total)
        
        action = get_user_input("\nAction [a/c/s/q/h]: ", ["a", "c", "s", "q", "h"])
        
        if action == "h":
            print("\nInstructions:")
            print("  [a] Approve - The extracted merchant and category are correct")
            print("  [c] Correct - Fix the merchant name and/or category")
            print("  [s] Skip - Skip this transaction for now")
            print("  [q] Quit - Save progress and exit")
            # Re-prompt for same transaction
            idx -= 1
            continue
        
        if action == "q":
            print("\n✓ Saving progress and exiting...")
            save_feedback(feedback)
            return
        
        entry = {
            "description_raw": row["description_raw"],
            "description": row["description"],
            "expected_merchant": row["expected_merchant"],
            "category_name": row["category_name"],
            "subcategory_name": row["subcategory_name"],
            "date": row["date"],
            "amount": float(row["amount"]),
        }
        
        if action == "a":
            # Approve
            feedback["approved"].append(entry)
            print("✓ Approved")
        
        elif action == "c":
            # Correct
            print("\nProvide corrections (press Enter to keep current value):")
            
            corrected_merchant = get_user_input(
                f"Merchant name [{row['expected_merchant']}]: "
            )
            corrected_merchant = corrected_merchant or row["expected_merchant"]
            
            corrected_category = get_user_input(
                f"Category [{row['category_name']}]: "
            )
            corrected_category = corrected_category or row["category_name"]
            
            corrected_subcategory = get_user_input(
                f"Subcategory [{row['subcategory_name']}]: "
            )
            corrected_subcategory = corrected_subcategory or row["subcategory_name"]
            
            # Validate the corrected category/subcategory combination
            is_valid, error_msg = validate_category_subcategory(corrected_category, corrected_subcategory)
            if not is_valid:
                print(f"\n⚠️  ERROR: {error_msg}")
                print("Please correct the category/subcategory.")
                print(f"\nValid categories: {', '.join(VALID_CATEGORY_SUBCATEGORIES.keys())}")
                if corrected_category in VALID_CATEGORY_SUBCATEGORIES:
                    valid_subcats = VALID_CATEGORY_SUBCATEGORIES[corrected_category]
                    print(f"Valid subcategories for '{corrected_category}': {', '.join(valid_subcats)}")
                print("\n[r] Re-enter corrections")
                print("[s] Skip this transaction")
                choice = get_user_input("Choice [r/s]: ", ["r", "s"])
                if choice == "r":
                    idx -= 1  # Re-do this transaction
                    continue
                elif choice == "s":
                    feedback["skipped"].append(entry)
                    print("⊘ Skipped")
                    continue
            
            entry["corrected_merchant"] = corrected_merchant
            entry["corrected_category"] = corrected_category
            entry["corrected_subcategory"] = corrected_subcategory
            
            feedback["corrected"].append(entry)
            print("✓ Correction saved")
        
        elif action == "s":
            # Skip
            feedback["skipped"].append(entry)
            print("⊘ Skipped")
        
        # Auto-save every 10 transactions
        if (idx + 1) % 10 == 0:
            save_feedback(feedback)
            print(f"\n💾 Auto-saved progress ({idx + 1}/{total})")
    
    # Final save
    save_feedback(feedback)
    
    print(f"\n{'='*80}")
    print("REVIEW SESSION COMPLETE")
    print(f"{'='*80}")
    print(f"\nReviewed: {end_index - start_index} transactions")
    print(f"  - Approved: {len([f for f in feedback['approved']])} (new this session)")
    print(f"  - Corrected: {len([f for f in feedback['corrected']])} (new this session)")
    print(f"  - Skipped: {len([f for f in feedback['skipped']])} (new this session)")
    print(f"\nFeedback saved to: {FEEDBACK_FILE}")
    print(f"\nRemaining: {total - end_index} transactions")
    
    if total > end_index:
        print(f"\nTo continue reviewing, run:")
        print(f"  python src/review_merchants.py --start {end_index}")


def main():
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Interactive review tool for merchant names and categories"
    )
    parser.add_argument(
        "--start",
        type=int,
        default=0,
        help="Start index for review (default: 0)"
    )
    parser.add_argument(
        "--batch",
        type=int,
        default=None,
        help="Number of transactions to review in this session (default: all)"
    )
    parser.add_argument(
        "--stats",
        action="store_true",
        help="Show review statistics and exit"
    )
    
    args = parser.parse_args()
    
    if args.stats:
        feedback = load_feedback()
        print(f"\n{'='*80}")
        print("REVIEW STATISTICS")
        print(f"{'='*80}")
        print(f"Approved: {len(feedback['approved'])}")
        print(f"Corrected: {len(feedback['corrected'])}")
        print(f"Skipped: {len(feedback['skipped'])}")
        print(f"Total reviewed: {len(feedback['approved']) + len(feedback['corrected'])}")
        
        if feedback["corrected"]:
            print(f"\nRecent corrections:")
            for item in feedback["corrected"][-5:]:
                print(f"  {item['expected_merchant']} → {item['corrected_merchant']}")
                print(f"    Category: {item['category_name']} → {item['corrected_category']}")
        return
    
    interactive_review(start_index=args.start, batch_size=args.batch)


if __name__ == "__main__":
    main()
