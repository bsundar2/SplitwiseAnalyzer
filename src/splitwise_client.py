import os
from datetime import datetime, timedelta
import pandas as pd
from splitwise import Splitwise
from dotenv import load_dotenv


# Handles Splitwise API/CSV integration
class SplitwiseClient:
    def __init__(self, env_path="config/credentials.env"):
        # Use absolute path for dotenv
        abs_env_path = os.path.abspath(env_path)
        load_dotenv(abs_env_path, verbose=True)
        self.consumer_key = os.getenv("SPLITWISE_CONSUMER_KEY")
        self.consumer_secret = os.getenv("SPLITWISE_CONSUMER_SECRET")
        self.api_key = os.getenv("SPLITWISE_API_KEY")
        # Error handling for missing env vars
        if not all([self.consumer_key, self.consumer_secret, self.api_key]):
            raise ValueError("One or more Splitwise credentials are missing. Check config/credentials.env and variable names.")
        self.sObj = Splitwise(self.consumer_key, self.consumer_secret, api_key=self.api_key)

    def get_expenses_last_7_days(self):
        today = datetime.now().date()
        seven_days_ago = today - timedelta(days=7)
        expenses = self.sObj.getExpenses(dated_after=seven_days_ago.strftime("%Y-%m-%d"),
                                         dated_before=today.strftime("%Y-%m-%d"))
        data = []
        for e in expenses:
            friends_split = [p.getFirstName() + ": " + str(p.getPaidShare()) for p in e.getUsers()]
            data.append({
                "date": e.getDate(),
                "amount": e.getCost(),
                "category": e.getCategory().getName() if e.getCategory() else None,
                "description": e.getDescription(),
                "friends_split": friends_split
            })
        df = pd.DataFrame(data)
        # Filter: keep only expenses where 'Balaji' is involved (paid share > 0 or present)
        def balaji_involved(friends_split):
            for entry in friends_split:
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
    df = client.get_expenses_last_7_days()
    print(df)
