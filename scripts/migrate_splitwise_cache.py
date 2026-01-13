"""Migrate data from Splitwise JSON cache files to database.

This script imports transactions from the Splitwise expense cache files
(splitwise_expense_details_2025.json, splitwise_expense_details_2026.json)
into the local SQLite database.
"""

import json
import os
import sys
from datetime import datetime
from typing import Dict, Any

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from src.database import DatabaseManager, Transaction
from src.database.models import ImportLog


def parse_splitwise_expense(expense: Dict[str, Any], current_user_id: int) -> Transaction:
    """Convert Splitwise expense JSON to Transaction object.
    
    Args:
        expense: Splitwise expense dictionary
        current_user_id: Your Splitwise user ID
        
    Returns:
        Transaction object
    """
    # Extract basic fields
    date = expense.get('date', '')
    description = expense.get('description', '')
    merchant = description  # Use description as merchant for now
    
    # Get your share of the cost
    cost = float(expense.get('cost', 0))
    
    # Determine amount based on who owes whom
    users = expense.get('users', [])
    your_share = 0.0
    
    for user in users:
        if user.get('user', {}).get('id') == current_user_id:
            owed_share = float(user.get('owed_share', 0))
            paid_share = float(user.get('paid_share', 0))
            # Positive if you owe, negative if you're owed
            your_share = paid_share - owed_share
            break
    
    # Get category info
    category_data = expense.get('category', {})
    category = category_data.get('name', 'Uncategorized')
    category_id = category_data.get('id')
    
    subcategory_data = category_data.get('subcategories', [{}])[0] if category_data.get('subcategories') else {}
    subcategory = subcategory_data.get('name', '')
    subcategory_id = subcategory_data.get('id')
    
    # Check if deleted
    deleted_at = expense.get('deleted_at')
    
    # Determine if refund (negative cost or "payment" category)
    is_payment = expense.get('payment', False)
    is_refund = cost < 0 or is_payment
    
    # Create transaction
    txn = Transaction(
        date=date,
        merchant=merchant,
        description=description,
        raw_description=description,
        amount=your_share,
        raw_amount=cost,
        source='splitwise',
        category=category,
        subcategory=subcategory,
        category_id=category_id,
        subcategory_id=subcategory_id,
        is_refund=is_refund,
        is_shared=True,
        currency=expense.get('currency_code', 'USD'),
        splitwise_id=expense.get('id'),
        splitwise_deleted_at=deleted_at,
        imported_at=datetime.utcnow().isoformat(),
        notes=f"Imported from Splitwise cache"
    )
    
    return txn


def migrate_splitwise_cache(
    cache_file: str,
    db_manager: DatabaseManager,
    current_user_id: int,
    dry_run: bool = False
) -> Dict[str, int]:
    """Migrate Splitwise cache file to database.
    
    Args:
        cache_file: Path to Splitwise cache JSON file
        db_manager: DatabaseManager instance
        current_user_id: Your Splitwise user ID
        dry_run: If True, don't actually insert
        
    Returns:
        Dictionary with import statistics
    """
    print(f"\n{'[DRY RUN] ' if dry_run else ''}Processing: {cache_file}")
    
    # Load cache file
    if not os.path.exists(cache_file):
        print(f"❌ File not found: {cache_file}")
        return {'attempted': 0, 'imported': 0, 'skipped': 0, 'failed': 0}
    
    with open(cache_file, 'r') as f:
        expenses = json.load(f)
    
    print(f"Found {len(expenses)} expenses in cache")
    
    stats = {
        'attempted': len(expenses),
        'imported': 0,
        'skipped': 0,
        'failed': 0
    }
    
    transactions_to_import = []
    
    for expense in expenses:
        try:
            # Check if already exists by splitwise_id
            splitwise_id = expense.get('id')
            if splitwise_id:
                existing = db_manager.get_transaction_by_splitwise_id(splitwise_id)
                if existing:
                    print(f"⏭️  Skipping duplicate: Splitwise ID {splitwise_id}")
                    stats['skipped'] += 1
                    continue
            
            # Parse expense
            txn = parse_splitwise_expense(expense, current_user_id)
            
            if not dry_run:
                transactions_to_import.append(txn)
            else:
                print(f"  Would import: {txn.date} | {txn.merchant} | ${txn.amount:.2f}")
            
            stats['imported'] += 1
            
        except Exception as e:
            print(f"❌ Error processing expense {expense.get('id')}: {e}")
            stats['failed'] += 1
    
    # Batch insert
    if not dry_run and transactions_to_import:
        print(f"\nInserting {len(transactions_to_import)} transactions...")
        db_manager.insert_transactions_batch(transactions_to_import)
        print(f"✅ Inserted {len(transactions_to_import)} transactions")
    
    return stats


def main():
    """Main migration script."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Migrate Splitwise cache to database')
    parser.add_argument('--user-id', type=int, required=True,
                       help='Your Splitwise user ID')
    parser.add_argument('--cache-dir', default='data',
                       help='Directory containing cache files (default: data)')
    parser.add_argument('--cache-file', 
                       help='Specific cache file to import (overrides --cache-dir)')
    parser.add_argument('--dry-run', action='store_true',
                       help='Preview without inserting')
    parser.add_argument('--db-path', 
                       help='Database path (default: data/transactions.db)')
    
    args = parser.parse_args()
    
    # Initialize database
    db_manager = DatabaseManager(db_path=args.db_path)
    
    print("=" * 60)
    print("Splitwise Cache → Database Migration")
    print("=" * 60)
    
    # Find cache files
    cache_files = []
    if args.cache_file:
        cache_files = [args.cache_file]
    else:
        cache_dir = os.path.join(project_root, args.cache_dir)
        for filename in os.listdir(cache_dir):
            if filename.startswith('splitwise_expense_details_') and filename.endswith('.json'):
                cache_files.append(os.path.join(cache_dir, filename))
    
    if not cache_files:
        print("❌ No cache files found")
        return
    
    print(f"Found {len(cache_files)} cache file(s)")
    
    # Migrate each file
    total_stats = {
        'attempted': 0,
        'imported': 0,
        'skipped': 0,
        'failed': 0
    }
    
    for cache_file in sorted(cache_files):
        stats = migrate_splitwise_cache(
            cache_file=cache_file,
            db_manager=db_manager,
            current_user_id=args.user_id,
            dry_run=args.dry_run
        )
        
        for key in total_stats:
            total_stats[key] += stats[key]
    
    # Log import (if not dry run)
    if not args.dry_run:
        log = ImportLog(
            timestamp=datetime.utcnow().isoformat(),
            source_type='splitwise_cache',
            source_identifier=args.cache_dir,
            records_attempted=total_stats['attempted'],
            records_imported=total_stats['imported'],
            records_skipped=total_stats['skipped'],
            records_failed=total_stats['failed']
        )
        db_manager.log_import(log)
    
    # Print summary
    print("\n" + "=" * 60)
    print("MIGRATION SUMMARY")
    print("=" * 60)
    print(f"Total expenses processed: {total_stats['attempted']}")
    print(f"✅ Imported: {total_stats['imported']}")
    print(f"⏭️  Skipped (duplicates): {total_stats['skipped']}")
    print(f"❌ Failed: {total_stats['failed']}")
    
    if args.dry_run:
        print("\n⚠️  This was a DRY RUN - no data was inserted")
    
    # Show database stats
    if not args.dry_run:
        print("\n" + "=" * 60)
        print("DATABASE STATS")
        print("=" * 60)
        stats = db_manager.get_stats()
        print(f"Total transactions: {stats['total_transactions']}")
        print(f"By source:")
        for source, count in stats['by_source'].items():
            print(f"  - {source}: {count}")
        print(f"Date range: {stats['date_range']['min']} to {stats['date_range']['max']}")


if __name__ == '__main__':
    main()
