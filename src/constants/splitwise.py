"""Constants related to Splitwise integration.

This module contains all the constants used for interacting with the Splitwise API,
including payload keys, default values, and other configuration parameters.
"""
from enum import IntEnum

# Marker used to identify imported transactions in Splitwise descriptions
IMPORTED_ID_MARKER = "[ImportedID:"

# Default currency code used for transactions
DEFAULT_CURRENCY = "USD"

class SplitwiseUserId(IntEnum):
    SELF_EXPENSE = 113553156
    PARTNER_EXPENSE = 5078839
