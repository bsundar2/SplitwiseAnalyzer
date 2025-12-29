import os

# Default worksheet name used by the Google Sheets writer
DEFAULT_WORKSHEET_NAME = "test_expenses"

# Path to service account JSON (resolved relative to this file)
SHEETS_AUTHENTICATION_FILE = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__), "..", "..", "config", "gsheets_authentication.json"
    )
)
