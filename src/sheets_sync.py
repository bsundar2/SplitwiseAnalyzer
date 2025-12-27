# Handles Google Sheets sync logic
import pandas as pd
from typing import Optional

import pygsheets

from src.constants.gsheets import DEFAULT_SPREADSHEET_NAME, SHEETS_AUTHENTICATION_FILE
from src.utils import LOG


def _colnum_to_a1(n: int) -> str:
    # 1 -> A, 27 -> AA
    s = ""
    while n > 0:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def _ensure_size_for_append(worksheet, start_row: int, num_rows: int, num_cols: int):
    # Ensure worksheet has enough rows and cols for an append. Use attribute checks instead of catching broad exceptions.
    needed_rows = start_row + num_rows - 1
    curr_rows = getattr(worksheet, 'rows', None)
    if curr_rows is not None and needed_rows > curr_rows:
        add = needed_rows - curr_rows
        LOG.info("Adding %d rows to worksheet to accommodate append", add)
        if hasattr(worksheet, 'add_rows'):
            worksheet.add_rows(add)
        else:
            # If add_rows not available, try resize API if present
            if hasattr(worksheet, 'resize'):
                worksheet.resize(rows=needed_rows)
            else:
                raise RuntimeError("Worksheet does not support add_rows or resize; cannot expand rows")

    needed_cols = max(num_cols, 1)
    curr_cols = getattr(worksheet, 'cols', None)
    if curr_cols is not None and needed_cols > curr_cols:
        addc = needed_cols - curr_cols
        LOG.info("Adding %d cols to worksheet to accommodate columns", addc)
        if hasattr(worksheet, 'add_cols'):
            worksheet.add_cols(addc)
        else:
            if hasattr(worksheet, 'resize'):
                worksheet.resize(cols=needed_cols)
            else:
                raise RuntimeError("Worksheet does not support add_cols or resize; cannot expand cols")


def _format_header_bold(sheet, worksheet, num_columns: int):
    header_range = f"A1:{_colnum_to_a1(num_columns)}1"
    # Use public API only. If the worksheet doesn't support .format(), log and skip bolding.
    if not hasattr(worksheet, 'format'):
        LOG.info("Worksheet object does not support .format(); skipping header bolding")
        return
    worksheet.format(header_range, {"textFormat": {"bold": True}})


def _apply_column_formats(worksheet, write_data: pd.DataFrame):
    # Some pygsheets versions accept include_tailing_empty; handle that specific TypeError at call site
    try:
        values = worksheet.get_all_values(include_tailing_empty=False)
    except TypeError:
        values = worksheet.get_all_values()

    used_rows = len(values) if values else 1

    cols = list(write_data.columns)
    # amount -> currency
    if "amount" in cols and used_rows:
        idx = cols.index("amount") + 1
        col_letter = _colnum_to_a1(idx)
        rng = f"{col_letter}2:{col_letter}{used_rows}"
        if hasattr(worksheet, 'format'):
            # Apply currency pattern; allow any errors to propagate so failures are visible and fixable
            worksheet.format(rng, {"numberFormat": {"type": "CURRENCY", "pattern": "$#,##0.00"}})
        else:
            raise RuntimeError("Worksheet object does not support .format() — cannot apply amount format")

    # date -> US-style date
    if "date" in cols and used_rows:
        idx = cols.index("date") + 1
        col_letter = _colnum_to_a1(idx)
        rng = f"{col_letter}2:{col_letter}{used_rows}"
        if hasattr(worksheet, 'format'):
            worksheet.format(rng, {"numberFormat": {"type": "DATE", "pattern": "mm/dd/yyyy"}})
        else:
            raise RuntimeError("Worksheet object does not support .format() — cannot apply date format")


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
    After writing, attempt to format key columns (date, amount) and freeze the header row.
    """
    # Inline small steps directly here instead of tiny helpers so flow is explicit
    gc = pygsheets.authorize(service_account_file=SHEETS_AUTHENTICATION_FILE)

    # Open spreadsheet by key or name
    if spreadsheet_key:
        sheet = gc.open_by_key(spreadsheet_key)
    else:
        sheet = gc.open(spreadsheet_name)

    # Ensure worksheet exists: scan existing worksheets, else create
    worksheet = None
    for ws in sheet.worksheets():
        if getattr(ws, "title", None) == worksheet_name:
            worksheet = ws
            break
    if worksheet is None:
        worksheet = sheet.add_worksheet(worksheet_name)

    num_cols = len(write_data.columns)

    if append:
        # get values with the include_tailing_empty fallback
        try:
            values = worksheet.get_all_values(include_tailing_empty=False)
        except TypeError:
            values = worksheet.get_all_values()
        used_rows = len(values) if values else 0
        if used_rows == 0:
            LOG.info("Appending to empty sheet; writing header and data")
            worksheet.set_dataframe(write_data, (1, 1), copy_index=False, copy_head=True)
        else:
            start_row = used_rows + 1
            LOG.info("Appending %d rows starting at row %d (existing rows=%d)", len(write_data), start_row, used_rows)
            _ensure_size_for_append(worksheet, start_row, len(write_data), num_cols)
            worksheet.set_dataframe(write_data, (start_row, 1), copy_index=False, copy_head=False)
    else:
        worksheet.clear()
        LOG.info("Writing to sheet (overwrite)")
        worksheet.set_dataframe(write_data, (1, 1), copy_index=False, copy_head=True)

    # Post-write formatting: freeze header, autosize and format columns
    worksheet.frozen_rows = 1

    # Autosize columns if API available (best-effort)
    for i in range(1, num_cols + 1):
        if hasattr(worksheet, 'adjust_column_width'):
            worksheet.adjust_column_width(i, 200)

    _apply_column_formats(worksheet, write_data)

    LOG.info("Updated Google sheet successfully: %s", sheet.url)
    return sheet.url
