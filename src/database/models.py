"""Transaction data model."""

from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Optional


@dataclass
class Transaction:
    """Represents a financial transaction."""

    # Core fields (required)
    date: str  # ISO date (YYYY-MM-DD)
    merchant: str  # Normalized merchant name
    amount: float  # Signed amount
    source: str  # amex, visa, splitwise, etc.
    imported_at: str  # ISO timestamp

    # Optional identification
    id: Optional[int] = None  # DB primary key

    # Additional details
    description: Optional[str] = None  # Original description
    raw_description: Optional[str] = None  # Unmodified description
    statement_date: Optional[str] = None  # Date from statement
    raw_amount: Optional[float] = None  # Original amount
    cc_reference_id: Optional[str] = None  # Credit card reference/transaction ID

    # Categorization
    category: Optional[str] = None
    subcategory: Optional[str] = None
    category_id: Optional[int] = None
    subcategory_id: Optional[int] = None

    # Source tracking
    source_file: Optional[str] = None

    # Characteristics
    is_refund: bool = False
    is_shared: bool = False
    currency: str = "USD"

    # Splitwise integration
    splitwise_id: Optional[int] = None
    splitwise_deleted_at: Optional[str] = None

    # Sync tracking
    written_to_sheet: bool = False
    sheet_year: Optional[int] = None
    sheet_row_id: Optional[int] = None

    # Metadata
    updated_at: Optional[str] = None
    notes: Optional[str] = None

    # Refund tracking
    refund_for_txn_id: Optional[int] = None  # Links to original transaction DB ID
    refund_for_splitwise_id: Optional[int] = None  # Links to original Splitwise expense
    refund_created_at: Optional[str] = None  # When refund was created
    reconciliation_status: str = "pending"  # pending, matched, unmatched, manual_review
    refund_match_method: Optional[str] = None  # txn_id, merchant_amount, manual
    is_partial_refund: bool = False  # True if refund amount < original amount
    refund_percentage: Optional[float] = None  # Percentage of original amount

    def to_dict(self) -> dict:
        """Convert to dictionary, filtering None values for DB insert."""
        data = asdict(self)
        # Remove None values to use DB defaults
        return {k: v for k, v in data.items() if v is not None}

    @classmethod
    def from_row(cls, row: dict) -> "Transaction":
        """Create Transaction from database row."""
        return cls(**row)

    def mark_written_to_sheet(self, year: int, row_id: Optional[int] = None):
        """Mark transaction as written to Google Sheets."""
        self.written_to_sheet = True
        self.sheet_year = year
        self.sheet_row_id = row_id
        self.updated_at = datetime.utcnow().isoformat()

    def update_splitwise_id(self, splitwise_id: int):
        """Update with Splitwise expense ID after creation."""
        self.splitwise_id = splitwise_id
        self.is_shared = True
        self.updated_at = datetime.utcnow().isoformat()

    def mark_deleted_in_splitwise(self):
        """Mark transaction as deleted in Splitwise."""
        self.splitwise_deleted_at = datetime.utcnow().isoformat()
        self.updated_at = datetime.utcnow().isoformat()

    def link_to_original_transaction(self, original_txn_id: int, original_splitwise_id: Optional[int], match_method: str, original_amount: Optional[float] = None):
        """Link this refund to its original transaction.
        
        Args:
            original_txn_id: Database ID of original transaction
            original_splitwise_id: Splitwise expense ID of original transaction
            match_method: How the match was made (txn_id, merchant_amount, manual)
            original_amount: Original transaction amount (to calculate if partial)
        """
        self.refund_for_txn_id = original_txn_id
        self.refund_for_splitwise_id = original_splitwise_id
        self.refund_match_method = match_method
        self.reconciliation_status = "matched"
        self.refund_created_at = datetime.utcnow().isoformat()
        self.updated_at = datetime.utcnow().isoformat()
        
        # Calculate if this is a partial refund
        if original_amount and abs(self.amount) > 0:
            refund_amt = abs(self.amount)
            self.refund_percentage = (refund_amt / original_amount) * 100
            # Consider partial if less than 95% of original (allows for return fees, restocking fees, etc.)
            self.is_partial_refund = self.refund_percentage < 95.0


@dataclass
class ImportLog:
    """Represents an import operation."""

    timestamp: str
    source_type: str  # csv, splitwise_api, sheets, manual
    records_attempted: int
    records_imported: int
    records_skipped: int
    records_failed: int

    id: Optional[int] = None
    source_identifier: Optional[str] = None
    error_message: Optional[str] = None
    metadata: Optional[str] = None  # JSON string

    def to_dict(self) -> dict:
        """Convert to dictionary for DB insert."""
        data = asdict(self)
        return {k: v for k, v in data.items() if v is not None}
