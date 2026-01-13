"""Helper script to get your Splitwise user ID.

Run this to find your Splitwise user ID, which is needed for the migration scripts.
"""

import os
import sys

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from src.common.splitwise_client import SplitwiseClient


def main():
    """Get current user info from Splitwise API."""
    print("=" * 60)
    print("Fetching Splitwise User Info")
    print("=" * 60)
    
    try:
        client = SplitwiseClient()
        current_user = client.get_current_user()
        
        print(f"\n✅ Connected to Splitwise API")
        print(f"\nYour User Info:")
        print(f"  Name: {current_user.getFirstName()} {current_user.getLastName()}")
        print(f"  Email: {current_user.getEmail()}")
        print(f"  User ID: {current_user.getId()}")
        
        print(f"\n💡 Use this User ID for migration scripts:")
        print(f"   --user-id {current_user.getId()}")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        print("\nMake sure your Splitwise API credentials are set in config/.env")


if __name__ == '__main__':
    main()
