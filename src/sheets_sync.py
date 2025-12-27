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
    append: bool = False,
):
    """Write a DataFrame to a Google Sheets worksheet.

    If append=True, the data will be appended after existing rows (header not duplicated).
    Otherwise the worksheet is cleared (or created) and rewritten.

    Args:
      write_data: DataFrame to write.
      worksheet_name: Title of the worksheet/tab to write into.
      spreadsheet_name: Spreadsheet title (used when spreadsheet_key is not provided).
      spreadsheet_key: Optional spreadsheet id/key (preferred; unique).
      append: Whether to append data (True) or overwrite (False).

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

    # Ensure worksheet exists
    try:
        worksheet = sheet.worksheet_by_title(worksheet_name)
    except Exception:
        worksheet = sheet.add_worksheet(worksheet_name)

    if append:
        # Determine starting row for append. If the sheet is empty, write header.
        try:
            values = worksheet.get_all_values(include_tailing_empty=False)
        except TypeError:
            # fallback if older pygsheets version doesn't support include_tailing_empty
            values = worksheet.get_all_values()
        used_rows = len(values) if values else 0
        if used_rows == 0:
            # empty sheet: write header + data at (1,1)
            LOG.info("Appending to empty sheet; writing header and data")
            worksheet.set_dataframe(write_data, (1, 1), copy_index=False, copy_head=True)
        else:
            # append without header
            start_row = used_rows + 1
            LOG.info("Appending %d rows starting at row %d (existing rows=%d)", len(write_data), start_row, used_rows)
            # Ensure sheet has enough rows and columns for the append
            needed_rows = start_row + len(write_data) - 1
            try:
                curr_rows = worksheet.rows
            except Exception:
                curr_rows = None
            if curr_rows is not None and needed_rows > curr_rows:
                add = needed_rows - curr_rows
                LOG.info("Adding %d rows to worksheet to accommodate append", add)
                try:
                    worksheet.add_rows(add)
                except Exception:
                    # fallback: resize (some pygsheets versions may support rows property only)
                    pass

            # Ensure enough columns
            needed_cols = max(len(write_data.columns), 1)
            try:
                curr_cols = worksheet.cols
            except Exception:
                curr_cols = None
            if curr_cols is not None and needed_cols > curr_cols:
                addc = needed_cols - curr_cols
                LOG.info("Adding %d cols to worksheet to accommodate columns", addc)
                try:
                    worksheet.add_cols(addc)
                except Exception:
                    pass

            worksheet.set_dataframe(write_data, (start_row, 1), copy_index=False, copy_head=False)
    else:
        # overwrite behavior: clear and write fresh
        try:
            worksheet.clear()
        except Exception:
            pass
        LOG.info("Writing to sheet (overwrite)")
        worksheet.set_dataframe(write_data, (1, 1), copy_index=False, copy_head=True)

    LOG.info("Updated Google sheet successfully: %s", sheet.url)
    return sheet.url
