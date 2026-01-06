#!/usr/bin/env python3
"""
Apply feedback from merchant review to update configurations.

This script:
1. Reads merchant_review_feedback.json
2. Updates merchant_category_lookup.json with corrected entries
3. Generates a report of changes
4. Moves reviewed entries to done_merchant_names_for_review.csv
"""

import json
import pandas as pd
from pathlib import Path
from typing import Dict, List
from collections import defaultdict
from src.common.utils import LOG, PROJECT_ROOT

# File paths
FEEDBACK_FILE = (
    Path(PROJECT_ROOT) / "data" / "processed" / "merchant_review_feedback.json"
)
MERCHANT_LOOKUP_FILE = Path(PROJECT_ROOT) / "config" / "merchant_category_lookup.json"
REVIEW_FILE = (
    Path(PROJECT_ROOT) / "data" / "processed" / "merchant_names_for_review.csv"
)
DONE_REVIEW_FILE = (
    Path(PROJECT_ROOT) / "data" / "processed" / "done_merchant_names_for_review.csv"
)
AMEX_CATEGORY_MAPPING = Path(PROJECT_ROOT) / "config" / "amex_category_mapping.json"


def load_feedback() -> Dict:
    """Load feedback from review session."""
    if not FEEDBACK_FILE.exists():
        LOG.error(f"Feedback file not found: {FEEDBACK_FILE}")
        return {"approved": [], "corrected": [], "skipped": []}

    with open(FEEDBACK_FILE, "r") as f:
        return json.load(f)


def load_merchant_lookup() -> Dict:
    """Load existing merchant lookup."""
    if MERCHANT_LOOKUP_FILE.exists():
        with open(MERCHANT_LOOKUP_FILE, "r") as f:
            return json.load(f)
    return {}


def save_merchant_lookup(lookup: Dict):
    """Save updated merchant lookup."""
    with open(MERCHANT_LOOKUP_FILE, "w") as f:
        json.dump(lookup, f, indent=2, sort_keys=True)
    LOG.info(f"Updated merchant lookup: {MERCHANT_LOOKUP_FILE}")


def normalize_merchant_key(merchant: str) -> str:
    """Normalize merchant name for use as lookup key."""
    if not merchant or not isinstance(merchant, str):
        return ""
    return merchant.lower().strip()


def apply_corrections(feedback: Dict, dry_run: bool = False) -> Dict:
    """Apply corrections from feedback to merchant lookup.

    Args:
        feedback: Feedback dictionary with approved and corrected entries
        dry_run: If True, don't actually save changes

    Returns:
        Dictionary with statistics about changes made
    """
    lookup = load_merchant_lookup()

    stats = {"added": 0, "updated": 0, "unchanged": 0, "changes": []}

    # Process approved entries - add them as-is
    for entry in feedback["approved"]:
        merchant_name = entry.get("expected_merchant") or entry.get("description")
        if not merchant_name:
            continue
        key = normalize_merchant_key(merchant_name)
        if not key:
            continue

        if key not in lookup:
            lookup[key] = {
                "category": entry["category_name"],
                "subcategory": entry["subcategory_name"],
                "canonical_name": entry["expected_merchant"],
            }
            stats["added"] += 1
            stats["changes"].append(
                {
                    "action": "added",
                    "merchant": entry["expected_merchant"],
                    "corrected_merchant": entry["expected_merchant"],
                    "new_category": entry["category_name"],
                    "new_subcategory": entry["subcategory_name"],
                }
            )
        else:
            stats["unchanged"] += 1

    # Process corrected entries - update with corrections
    for entry in feedback["corrected"]:
        # Use the corrected merchant name as the key
        merchant_name = entry.get("corrected_merchant") or entry.get("description")
        if not merchant_name:
            continue
        key = normalize_merchant_key(merchant_name)
        if not key:
            continue

        old_entry = lookup.get(key, {})
        new_entry = {
            "category": entry["corrected_category"],
            "subcategory": entry["corrected_subcategory"],
            "canonical_name": entry["corrected_merchant"],
        }

        if key in lookup:
            stats["updated"] += 1
            action = "updated"
        else:
            stats["added"] += 1
            action = "added"

        lookup[key] = new_entry

        stats["changes"].append(
            {
                "action": action,
                "merchant": entry["expected_merchant"],
                "corrected_merchant": entry["corrected_merchant"],
                "old_category": old_entry.get("category", "N/A"),
                "new_category": entry["corrected_category"],
                "old_subcategory": old_entry.get("subcategory", "N/A"),
                "new_subcategory": entry["corrected_subcategory"],
            }
        )

    if not dry_run:
        save_merchant_lookup(lookup)

    return stats


def move_reviewed_to_done(feedback: Dict):
    """Move reviewed entries to done file."""
    if not REVIEW_FILE.exists():
        LOG.warning(f"Review file not found: {REVIEW_FILE}")
        return

    df_review = pd.read_csv(REVIEW_FILE)

    # Get all reviewed description_raw values
    reviewed_descriptions = set()
    for entry in feedback["approved"] + feedback["corrected"]:
        reviewed_descriptions.add(entry["description_raw"])

    # Split into done and remaining
    df_done = df_review[df_review["description_raw"].isin(reviewed_descriptions)]
    df_remaining = df_review[~df_review["description_raw"].isin(reviewed_descriptions)]

    # Append to done file
    if not df_done.empty:
        if DONE_REVIEW_FILE.exists():
            df_existing_done = pd.read_csv(DONE_REVIEW_FILE)
            df_done = pd.concat([df_existing_done, df_done], ignore_index=True)

        df_done.to_csv(DONE_REVIEW_FILE, index=False)
        LOG.info(f"Moved {len(df_done)} reviewed entries to: {DONE_REVIEW_FILE}")

    # Update review file with remaining
    if not df_remaining.empty:
        df_remaining.to_csv(REVIEW_FILE, index=False)
        LOG.info(f"Remaining entries in review file: {len(df_remaining)}")
    else:
        # All done! Remove the review file
        REVIEW_FILE.unlink()
        LOG.info("All entries reviewed! Removed review file.")


def generate_report(stats: Dict):
    """Generate a human-readable report of changes."""
    print("\n" + "=" * 80)
    print("FEEDBACK APPLICATION REPORT")
    print("=" * 80)

    print(f"\nSummary:")
    print(f"  Added:     {stats['added']} new merchant mappings")
    print(f"  Updated:   {stats['updated']} existing mappings")
    print(f"  Unchanged: {stats['unchanged']} approved existing mappings")
    print(f"  Total:     {stats['added'] + stats['updated']} changes applied")

    if stats["changes"]:
        print(f"\n{'─'*80}")
        print("Recent Changes:")
        print(f"{'─'*80}")

        # Group by action
        by_action = defaultdict(list)
        for change in stats["changes"]:
            by_action[change["action"]].append(change)

        if "added" in by_action:
            print(f"\n✓ Added ({len(by_action['added'])} merchants):")
            for change in by_action["added"][:10]:  # Show first 10
                merchant = change.get("corrected_merchant", change["merchant"])
                print(f"  • {merchant}")
                print(f"    → {change['new_category']} / {change['new_subcategory']}")
            if len(by_action["added"]) > 10:
                print(f"  ... and {len(by_action['added']) - 10} more")

        if "updated" in by_action:
            print(f"\n✓ Updated ({len(by_action['updated'])} merchants):")
            for change in by_action["updated"][:10]:  # Show first 10
                print(f"  • {change['merchant']} → {change['corrected_merchant']}")
                if change["old_category"] != change["new_category"]:
                    print(
                        f"    Category: {change['old_category']} → {change['new_category']}"
                    )
                if change["old_subcategory"] != change["new_subcategory"]:
                    print(
                        f"    Subcategory: {change['old_subcategory']} → {change['new_subcategory']}"
                    )
            if len(by_action["updated"]) > 10:
                print(f"  ... and {len(by_action['updated']) - 10} more")

    print(f"\n{'='*80}")


def analyze_correction_patterns(feedback: Dict):
    """Analyze patterns in corrections to suggest algorithm improvements."""
    if not feedback["corrected"]:
        return

    print("\n" + "=" * 80)
    print("CORRECTION PATTERNS ANALYSIS")
    print("=" * 80)

    # Common mistakes
    mistakes = defaultdict(int)
    category_changes = defaultdict(int)

    for entry in feedback["corrected"]:
        original = entry["expected_merchant"]
        corrected = entry["corrected_merchant"]

        # Track if merchant name changed
        if original != corrected:
            mistakes["merchant_name_wrong"] += 1

        # Track category changes
        if entry["category_name"] != entry["corrected_category"]:
            category_changes[
                f"{entry['category_name']} → {entry['corrected_category']}"
            ] += 1

    print(f"\nCommon Issues:")
    print(f"  Merchant name corrections: {mistakes['merchant_name_wrong']}")

    if category_changes:
        print(f"\n  Category changes:")
        for change, count in sorted(category_changes.items(), key=lambda x: -x[1])[:5]:
            print(f"    • {change}: {count} times")

    print(f"\n{'─'*80}")
    print("Recommendations:")
    print("  1. Review merchant name extraction rules in utils.py")
    print("  2. Update category mapping rules if needed")
    print("  3. Consider adding more merchant patterns to config")
    print("=" * 80)


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Apply feedback from merchant review to update configurations"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be changed without actually updating files",
    )
    parser.add_argument(
        "--analyze",
        action="store_true",
        help="Analyze correction patterns to suggest improvements",
    )

    args = parser.parse_args()

    feedback = load_feedback()

    if not feedback["approved"] and not feedback["corrected"]:
        print("\n⚠ No feedback to apply yet.")
        print("Run: python src/review_merchants.py")
        return

    print(f"\nLoaded feedback:")
    print(f"  Approved:  {len(feedback['approved'])} entries")
    print(f"  Corrected: {len(feedback['corrected'])} entries")
    print(f"  Skipped:   {len(feedback['skipped'])} entries")

    if args.dry_run:
        print("\n🔍 DRY RUN - No changes will be saved")

    # Apply corrections
    stats = apply_corrections(feedback, dry_run=args.dry_run)

    # Generate report
    generate_report(stats)

    # Analyze patterns
    if args.analyze:
        analyze_correction_patterns(feedback)

    # Move reviewed entries
    if not args.dry_run:
        move_reviewed_to_done(feedback)
        print(f"\n✓ All changes applied successfully!")
        print(f"\nNext steps:")
        print(f"  1. Review the changes in: {MERCHANT_LOOKUP_FILE}")
        print(f"  2. Re-run the pipeline to apply new mappings")
        print(f"  3. Continue reviewing remaining merchants if any")
    else:
        print(f"\n💡 Run without --dry-run to apply these changes")


if __name__ == "__main__":
    main()
