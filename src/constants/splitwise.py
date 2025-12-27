"""Constants related to Splitwise integration.

This module contains all the constants used for interacting with the Splitwise API,
including payload keys, default values, and other configuration parameters.
"""

# Marker used to identify imported transactions in Splitwise descriptions
IMPORTED_ID_MARKER = "[ImportedID:"

# Default currency code used for transactions
DEFAULT_CURRENCY = "USD"

# Keys used in Splitwise API payloads
class PayloadKeys:
    """Constants for Splitwise API payload keys."""
    COST = "cost"
    DESCRIPTION = "description"
    DATE = "date"
    CURRENCY = "currency_code"
