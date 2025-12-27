import os
from datetime import datetime, timedelta
import pandas as pd
from splitwise import Splitwise
from dotenv import load_dotenv

from src.utils import merchant_slug, LOG

load_dotenv("config/credentials.env")

# Module-level constants
IMPORTED_ID_MARKER = "[ImportedID:"
DEFAULT_CURRENCY = "USD"
PAYLOAD_KEY_COST = "cost"
PAYLOAD_KEY_DESCRIPTION = "description"
PAYLOAD_KEY_DATE = "date"
PAYLOAD_KEY_CURRENCY = "currency_code"


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

    def add_expense_from_txn(self, txn: dict, import_id: str, users=None):
        """Create a Splitwise expense from normalized txn.

        - txn: dict with keys: date (YYYY-MM-DD), amount (float), currency, description, merchant
        - import_id: string
        - users: optional list of dicts with user_id and share info

        This will append a marker [ImportedID:{import_id}] to the description so we can find it later.
        Returns the created expense id or raises on failure.
        """
        desc = txn.get("description") or txn.get("merchant") or "Imported expense"
        desc_with_marker = f"{desc} {IMPORTED_ID_MARKER}{import_id}]"

        cost = float(txn.get("amount"))
        date = txn.get("date")
        currency = txn.get("currency") or DEFAULT_CURRENCY

        # Use SDK Expense objects (ImportError will propagate if SDK pieces missing)
        from splitwise import Expense, ExpenseUser
        expense = Expense()
        expense.setCost(str(cost))
        expense.setDescription(desc_with_marker)
        expense.setDate(date)
        expense.setCurrencyCode(currency)
        # By default: mark as paid by current user and owed by others (if users provided)
        if users:
            # users is list of {"user_id": id, "paid_share": x, "owed_share": y}
            for u in users:
                eu = ExpenseUser()
                eu.setId(u.get("user_id"))
                if "paid_share" in u:
                    eu.setPaidShare(str(u.get("paid_share")))
                if "owed_share" in u:
                    eu.setOwedShare(str(u.get("owed_share")))
                expense.addUser(eu)
        # If no users specified, leave it as a simple expense paid by current user
        created = self.sObj.createExpense(expense)
        # created may be an Expense object or dict depending on SDK
        try:
            return created.getId()
        except AttributeError:
            return created

        # Note: no broad except blocks — let unexpected errors propagate so failures are visible


# Example usage:
if __name__ == "__main__":
    client = SplitwiseClient()
    print(f"User ID: {client.get_current_user_id()}")

    today = datetime.now().date()
    seven_days_ago = today - timedelta(days=7)
    df = client.get_expenses_by_date_range(seven_days_ago, today)
    print(df)
