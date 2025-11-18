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
                "friends_split": [f"{u.getFirstName()}: {u.getPaidShare()}" for u in e.getUsers()]
            }
            for e in filtered_expenses
        ]
        df = pd.DataFrame(data)
        return df

# Example usage:
if __name__ == "__main__":
    client = SplitwiseClient()
    print(f"User ID: {client.get_current_user_id()}")

    today = datetime.now().date()
    seven_days_ago = today - timedelta(days=7)
    df = client.get_expenses_by_date_range(seven_days_ago, today)
    print(df)
