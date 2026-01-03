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
from splitwise.category import Category
from splitwise.user import ExpenseUser

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

    @cache
    def fetch_expenses_with_details(self, start_date_str: str, end_date_str: str):
        """Fetch all expenses within a date range with full details populated.
        
        This fetches the expense list first, then calls getExpense(id) for each
        one to populate the details field. Results are cached using @lru_cache.
        
        Args:
            start_date_str: Start date as string (YYYY-MM-DD)
            end_date_str: End date as string (YYYY-MM-DD)
            
        Returns:
            dict: Mapping of expense_id -> expense dict with details field populated
        """
        from datetime import datetime
        start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date()
        end_date = datetime.strptime(end_date_str, "%Y-%m-%d").date()
        
        LOG.info(f"Fetching expenses with full details from {start_date} to {end_date}")
        all_expenses = []
        offset = 0
        page_size = 50
        has_more = True
        
        # First, get the list of expense IDs
        while has_more:
            try:
                expenses = self.sObj.getExpenses(
                    dated_after=start_date_str,
                    dated_before=end_date_str,
                    limit=page_size,
                    offset=offset,
                )
                
                if not expenses:
                    break
                    
                all_expenses.extend(expenses)
                
                if len(expenses) < page_size:
                    has_more = False
                else:
                    offset += page_size
                    
            except Exception as e:
                LOG.error(f"Error fetching expense list (offset {offset}): {str(e)}")
                raise
        
        LOG.info(f"Fetched {len(all_expenses)} expenses, now getting full details for each")
        
        # Now fetch each expense individually to get the details field
        expenses_with_details = {}
        for i, exp in enumerate(all_expenses):
            try:
                expense_id = exp.getId()
                # Fetch full expense details
                full_expense = self.sObj.getExpense(expense_id)
                
                expenses_with_details[expense_id] = {
                    'id': expense_id,
                    'date': full_expense.getDate(),
                    'description': full_expense.getDescription(),
                    'cost': full_expense.getCost(),
                    'details': full_expense.getDetails() or '',
                    'category': full_expense.getCategory().getName() if full_expense.getCategory() else None,
                }
                
                if (i + 1) % 20 == 0:
                    LOG.info(f"Processed {i + 1}/{len(all_expenses)} expenses")
                    
            except Exception as e:
                LOG.warning(f"Error fetching details for expense {expense_id}: {str(e)}")
                continue
        
        LOG.info(f"Cached {len(expenses_with_details)} expenses with details")
        return expenses_with_details

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
                # Debug: Print details for recent expenses
                if len(data) <= 3:
                    print(f"[DEBUG] Expense {expense.getId()}: getDetails()={repr(expense.getDetails())}")
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
        use_detailed_search: bool = False,
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

        # Use detailed search if requested (fetches full details for each expense)
        if use_detailed_search and cc_reference_id:
            end_date = datetime.now().date()
            start_date = end_date - timedelta(days=lookback_days)
            
            # Call cached method with string dates
            expense_cache = self.fetch_expenses_with_details(
                start_date.strftime("%Y-%m-%d"),
                end_date.strftime("%Y-%m-%d")
            )
            
            # Search in the cache
            cc_ref_clean = cc_reference_id.strip().strip("'\"")
            for exp_id, exp_data in expense_cache.items():
                details_clean = str(exp_data.get('details', '')).strip().strip("'\"")
                if details_clean == cc_ref_clean:
                    LOG.info(f"Found expense {exp_id} matching cc_reference_id: {cc_reference_id}")
                    return exp_data
            return None
        
        # Fallback: Fetch from API (legacy behavior, doesn't have details field)
        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=lookback_days)

        df = self.get_my_expenses_by_date_range(start_date, end_date)
        if df.empty:
            return None

        # First, try exact match by cc_reference_id in details if provided
        print(f"[SEARCH DEBUG] cc_reference_id={cc_reference_id}, checking if should search details")
        details_col = "Details"  # Column name from ExportColumns.DETAILS
        if cc_reference_id and details_col in df.columns:
            # Strip quotes and whitespace from both sides for comparison
            # (Splitwise SDK may wrap details in DOUBLE quotes like ''value'')
            df_details_clean = df[details_col].astype(str).str.strip()
            # Strip multiple layers of quotes (Splitwise returns ''value'' with double quotes)
            for _ in range(3):
                df_details_clean = df_details_clean.str.strip("'\"")
            
            cc_ref_clean = str(cc_reference_id).strip()
            for _ in range(3):
                cc_ref_clean = cc_ref_clean.strip("'\"")
            
            details_matches = df_details_clean == cc_ref_clean
            matches = df[details_matches]

            if len(matches) == 1:
                LOG.info(f"Found exact match for cc_reference_id: {cc_reference_id}")
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
            else:
                LOG.debug(f"No exact details match found for '{cc_ref_clean}'")

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

        # Only run category inference if not already provided
        if txn.get("category_id") is None:
            LOG.info("Category not provided, running inference")
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
        else:
            LOG.info(
                f"Using provided category: {txn.get('category_name')} / {txn.get('subcategory_name')} "
                f"(ID: {txn.get('category_id')}, Subcategory ID: {txn.get('subcategory_id')})"
            )

        # Use SDK Expense objects
        expense = Expense()
        expense.setCost(str(cost))
        expense.setDescription(desc)
        expense.setDetails(str(cc_reference_id))  # Ensure it's a plain string without quotes
        expense.setDate(date)
        expense.setCurrencyCode(currency)

        # Set the category - fail if None (no default fallback)
        category_id = txn.get("category_id")
        subcategory_id = txn.get("subcategory_id")
        
        LOG.info(
            f"Setting category: ID={category_id}, Subcategory ID={subcategory_id}, "
            f"Name={txn.get('category_name')}/{txn.get('subcategory_name')}"
        )
        
        if category_id is None or category_id == 0:
            error_msg = (
                f"Cannot add expense without valid category. "
                f"Merchant: {desc}, "
                f"Category from inference: {txn.get('category_name')} / {txn.get('subcategory_name')}"
            )
            LOG.error(error_msg)
            raise ValueError(error_msg)
        
        # Create category object with ID and subcategory
        category = Category()
        category.id = category_id
        if subcategory_id is not None and subcategory_id != 0:
            # Try setting subcategory properly
            LOG.info(f"Setting subcategory ID: {subcategory_id}")
            # The Category object may need subcategory set differently
            try:
                category.subcategory_id = subcategory_id
            except AttributeError:
                LOG.warning(f"Could not set subcategory_id as attribute, trying subcategories list")
                category.subcategories = [{"id": subcategory_id}]
        
        LOG.info(f"Category object created: id={category.id}, has subcategory={hasattr(category, 'subcategory_id')}")
        expense.setCategory(category)
        LOG.debug(
            f"Set category: {txn.get('category_name')} / {txn.get('subcategory_name')}"
        )

        # Handle user shares if provided
        if users:
            for user_data in users:
                user = ExpenseUser()
                user.setId(user_data.get("user_id"))
                user.setPaidShare(str(user_data.get("paid_share", "0.0")))
                user.setOwedShare(str(user_data.get("owed_share", "0.0")))
                expense.addUser(user)

        # Create the expense and return the ID
        try:
            created = self.sObj.createExpense(expense)
            
            # Handle tuple return (success, expense_object) or direct Expense object
            if isinstance(created, tuple):
                if len(created) >= 2 and created[1] is not None:
                    created = created[1]  # Get the expense object from tuple
                elif len(created) >= 1:
                    created = created[0]
            
            # Extract ID using various methods
            expense_id = None
            if hasattr(created, 'getId') and callable(created.getId):
                expense_id = created.getId()
            elif hasattr(created, 'id'):
                expense_id = created.id
            elif isinstance(created, (int, str)):
                expense_id = created
            
            if expense_id is None:
                LOG.error(f"Could not extract expense ID. Type: {type(created)}, Dir: {dir(created) if hasattr(created, '__dict__') else 'N/A'}")
                raise RuntimeError("Failed to get expense ID from created expense")
            
            LOG.info(f"Successfully created expense with ID: {expense_id}")
            return int(expense_id)
        except RuntimeError:
            raise
        except Exception as e:
            LOG.error(f"Error creating expense: {str(e)}", exc_info=True)
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
