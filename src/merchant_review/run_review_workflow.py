#!/usr/bin/env python3
"""Run the complete merchant review workflow.

This script orchestrates the three-step merchant review process:
1. Generate review file from processed transactions
2. Interactive merchant review
3. Apply feedback to update merchant lookup
"""

import argparse
import subprocess
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.common.utils import LOG


def run_workflow(
    processed_csv: str,
    review_file: str = "merchant_names_for_review.csv",
    batch_size: int = 30,
    include_known: bool = False,
    skip_generation: bool = False,
    skip_review: bool = False,
    skip_apply: bool = False,
):
    """Run the complete merchant review workflow.

    Args:
        processed_csv: Path to processed CSV file
        review_file: Path for review file (default: merchant_names_for_review.csv)
        batch_size: Number of merchants to review at once
        include_known: Include merchants already in lookup
        skip_generation: Skip generation step (use existing review file)
        skip_review: Skip interactive review (use existing reviewed file)
        skip_apply: Skip applying feedback
    """
    PROJECT_ROOT = Path(__file__).parent.parent.parent

    # Step 1: Generate review file
    if not skip_generation:
        LOG.info("=" * 60)
        LOG.info("STEP 1: Generating merchant review file")
        LOG.info("=" * 60)

        cmd = [
            sys.executable,
            "src/merchant_review/generate_review_file.py",
            "--processed-csv",
            processed_csv,
            "--output",
            review_file,
        ]
        if include_known:
            cmd.append("--all")

        result = subprocess.run(cmd, cwd=PROJECT_ROOT)
        if result.returncode != 0:
            LOG.error("Failed to generate review file")
            return False
        LOG.info("Review file generated\n")
    else:
        LOG.info("Skipping generation step (using existing review file)\n")

    # Step 2: Interactive review
    if not skip_review:
        LOG.info("=" * 60)
        LOG.info("STEP 2: Interactive merchant review")
        LOG.info("=" * 60)

        cmd = [
            sys.executable,
            "src/merchant_review/review_merchants.py",
            "--batch",
            str(batch_size),
        ]

        result = subprocess.run(cmd, cwd=PROJECT_ROOT)
        if result.returncode != 0:
            LOG.error("Review process was interrupted or failed")
            return False
        LOG.info("Review completed\n")
    else:
        LOG.info("Skipping review step (using existing reviewed file)\n")

    # Step 3: Apply feedback
    if not skip_apply:
        LOG.info("=" * 60)
        LOG.info("STEP 3: Applying feedback to merchant lookup")
        LOG.info("=" * 60)

        cmd = [
            sys.executable,
            "src/merchant_review/apply_review_feedback.py",
        ]

        result = subprocess.run(cmd, cwd=PROJECT_ROOT)
        if result.returncode != 0:
            LOG.error("Failed to apply feedback")
            return False
        LOG.info("Feedback applied\n")
    else:
        LOG.info("Skipping apply step\n")

    LOG.info("=" * 60)
    LOG.info("WORKFLOW COMPLETE!")
    LOG.info("=" * 60)
    return True


def main():
    parser = argparse.ArgumentParser(
        description="Run the complete merchant review workflow",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Full workflow with default settings
  python src/merchant_review/run_review_workflow.py -i jan2026.csv.processed.csv
  
  # Review more merchants at once
  python src/merchant_review/run_review_workflow.py -i jan2026.csv.processed.csv --batch 50
  
  # Skip generation if review file already exists
  python src/merchant_review/run_review_workflow.py -i jan2026.csv.processed.csv --skip-generation
  
  # Include all merchants (even those already in lookup)
  python src/merchant_review/run_review_workflow.py -i jan2026.csv.processed.csv --all
        """,
    )
    parser.add_argument(
        "--processed-csv",
        "-i",
        required=True,
        help="Path to processed CSV file (relative to data/processed/ or absolute)",
    )
    parser.add_argument(
        "--review-file",
        "-o",
        default="merchant_names_for_review.csv",
        help="Review file name (default: merchant_names_for_review.csv)",
    )
    parser.add_argument(
        "--batch",
        "-b",
        type=int,
        default=30,
        help="Number of merchants to review at once (default: 30)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Include all merchants (even those already in lookup)",
    )
    parser.add_argument(
        "--skip-generation",
        action="store_true",
        help="Skip generation step (use existing review file)",
    )
    parser.add_argument(
        "--skip-review",
        action="store_true",
        help="Skip interactive review (use existing reviewed file)",
    )
    parser.add_argument(
        "--skip-apply",
        action="store_true",
        help="Skip applying feedback (only generate and review)",
    )

    args = parser.parse_args()

    success = run_workflow(
        processed_csv=args.processed_csv,
        review_file=args.review_file,
        batch_size=args.batch,
        include_known=args.all,
        skip_generation=args.skip_generation,
        skip_review=args.skip_review,
        skip_apply=args.skip_apply,
    )

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
