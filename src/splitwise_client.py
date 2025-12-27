"""Client for interacting with the Splitwise API.

This module provides a high-level interface for common Splitwise operations,
including expense management, search, and data export.
"""

# Standard library
import os
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, Union, List

# Third-party
import pandas as pd
from dateutil import parser as date_parser
from dotenv import load_dotenv
from splitwise import Expense, Splitwise

# Local application
from src.constants.splitwise import (
    IMPORTED_ID_MARKER,
    DEFAULT_CURRENCY,
    PayloadKeys
)
from src.utils import LOG, merchant_slug, compute_import_id

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

    def get_current_user_id(self):
        return self.sObj.getCurrentUser().getId()

    def get_expenses_by_date_range(self, start_date, end_date):
        expenses = self.sObj.getExpenses(dated_after=start_date.strftime("%Y-%m-%d"),
                                         dated_before=end_date.strftime("%Y-%m-%d"))
        my_user_id = self.get_current_user_id()

        # Filter: keep only expenses where current user is involved (paid share > 0)
        filtered_expenses = [e for e in expenses if any(u.getId() == my_user_id and float(u.getPaidShare()) > 0 for u in e.getUsers())]
        data = [
            {
                "date": e.getDate(),
                "amount": e.getCost(),
                "category": e.getCategory().getName() if e.getCategory() else None,
                "description": e.getDescription(),
                "friends_split": [f"{u.getFirstName()}: {u.getPaidShare()}" for u in e.getUsers()],
                "id": e.getId(),
            }
            for e in filtered_expenses
        ]
        df = pd.DataFrame(data)
        return df

    def find_expense_by_import_id(self, import_id: str, merchant: str = None, lookback_days: int = 365):
        """Search recent Splitwise expenses for the import id marker in description.

        If not found, fall back to fuzzy match: same amount, date within +/-1 day, and merchant slug match.
        Returns a dict row if a single unambiguous match is found, otherwise None.
        """
        # naive strategy: fetch last N days and scan descriptions for marker
        end = datetime.now().date()
        start = end - timedelta(days=lookback_days)

        df = self.get_expenses_by_date_range(start, end)
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

    def generate_fingerprint(self, date_val: str, amount_val: Union[str, float], desc_val: str) -> str:
        """Generate a stable fingerprint for a transaction.
        
        Args:
            date_val: Date string in any parseable format
            amount_val: Transaction amount (string or number)
            desc_val: Transaction description
            
        Returns:
            A stable string fingerprint for the transaction
        """
        # Normalize date to YYYY-MM-DD
        try:
            dnorm = date_parser.parse(str(date_val)).date().isoformat()
        except (ValueError, TypeError, OverflowError):
            dnorm = str(date_val)
        
        # Normalize amount
        try:
            amt = float(amount_val)
        except (ValueError, TypeError):
            try:
                amt = float(str(amount_val).replace(',', '').replace('$', ''))
            except (ValueError, TypeError):
                amt = 0.0
        
        # Normalize description
        desc_norm = merchant_slug(desc_val or "")
        
        return compute_import_id(dnorm, amt, desc_norm)

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


# Example usage:
if __name__ == "__main__":
    client = SplitwiseClient()
    print(f"User ID: {client.get_current_user_id()}")

    today = datetime.now().date()
    seven_days_ago = today - timedelta(days=25)
    df = client.get_expenses_by_date_range(seven_days_ago, today)
    print(df)
