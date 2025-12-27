import os

# Default spreadsheet name used by the Google Sheets writer
DEFAULT_SPREADSHEET_NAME = "test_expenses"
SPLITWISE_EXPENSES_WORKSHEET = "Splitwise Expenses"

# Path to service account JSON (resolved relative to this file)
SHEETS_AUTHENTICATION_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'config', 'gsheets_authentication.json'))
