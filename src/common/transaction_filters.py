"""Transaction filtering utilities.

Provides common filtering logic for deleted expenses, payments, refunds, etc.
Centralizes these checks to avoid duplication across the codebase.
"""

from typing import Any, Optional
from src.constants.splitwise import DELETED_AT_FIELD, REFUND_KEYWORDS


def is_deleted_expense(expense_obj: Any) -> bool:
    """Check if Splitwise expense object is deleted.

    Args:
        expense_obj: Splitwise expense object from API

    Returns:
        True if expense is marked as deleted
    """
    return (
        hasattr(expense_obj, DELETED_AT_FIELD)
        and getattr(expense_obj, DELETED_AT_FIELD) is not None
        and getattr(expense_obj, DELETED_AT_FIELD) != ""
    )


def is_deleted_transaction(txn) -> bool:
    """Check if database transaction is deleted.

    Args:
        txn: Transaction object from database

    Returns:
        True if transaction is marked as deleted in Splitwise
    """
    return bool(txn.splitwise_deleted_at)


def is_payment_transaction(description: str) -> bool:
    """Check if transaction is a payment/settlement.

    Args:
        description: Transaction description

    Returns:
        True if description matches payment patterns
    """
    if not description:
        return False

    lower = description.lower()

    # Exact matches for common Splitwise patterns
    if lower == "settle all balances" or lower == "payment":
        return True

    # Check for payment keywords
    payment_keywords = ["payment", "autopay", "thank you", "settle"]
    return any(kw in lower for kw in payment_keywords)


def is_refund_transaction(txn, check_description: bool = True) -> bool:
    """Check if transaction is a refund.

    Checks both the is_refund flag and optionally the description
    for refund keywords.

    Args:
        txn: Transaction object from database
        check_description: Whether to also check description for refund keywords

    Returns:
        True if transaction is a refund
    """
    # Check explicit flag first
    if hasattr(txn, "is_refund") and txn.is_refund:
        return True

    # Optionally check description
    if check_description:
        description = (
            getattr(txn, "description", None) or getattr(txn, "merchant", None) or ""
        )
        return any(keyword in description.lower() for keyword in REFUND_KEYWORDS)

    return False


def is_excluded_description(description: str) -> bool:
    """Check if description should be excluded from exports.

    Args:
        description: Transaction description

    Returns:
        True if description matches exclusion patterns
    """
    # Currently only excludes payment/settlement transactions
    return is_payment_transaction(description)
