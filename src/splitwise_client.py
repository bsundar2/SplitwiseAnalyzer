"""Client for interacting with the Splitwise API.

This module provides a high-level interface for common Splitwise operations,
including expense management, search, and data export.
"""

# Standard library
import os
import re
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, Union, List
from functools import cache

import numpy as np

# Third-party
import pandas as pd
from dotenv import load_dotenv
from splitwise import Expense, Splitwise

# Local application
from src.constants.splitwise import DEFAULT_CURRENCY, SplitwiseUserId
from src.constants.export_columns import ExportColumns
from src.utils import LOG, parse_float_safe, infer_category

load_dotenv("config/.env")


# Handles Splitwise API/CSV integration
class SplitwiseClient:
    def __init__(self):
        self.consumer_key = os.getenv("SPLITWISE_CONSUMER_KEY")
        self.consumer_secret = os.getenv("SPLITWISE_CONSUMER_SECRET")
        self.api_key = os.getenv("SPLITWISE_API_KEY")
        # Error handling for missing env vars
        if not all([self.consumer_key, self.consumer_secret, self.api_key]):
            raise ValueError(
                "One or more Splitwise credentials are missing. Check config/.env and variable names."
            )
        self.sObj = Splitwise(
            self.consumer_key, self.consumer_secret, api_key=self.api_key
        )

    @cache
    def get_current_user_id(self):
        return self.sObj.getCurrentUser().getId()

    def get_my_expenses_by_date_range(self, start_date, end_date):
        """Fetch all expenses within a date range with automatic pagination.

        This will page through the Splitwise API until no more results are
        returned for the date range. No hard cap is applied here; the function
        will continue paging until the API indicates the end of results.

        Args:
            start_date: Start date (datetime or date object)
            end_date: End date (datetime or date object)

        Returns:
            DataFrame containing all matching expenses
        """
        all_expenses = []
        offset = 0
        page_size = 50  # Maximum allowed by Splitwise API
        has_more = True

        while has_more:
            try:
                # Get a page of expenses
                expenses = self.sObj.getExpenses(
                    dated_after=start_date.strftime("%Y-%m-%d"),
                    dated_before=end_date.strftime("%Y-%m-%d"),
                    limit=page_size,
                    offset=offset,
                )

                if not expenses:  # No more expenses
                    break

                all_expenses.extend(expenses)

                # If we got fewer results than the page size, we've reached the end
                if len(expenses) < page_size:
                    has_more = False
                else:
                    offset += page_size

                LOG.debug(
                    f"Fetched {len(expenses)} expenses (total: {len(all_expenses)})"
                )

            except Exception as e:
                LOG.error(f"Error fetching expenses (offset {offset}): {str(e)}")
                raise

        # Process the expenses into a DataFrame
        my_user_id = self.get_current_user_id()
        data = []

        for expense in all_expenses:
            try:
                users = expense.getUsers() or []

                def _user_name(u) -> str:
                    first = u.getFirstName() or ""
                    return first.strip() or str(u.getId())

                user_rows = []
                for u in users:
                    user_rows.append(
                        {
                            "id": u.getId(),
                            "name": _user_name(u),
                            "paid": parse_float_safe(u.getPaidShare()),
                            "owed": parse_float_safe(u.getOwedShare()),
                        }
                    )

                user_rows_sorted = sorted(
                    user_rows, key=lambda r: (r["name"] or "").lower()
                )

                # Sheets-friendly: single deterministic string, easy to parse with SPLIT/REGEX
                # Example: "Alice|paid=10.00|owed=0.00; Bob|paid=0.00|owed=10.00"
                friends_split = "; ".join(
                    [
                        f"{r['name']}|paid={r['paid']:.2f}|owed={r['owed']:.2f}"
                        for r in user_rows_sorted
                    ]
                )

                participant_names = ", ".join([r["name"] for r in user_rows_sorted])

                my_row = next(
                    (r for r in user_rows_sorted if r["id"] == my_user_id), None
                )
                my_paid = my_row["paid"] if my_row else 0.0
                my_owed = my_row["owed"] if my_row else 0.0
                my_net = my_paid - my_owed

                participant_ids = {r["id"] for r in user_rows_sorted}

                has_self_user = SplitwiseUserId.SELF_EXPENSE in participant_ids
                is_partner_only = participant_ids == {
                    my_user_id,
                    SplitwiseUserId.PARTNER_EXPENSE,
                }

                if has_self_user:
                    split_type = "self"
                elif is_partner_only:
                    split_type = "partner"
                else:
                    other_nonzero = any(
                        r["id"] != my_user_id and (r["paid"] > 0 or r["owed"] > 0)
                        for r in user_rows_sorted
                    )
                    split_type = "shared" if bool(other_nonzero) else "self"

                data.append(
                    {
                        ExportColumns.DATE: expense.getDate(),
                        ExportColumns.AMOUNT: expense.getCost(),
                        ExportColumns.CATEGORY: (
                            expense.getCategory().getName()
                            if expense.getCategory()
                            else None
                        ),
                        ExportColumns.DESCRIPTION: expense.getDescription(),
                        ExportColumns.DETAILS: expense.getDetails() or "",
                        ExportColumns.SPLIT_TYPE: split_type,
                        ExportColumns.PARTICIPANT_NAMES: participant_names,
                        ExportColumns.MY_PAID: my_paid,
                        ExportColumns.MY_OWED: my_owed,
                        ExportColumns.MY_NET: my_net,
                        ExportColumns.FRIENDS_SPLIT: friends_split,
                        ExportColumns.ID: expense.getId(),
                    }
                )
            except Exception as e:
                LOG.warning(
                    f"Error processing expense {getattr(expense, 'id', 'unknown')}: {str(e)}"
                )
                continue

        LOG.info(f"Found {len(data)} expenses between {start_date} and {end_date}")
        return pd.DataFrame(data)

    def find_expense_by_cc_reference(
        self,
        cc_reference_id: str = None,
        amount: float = None,
        date: str = None,
        merchant: str = None,
        lookback_days: int = 30,
    ) -> Optional[Dict]:
        """Find an expense by its cc_reference_id or by matching transaction details.

        First tries to find an exact match by cc_reference_id in the details field.
        If not found and additional details (amount, date, merchant) are provided,
        attempts to find a matching transaction using those criteria.

        Args:
            cc_reference_id: The credit card reference ID to search for
            amount: Transaction amount (required for fuzzy matching)
            date: Transaction date in YYYY-MM-DD format (required for fuzzy matching)
            merchant: Merchant name (optional, improves fuzzy matching)
            lookback_days: Number of days to look back for matching expenses

        Returns:
            dict: The matching expense as a dictionary, or None if not found
        """
        if not cc_reference_id and not (amount is not None and date):
            LOG.debug("Either cc_reference_id or both amount and date must be provided")
            return None

        # Clean and validate the reference ID if provided
        if cc_reference_id:
            cc_reference_id = str(cc_reference_id).strip()
            if not cc_reference_id:
                cc_reference_id = None

        # Fetch recent expenses
        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=lookback_days)

        df = self.get_my_expenses_by_date_range(start_date, end_date)
        if df.empty:
            return None

        # First, try exact match by cc_reference_id in details if provided
        if cc_reference_id and "details" in df.columns:
            details_matches = df["details"].astype(str).str.strip() == cc_reference_id
            matches = df[details_matches]

            if len(matches) == 1:
                return matches.iloc[0].to_dict()
            elif len(matches) > 1:
                LOG.warning(
                    "Multiple expenses found with cc_reference_id %s", cc_reference_id
                )
                return (
                    matches.sort_values("date_updated", ascending=False)
                    .iloc[0]
                    .to_dict()
                )

        # If we have amount and date, try fuzzy matching
        if amount is not None and date:
            try:
                # Convert date string to datetime for comparison
                target_date = pd.to_datetime(date).date()

                # Filter for same amount (within a small tolerance for floating point)
                amount_matches = np.isclose(
                    df["amount"].astype(float), float(amount), rtol=1e-5
                )
                df_filtered = df[amount_matches]

                if not df_filtered.empty:
                    # Filter for same date
                    df_filtered["expense_date"] = pd.to_datetime(
                        df_filtered["date"]
                    ).dt.date
                    date_matches = df_filtered["expense_date"] == target_date
                    df_filtered = df_filtered[date_matches]

                    if not df_filtered.empty:
                        # If we have merchant info, try to match that too
                        if merchant:
                            merchant = str(merchant).lower().strip()
                            if merchant:
                                merchant_matches = (
                                    df_filtered["description"]
                                    .str.lower()
                                    .str.contains(merchant, regex=False)
                                )
                                merchant_matches = df_filtered[merchant_matches]
                                if not merchant_matches.empty:
                                    df_filtered = merchant_matches

                        # Return the best match (most recent if multiple)
                        if not df_filtered.empty:
                            best_match = df_filtered.sort_values(
                                "date_updated", ascending=False
                            ).iloc[0]
                            LOG.info("Found potential match by amount/date/merchant")
                            return best_match.to_dict()

            except Exception as e:
                LOG.warning("Error during fuzzy matching: %s", str(e), exc_info=True)
                return None

        LOG.debug("No matching expense found")
        return None

    def add_expense_from_txn(
        self,
        txn: Dict[str, Any],
        cc_reference_id: str,
        users: Optional[List[Dict]] = None,
    ) -> Union[str, int]:
        """Create a Splitwise expense from normalized transaction data.

        Args:
            txn: Dictionary containing:
                - date (str): Date in YYYY-MM-DD format
                - amount (float): Transaction amount
                - currency (str, optional): Currency code (default: USD)
                - description (str): Transaction description
                - merchant (str, optional): Merchant name (used if description is empty)
                - detail (str, optional): Additional transaction details (stored in notes)
            cc_reference_id: Credit card reference ID for this transaction
            users: Optional list of user participation details:
                - user_id (int): Splitwise user ID
                - paid_share (float): Amount paid by this user
                - owed_share (float): Amount owed by this user

        Returns:
            The created expense ID

        Raises:
            RuntimeError: If expense creation fails or cc_reference_id is missing
        """
        if not cc_reference_id:
            raise ValueError("cc_reference_id is required")

        desc = txn.get("description") or txn.get("merchant") or "Imported expense"
        cost = float(txn.get("amount", 0))
        date = txn.get("date")
        currency = txn.get("currency") or DEFAULT_CURRENCY

        # Always run category inference for statement imports
        category_info = infer_category(txn)
        if category_info:
            txn.update(
                {
                    "category_id": category_info["category_id"],
                    "subcategory_id": category_info.get("subcategory_id", 0),
                    "category_name": category_info.get("category_name"),
                    "subcategory_name": category_info.get("subcategory_name"),
                }
            )
            LOG.info(
                f"Assigned category: {category_info.get('category_name')} / {category_info.get('subcategory_name')}"
            )
        else:
            LOG.warning("No category could be inferred, using default category")
            txn.update(
                {
                    "category_id": 18,  # Default "Other" category
                    "subcategory_id": 0,
                    "category_name": "Other",
                    "subcategory_name": "Other",
                }
            )

        # Use SDK Expense objects
        expense = Expense()
        expense.setCost(str(cost))
        expense.setDescription(desc)
        expense.setDetails(cc_reference_id)
        expense.setDate(date)
        expense.setCurrencyCode(currency)

        # Always set the category (we've ensured it exists above)
        expense.setCategoryId(txn["category_id"])
        if txn.get("subcategory_id") is not None:
            expense.setSubcategoryId(txn["subcategory_id"])
        LOG.debug(
            f"Set category: {txn.get('category_name')} / {txn.get('subcategory_name')}"
        )

        # Handle user shares if provided
        if users:
            for user in users:
                user_id = user.get("user_id")
                paid_share = str(user.get("paid_share", "0.0"))
                owed_share = str(user.get("owed_share", "0.0"))
                expense.addUser(user_id, paid_share=paid_share, owed_share=owed_share)

        # Create the expense and return the ID
        try:
            created = self.sObj.createExpense(expense)
            return created.getId() if hasattr(created, "getId") else created
        except Exception as e:
            raise RuntimeError(f"Failed to create expense: {str(e)}")

    @cache
    def get_categories(self):
        """Get all available Splitwise categories and subcategories.

        Returns:
            list: List of category dictionaries with 'id', 'name', and 'subcategories'
        """
        return self.sObj.getCategories()


# Example usage:
if __name__ == "__main__":
    client = SplitwiseClient()
    print(f"User ID: {client.get_current_user_id()}")

    categories = client.get_categories()
    print(
        "Available Splitwise categories: %s",
        [
            {
                "id": c.id,
                "name": c.name,
                "subcategories": [
                    {"id": s.id, "name": s.name} for s in c.subcategories
                ],
            }
            for c in categories
        ],
    )

    # today = datetime.now().date()
    # seven_days_ago = today - timedelta(days=25)
    # df = client.get_my_expenses_by_date_range(seven_days_ago, today)
    # print(df)
