"""Client for interacting with the Splitwise API.

This module provides a high-level interface for common Splitwise operations,
including expense management, search, and data export.
"""

# Standard library
import os
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, Union, List
from functools import cache

# Third-party
import pandas as pd
from dotenv import load_dotenv
from splitwise import Expense, Splitwise

# Local application
from src.constants.splitwise import (
    IMPORTED_ID_MARKER,
    DEFAULT_CURRENCY,
    SplitwiseUserId
)
from src.utils import LOG, merchant_slug, compute_import_id, generate_fingerprint, safe_float

load_dotenv("config/credentials.env")


# Handles Splitwise API/CSV integration
class SplitwiseClient:
    def __init__(self):
        self.consumer_key = os.getenv("SPLITWISE_CONSUMER_KEY")
        self.consumer_secret = os.getenv("SPLITWISE_CONSUMER_SECRET")
        self.api_key = os.getenv("SPLITWISE_API_KEY")
        # Error handling for missing env vars
        if not all([self.consumer_key, self.consumer_secret, self.api_key]):
            raise ValueError("One or more Splitwise credentials are missing. Check config/credentials.env and variable names.")
        self.sObj = Splitwise(self.consumer_key, self.consumer_secret, api_key=self.api_key)

    @cache
    def get_current_user_id(self):
        return self.sObj.getCurrentUser().getId()

    def get_my_expenses_by_date_range(self, start_date, end_date, max_results=1000):
        """Fetch all expenses within a date range with automatic pagination.
        
        Args:
            start_date: Start date (datetime or date object)
            end_date: End date (datetime or date object)
            max_results: Maximum number of results to return (safety limit)
            
        Returns:
            DataFrame containing all matching expenses
        """
        all_expenses = []
        offset = 0
        page_size = 50  # Maximum allowed by Splitwise API
        has_more = True
        
        while has_more and len(all_expenses) < max_results:
            try:
                # Get a page of expenses
                expenses = self.sObj.getExpenses(
                    dated_after=start_date.strftime("%Y-%m-%d"),
                    dated_before=end_date.strftime("%Y-%m-%d"),
                    limit=page_size,
                    offset=offset
                )
                
                if not expenses:  # No more expenses
                    break
                    
                all_expenses.extend(expenses)
                
                # If we got fewer results than the page size, we've reached the end
                if len(expenses) < page_size:
                    has_more = False
                else:
                    offset += page_size
                    
                LOG.debug(f"Fetched {len(expenses)} expenses (total: {len(all_expenses)})")
                    
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
                            "paid": safe_float(u.getPaidShare()),
                            "owed": safe_float(u.getOwedShare()),
                        }
                    )

                user_rows_sorted = sorted(user_rows, key=lambda r: (r["name"] or "").lower())

                # Sheets-friendly: single deterministic string, easy to parse with SPLIT/REGEX
                # Example: "Alice|paid=10.00|owed=0.00; Bob|paid=0.00|owed=10.00"
                friends_split = "; ".join(
                    [f"{r['name']}|paid={r['paid']:.2f}|owed={r['owed']:.2f}" for r in user_rows_sorted]
                )

                participant_names = ", ".join([r["name"] for r in user_rows_sorted])

                my_row = next((r for r in user_rows_sorted if r["id"] == my_user_id), None)
                my_paid = my_row["paid"] if my_row else 0.0
                my_owed = my_row["owed"] if my_row else 0.0
                my_net = my_paid - my_owed

                participant_ids = {r["id"] for r in user_rows_sorted}

                has_self_user = SplitwiseUserId.SELF_EXPENSE in participant_ids
                is_partner_only = participant_ids == {my_user_id, SplitwiseUserId.PARTNER_EXPENSE}

                if has_self_user:
                    split_type = "self"
                elif is_partner_only:
                    split_type = "partner"
                else:
                    other_nonzero = any(
                        r["id"] != my_user_id and (r["paid"] > 0 or r["owed"] > 0) for r in user_rows_sorted
                    )
                    split_type = "shared" if bool(other_nonzero) else "self"

                data.append({
                    "date": expense.getDate(),
                    "amount": expense.getCost(),
                    "category": expense.getCategory().getName() if expense.getCategory() else None,
                    "description": expense.getDescription(),
                    "details": expense.getDetails() or "",
                    "split_type": split_type,
                    "participant_names": participant_names,
                    "my_paid": my_paid,
                    "my_owed": my_owed,
                    "my_net": my_net,
                    "friends_split": friends_split,
                    "id": expense.getId(),
                })
            except Exception as e:
                LOG.warning(f"Error processing expense {getattr(expense, 'id', 'unknown')}: {str(e)}")
                continue
        
        LOG.info(f"Found {len(data)} expenses between {start_date} and {end_date}")
        return pd.DataFrame(data)

    def find_expense_by_import_id(self, import_id: str, merchant: str = None, lookback_days: int = 365):
        """Search recent Splitwise expenses for the import id marker in description.

        If not found, fall back to fuzzy match: same amount, date within +/-1 day, and merchant slug match.
        Returns a dict row if a single unambiguous match is found, otherwise None.
        """
        # naive strategy: fetch last N days and scan descriptions for marker
        end = datetime.now().date()
        start = end - timedelta(days=lookback_days)

        df = self.get_my_expenses_by_date_range(start, end)
        if df.empty:
            return None
        # First, try exact marker search in description
        mask = df["description"].astype(str).str.contains(import_id, na=False)
        matches = df[mask]
        if len(matches) == 1:
            return matches.iloc[0].to_dict()
        elif len(matches) > 1:
            LOG.info("Multiple Splitwise expenses matched import_id %s; returning first", import_id)
            return matches.iloc[0].to_dict()

        # Fallback fuzzy match if merchant provided
        candidates = []
        # If merchant not provided, try to derive nothing
        target_slug = merchant_slug(merchant) if merchant else None
        # Build candidates conservatively, skipping rows with non-numeric amounts
        for _, r in df.iterrows():
            try:
                r_amount = float(r.get("amount", 0))
            except (ValueError, TypeError):
                continue
            candidates.append(r)

        # If merchant provided, filter by slug similarity
        if target_slug:
            slug_matches = []
            for r in candidates:
                desc = r.get("description") or ""
                rslug = merchant_slug(desc)
                if not rslug:
                    continue
                # exact or prefix match
                if rslug == target_slug or target_slug in rslug or rslug in target_slug:
                    slug_matches.append(r)
            if len(slug_matches) == 1:
                return slug_matches[0].to_dict()
            elif len(slug_matches) > 1:
                LOG.info("Multiple slug matches found for merchant %s; returning first", merchant)
                return slug_matches[0].to_dict()

        # If nothing found, return None
        return None

    def add_expense_from_txn(self, txn: Dict[str, Any], import_id: str, users: Optional[List[Dict]] = None) -> Union[str, int]:
        """Create a Splitwise expense from normalized transaction data.

        Args:
            txn: Dictionary containing:
                - date (str): Date in YYYY-MM-DD format
                - amount (float): Transaction amount
                - currency (str, optional): Currency code (default: USD)
                - description (str): Transaction description
                - merchant (str, optional): Merchant name (used if description is empty)
            import_id: Unique identifier for this transaction
            users: Optional list of user participation details:
                - user_id (int): Splitwise user ID
                - paid_share (float): Amount paid by this user
                - owed_share (float): Amount owed by this user

        Returns:
            The created expense ID

        Raises:
            RuntimeError: If expense creation fails
        """
        desc = txn.get("description") or txn.get("merchant") or "Imported expense"
        desc_with_marker = f"{desc} {IMPORTED_ID_MARKER}{import_id}]"

        cost = float(txn.get("amount", 0))
        date = txn.get("date")
        currency = txn.get("currency") or DEFAULT_CURRENCY

        # Use SDK Expense objects
        expense = Expense()
        expense.setCost(str(cost))
        expense.setDescription(desc_with_marker)
        expense.setDate(date)
        expense.setCurrencyCode(currency)
        
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
            return created.getId() if hasattr(created, 'getId') else created
        except Exception as e:
            raise RuntimeError(f"Failed to create expense: {str(e)}")

    @cache
    def get_categories(self):
        return self.sObj.getCategories()


# Example usage:
if __name__ == "__main__":
    client = SplitwiseClient()
    print(f"User ID: {client.get_current_user_id()}")

    today = datetime.now().date()
    seven_days_ago = today - timedelta(days=25)
    df = client.get_my_expenses_by_date_range(seven_days_ago, today)
    print(df)
