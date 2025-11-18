import os
from datetime import datetime, timedelta
import pandas as pd
from splitwise import Splitwise
from dotenv import load_dotenv

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
        data = []
        expenses = self.sObj.getExpenses(dated_after=start_date.strftime("%Y-%m-%d"),
                                         dated_before=end_date.strftime("%Y-%m-%d"))

        for expense in expenses:
            friends_split = [user.getFirstName() + ": " + str(user.getPaidShare()) for user in expense.getUsers()]
            data.append({
                "date": expense.getDate(),
                "amount": expense.getCost(),
                "category": expense.getCategory().getName() if expense.getCategory() else None,
                "description": expense.getDescription(),
                "friends_split": friends_split
            })
        df = pd.DataFrame(data)

        def balaji_involved(split_entry):
            """Filter: keep only expenses where 'Balaji' is involved (paid share > 0 or present)"""
            for entry in split_entry:
                if "Balaji" in entry:
                    # Extract paid share value
                    try:
                        paid_share = float(entry.split(": ")[-1])
                        if paid_share > 0:
                            return True
                    except Exception:
                        continue
            return False
        df = df[df["friends_split"].apply(balaji_involved)]
        return df

# Example usage:
if __name__ == "__main__":
    client = SplitwiseClient()
    print(f"User ID: {client.get_current_user_id()}")

    today = datetime.now().date()
    seven_days_ago = today - timedelta(days=7)
    df = client.get_expenses_by_date_range(seven_days_ago, today)
    print(df)
