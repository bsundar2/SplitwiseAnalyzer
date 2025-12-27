# Handles Google Sheets sync logic
import pandas as pd
from typing import Optional

import pygsheets

from src.constants.gsheets import DEFAULT_SPREADSHEET_NAME, SHEETS_AUTHENTICATION_FILE
from src.utils import LOG


def write_to_sheets(
    write_data: pd.DataFrame,
    worksheet_name: str,
    spreadsheet_name: str = DEFAULT_SPREADSHEET_NAME,
    spreadsheet_key: Optional[str] = None,
):
    """Write a DataFrame to a Google Sheets worksheet.

    Behavior:
      - If `spreadsheet_key` is provided, uses `gc.open_by_key(spreadsheet_key)` (recommended).
      - Otherwise falls back to `gc.open(spreadsheet_name)` (opens by title). If open by name fails, the function will create a new spreadsheet with that name.

    Args:
      write_data: DataFrame to write.
      worksheet_name: Title of the worksheet/tab to write into.
      spreadsheet_name: Spreadsheet title (used when spreadsheet_key is not provided).
      spreadsheet_key: Optional spreadsheet id/key (preferred; unique).

    Returns:
      The spreadsheet URL (string) after writing.
    """
    # Login/Authenticate
    LOG.info("Authenticating to Google Sheets using %s", SHEETS_AUTHENTICATION_FILE)
    gc = pygsheets.authorize(service_account_file=SHEETS_AUTHENTICATION_FILE)

    # Open the spreadsheet by key if provided, else by name (with create fallback)
    if spreadsheet_key:
        LOG.info("Opening spreadsheet by key: %s", spreadsheet_key)
        sheet = gc.open_by_key(spreadsheet_key)
    else:
        LOG.info("Opening spreadsheet by name: %s", spreadsheet_name)
        try:
            sheet = gc.open(spreadsheet_name)
        except Exception as e:
            LOG.info("Spreadsheet '%s' not found or not accessible; creating new sheet (owned by service account). Error: %s", spreadsheet_name, str(e))
            sheet = gc.create(spreadsheet_name)

    try:
        worksheet = sheet.worksheet_by_title(worksheet_name)
        worksheet.clear()
    except Exception:
        # If worksheet doesn't exist, create it
        worksheet = sheet.add_worksheet(worksheet_name)

    LOG.info("Writing to sheet (worksheet=%s)", worksheet_name)
    worksheet.set_dataframe(write_data, (1, 1), copy_index=False, copy_head=True)
    LOG.info("Updated Google sheet successfully: %s", sheet.url)
    return sheet.url
