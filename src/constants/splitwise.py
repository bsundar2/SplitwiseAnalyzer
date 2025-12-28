"""Constants related to Splitwise integration.

This module contains all the constants used for interacting with the Splitwise API,
including payload keys, default values, and other configuration parameters.
"""

from enum import IntEnum, StrEnum

# Marker used to identify imported transactions in Splitwise descriptions
IMPORTED_ID_MARKER = "[ImportedID:"

# Default currency code used for transactions
DEFAULT_CURRENCY = "USD"


class SplitwiseUserId(IntEnum):
    SELF_EXPENSE = 113553156
    PARTNER_EXPENSE = 5078839


class ExcludedSplitwiseDescriptions(StrEnum):
    """Well-known Splitwise-generated descriptions that should be excluded from budgeting exports.

    These are exact-match strings (after trimming and case-normalization) that represent
    settlement/payment style records rather than expense items.
    """

    SETTLE_ALL_BALANCES = "Settle all balances"
    PAYMENT = "Payment"
