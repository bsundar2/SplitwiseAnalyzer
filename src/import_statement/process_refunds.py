"""Process refund transactions and create corresponding Splitwise expenses.

This module can be used in two ways:
1. Import RefundProcessor class for programmatic use
2. Run as standalone script with CLI arguments

Example usage:
    # As module
    from src.import_statement.process_refunds import RefundProcessor
    processor = RefundProcessor(db, client)
    summary = processor.process_all_pending_refunds()
    
    # As script
    python -m src.import_statement.process_refunds --dry-run --verbose
"""

import argparse
from datetime import datetime
from typing import Optional, Dict, Any

from src.common.utils import LOG
from src.common.splitwise_client import SplitwiseClient
from src.database import DatabaseManager
from src.database.models import Transaction
from src.constants.splitwise import SplitwiseUserId


class RefundProcessor:
    """Handles refund detection, matching, and Splitwise creation."""

    def __init__(self, db: DatabaseManager, client: SplitwiseClient = None):
        """Initialize refund processor.
        
        Args:
            db: DatabaseManager instance
            client: SplitwiseClient instance (optional, for dry-run mode)
        """
        self.db = db
        self.client = client

    def process_refund(
        self,
        refund_txn: Transaction,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        """Process a single refund transaction.
        
        Workflow:
        1. Find original transaction (by cc_reference_id or merchant+amount+date)
        2. Check if refund already processed (idempotency)
        3. Create negative Splitwise expense with same category/split as original
        4. Link refund to original in database
        
        Args:
            refund_txn: Transaction object for the refund (is_refund=True)
            dry_run: If True, don't create Splitwise expense
            
        Returns:
            Result dictionary with status and details
        """
        result = {
            "refund_txn_id": refund_txn.id,
            "amount": refund_txn.amount,
            "merchant": refund_txn.merchant,
            "date": refund_txn.date,
            "cc_reference_id": refund_txn.cc_reference_id,
        }

        # Step 1: Find original transaction
        original = self.db.find_original_for_refund(
            refund_amount=abs(refund_txn.amount),
            refund_date=refund_txn.date,
            merchant=refund_txn.merchant,
            cc_reference_id=refund_txn.cc_reference_id,
            date_window_days=90,
        )

        if not original:
            LOG.warning(
                "Cannot find original transaction for refund: %s (merchant=%s, amount=$%.2f, date=%s)",
                refund_txn.cc_reference_id,
                refund_txn.merchant,
                refund_txn.amount,
                refund_txn.date,
            )
            self.db.mark_refund_as_unmatched(
                refund_txn.id,
                reason=f"No original found for merchant={refund_txn.merchant}, amount={refund_txn.amount}",
            )
            result["status"] = "unmatched"
            result["error"] = "Original transaction not found"
            return result

        # Step 2: Check idempotency - has this refund already been processed?
        if self.db.has_existing_refund_for_original(
            original_txn_id=original.id,
            refund_amount=abs(refund_txn.amount),
            cc_reference_id=refund_txn.cc_reference_id,
        ):
            LOG.info(
                "Refund already exists for original transaction ID %s, skipping",
                original.id,
            )
            result["status"] = "duplicate"
            result["original_txn_id"] = original.id
            result["original_splitwise_id"] = original.splitwise_id
            return result
        
        # Check if this is a partial refund
        refund_percentage = (abs(refund_txn.amount) / original.amount * 100) if original.amount > 0 else 0
        is_full_refund = refund_percentage >= 95.0  # >= 95% considered full (allows for fees)
        
        # Get cumulative refunds for logging
        total_refunded = self.db.get_total_refunds_for_original(original.id)
        net_cost = original.amount - total_refunded - abs(refund_txn.amount)
        
        if not is_full_refund:
            LOG.info(
                "Processing PARTIAL REFUND: $%.2f of $%.2f (%.1f%%) - Net cost: $%.2f",
                abs(refund_txn.amount),
                original.amount,
                refund_percentage,
                net_cost,
            )
        else:
            LOG.info(
                "Processing FULL REFUND: $%.2f of $%.2f (%.1f%%)",
                abs(refund_txn.amount),
                original.amount,
                refund_percentage,
            )

        # Step 3: Verify original has Splitwise ID
        if not original.splitwise_id:
            LOG.warning(
                "Original transaction ID %s has no Splitwise ID, cannot create refund",
                original.id,
            )
            self.db.mark_refund_as_unmatched(
                refund_txn.id,
                reason=f"Original transaction ID {original.id} not in Splitwise",
            )
            result["status"] = "unmatched"
            result["error"] = "Original not in Splitwise"
            result["original_txn_id"] = original.id
            return result

        LOG.info(
            "Matched refund to original: refund_id=%s -> original_id=%s (Splitwise ID: %s)",
            refund_txn.id,
            original.id,
            original.splitwise_id,
        )

        result["original_txn_id"] = original.id
        result["original_splitwise_id"] = original.splitwise_id
        result["category"] = original.category
        result["subcategory"] = original.subcategory
        result["match_method"] = (
            "txn_id" if refund_txn.cc_reference_id else "merchant_amount"
        )

        if dry_run:
            result["status"] = "would_create"
            return result

        # Step 4: Create negative Splitwise expense with same category/split
        try:
            splitwise_id = self._create_refund_in_splitwise(
                refund_txn=refund_txn,
                original_txn=original,
            )

            LOG.info(
                "Created refund in Splitwise: ID %s (original: %s)",
                splitwise_id,
                original.splitwise_id,
            )

            # Step 5: Update refund transaction with Splitwise ID and linkage
            refund_txn.update_splitwise_id(splitwise_id)
            refund_txn.link_to_original_transaction(
                original_txn_id=original.id,
                original_splitwise_id=original.splitwise_id,
                match_method=result["match_method"],
                original_amount=original.amount,
            )

            # Update database
            self.db.update_transaction(refund_txn)

            result["status"] = "created"
            result["splitwise_id"] = splitwise_id

        except Exception as e:
            LOG.exception(
                "Failed to create refund in Splitwise for txn %s: %s",
                refund_txn.id,
                str(e),
            )
            self.db.mark_refund_as_unmatched(
                refund_txn.id,
                reason=f"Splitwise creation failed: {str(e)}",
            )
            result["status"] = "error"
            result["error"] = str(e)

        return result

    def _create_refund_in_splitwise(
        self,
        refund_txn: Transaction,
        original_txn: Transaction,
    ) -> int:
        """Create a negative expense in Splitwise for a refund.
        
        The refund expense will have:
        - Negative amount
        - Same category/subcategory as original
        - Same split participants and ratios as original
        - Description indicating it's a refund
        - Notes linking to original expense
        
        Args:
            refund_txn: Refund transaction
            original_txn: Original transaction being refunded
            
        Returns:
            Splitwise expense ID of created refund
        """
        if not self.client:
            raise ValueError("SplitwiseClient required for creating refunds")

        # Fetch original expense details to get split information
        original_expense = self.client.get_expense(original_txn.splitwise_id)
        if not original_expense:
            raise ValueError(
                f"Cannot fetch original Splitwise expense {original_txn.splitwise_id}"
            )

        # Get current user ID
        current_user_id = self.client.get_current_user_id()

        # Extract users and their split ratios from original expense
        # Refund should mirror the original split exactly
        original_users = original_expense.getUsers()
        users = []

        for user in original_users:
            user_id = user.getId()
            paid_share = float(user.getPaidShare())
            owed_share = float(user.getOwedShare())

            # For refund: reverse the paid/owed shares
            # Original: SELF paid X, user owed X
            # Refund: user paid X (received credit), SELF owed X
            users.append(
                {
                    "user_id": user_id,
                    "paid_share": owed_share,  # Reversed
                    "owed_share": paid_share,  # Reversed
                }
            )

        # Build refund expense
        refund_percentage = (abs(refund_txn.amount) / original_txn.amount * 100) if original_txn.amount > 0 else 0
        # Consider it a full refund if >= 95% (allows for restocking fees, return fees, etc.)
        is_full_refund = refund_percentage >= 95.0
        
        if is_full_refund:
            description = f"REFUND: {original_txn.description or original_txn.merchant}"
        else:
            # Partial refund - show percentage
            description = f"REFUND ({refund_percentage:.0f}%): {original_txn.description or original_txn.merchant}"
        
        # Always include net cost information in notes
        net_cost = original_txn.amount - abs(refund_txn.amount)
        notes = (
            f"REFUND for Splitwise expense {original_txn.splitwise_id}\n"
            f"Refund amount: ${abs(refund_txn.amount):.2f} of ${original_txn.amount:.2f} ({refund_percentage:.1f}%)\n"
            f"Net cost: ${net_cost:.2f}\n"
            f"Original cc_reference_id: {original_txn.cc_reference_id}\n"
            f"Refund cc_reference_id: {refund_txn.cc_reference_id}"
        )

        txn_dict = {
            "date": refund_txn.date,
            "amount": abs(refund_txn.amount),  # Use absolute value
            "description": description,
            "merchant": refund_txn.merchant,
            "detail": refund_txn.cc_reference_id,
            "category_id": original_txn.category_id,
            "subcategory_id": original_txn.subcategory_id,
            "category_name": original_txn.category,
            "subcategory_name": original_txn.subcategory,
        }

        # Create expense using client
        splitwise_id = self.client.add_expense_from_txn(
            txn_dict,
            cc_reference_id=refund_txn.cc_reference_id,
            users=users,
            notes=notes,
        )

        return splitwise_id

    def process_all_pending_refunds(self, dry_run: bool = False) -> Dict[str, Any]:
        """Process all pending unmatched refunds.
        
        Args:
            dry_run: If True, don't create Splitwise expenses
            
        Returns:
            Summary of processing results
        """
        pending_refunds = self.db.get_unmatched_refunds()

        LOG.info("Found %d pending refunds to process", len(pending_refunds))

        summary = {
            "total": len(pending_refunds),
            "created": 0,
            "duplicate": 0,
            "unmatched": 0,
            "errors": 0,
            "would_create": 0,
            "results": [],
        }

        for refund in pending_refunds:
            result = self.process_refund(refund, dry_run=dry_run)
            summary["results"].append(result)

            status = result.get("status")
            if status == "created":
                summary["created"] += 1
            elif status == "duplicate":
                summary["duplicate"] += 1
            elif status == "unmatched":
                summary["unmatched"] += 1
            elif status == "error":
                summary["errors"] += 1
            elif status == "would_create":
                summary["would_create"] += 1

        LOG.info(
            "Refund processing complete: %d created, %d duplicates, %d unmatched, %d errors",
            summary["created"],
            summary["duplicate"],
            summary["unmatched"],
            summary["errors"],
        )

        return summary


def main():
    """Main entry point for standalone script execution."""
    parser = argparse.ArgumentParser(
        description="Process pending refunds - match to originals and create in Splitwise"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview what would be done without making changes",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose logging",
    )

    args = parser.parse_args()

    # Initialize database and client
    db = DatabaseManager()
    client = None if args.dry_run else SplitwiseClient()

    LOG.info("=" * 60)
    LOG.info("Refund Processing Script")
    LOG.info("=" * 60)
    LOG.info("Mode: %s", "DRY RUN" if args.dry_run else "LIVE")
    LOG.info("Time: %s", datetime.now().isoformat())
    LOG.info("=" * 60)

    # Get pending refunds count
    pending_refunds = db.get_unmatched_refunds()
    LOG.info("Found %d pending refunds to process", len(pending_refunds))

    if not pending_refunds:
        LOG.info("No pending refunds to process")
        return

    # Show sample of pending refunds
    if args.verbose:
        LOG.info("\nPending refunds:")
        for i, refund in enumerate(pending_refunds[:5], 1):
            LOG.info(
                "  %d. ID=%s, Date=%s, Merchant=%s, Amount=$%.2f, Status=%s",
                i,
                refund.id,
                refund.date,
                refund.merchant,
                refund.amount,
                refund.reconciliation_status,
            )
        if len(pending_refunds) > 5:
            LOG.info("  ... and %d more", len(pending_refunds) - 5)

    # Process refunds
    LOG.info("\nProcessing refunds...")
    processor = RefundProcessor(db=db, client=client)
    summary = processor.process_all_pending_refunds(dry_run=args.dry_run)

    # Print summary
    LOG.info("\n" + "=" * 60)
    LOG.info("REFUND PROCESSING SUMMARY")
    LOG.info("=" * 60)
    LOG.info("Total pending refunds: %d", summary["total"])

    if args.dry_run:
        LOG.info("Would create in Splitwise: %d", summary["would_create"])
    else:
        LOG.info("Successfully created: %d", summary["created"])

    LOG.info("Duplicates (already processed): %d", summary["duplicate"])
    LOG.info("Unmatched (manual review needed): %d", summary["unmatched"])
    LOG.info("Errors: %d", summary["errors"])
    LOG.info("=" * 60)

    # Show details of unmatched refunds
    if summary["unmatched"] > 0 and args.verbose:
        LOG.info("\nUnmatched refunds requiring manual review:")
        for result in summary["results"]:
            if result.get("status") == "unmatched":
                LOG.info(
                    "  - ID=%s, Date=%s, Merchant=%s, Amount=$%.2f",
                    result.get("refund_txn_id"),
                    result.get("date"),
                    result.get("merchant"),
                    result.get("amount"),
                )
                LOG.info("    Error: %s", result.get("error"))

    # Show details of errors
    if summary["errors"] > 0 and args.verbose:
        LOG.info("\nErrors encountered:")
        for result in summary["results"]:
            if result.get("status") == "error":
                LOG.info(
                    "  - ID=%s, Date=%s, Merchant=%s, Amount=$%.2f",
                    result.get("refund_txn_id"),
                    result.get("date"),
                    result.get("merchant"),
                    result.get("amount"),
                )
                LOG.info("    Error: %s", result.get("error"))

    if args.dry_run:
        LOG.info("\nDry run complete - no changes were made")
    else:
        LOG.info("\nRefund processing complete")


if __name__ == "__main__":
    # Load environment variables when run as script
    from dotenv import load_dotenv
    load_dotenv("config/.env")
    
    main()
