"""Migrate data from Google Sheets to database.

This script imports transactions from your Google Sheets expense tracking
sheet into the local SQLite database. Useful for importing historical data
that's already been processed and exported to Sheets.
"""

import os
import sys
from datetime import datetime
from typing import List

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from src.database import DatabaseManager, Transaction
from src.database.models import ImportLog
from src.common.sheets_sync import GoogleSheetsSync
from src.constants.config import Config


def parse_sheet_row(row: dict, source: str = 'sheets_import') -> Transaction:
    """Convert Google Sheets row to Transaction object.
    
    Args:
        row: Dictionary with sheet column names as keys
        source: Source identifier (default: 'sheets_import')
        
    Returns:
        Transaction object
    """
    # Extract fields - adjust column names based on your sheet structure
    date = row.get('Date', row.get('date', ''))
    merchant = row.get('Merchant', row.get('merchant', row.get('Description', '')))
    description = row.get('Description', row.get('description', merchant))
    
    # Amount
    amount_str = row.get('Amount', row.get('amount', row.get('Cost', '0')))
    try:
        amount = float(str(amount_str).replace('$', '').replace(',', ''))
    except (ValueError, AttributeError):
        amount = 0.0
    
    # Category
    category = row.get('Category', row.get('category', ''))
    subcategory = row.get('Subcategory', row.get('subcategory', ''))
    
    # Splitwise ID
    splitwise_id_str = row.get('Expense ID', row.get('expense_id', row.get('Splitwise ID', '')))
    try:
        splitwise_id = int(splitwise_id_str) if splitwise_id_str else None
    except (ValueError, TypeError):
        splitwise_id = None
    
    # Currency
    currency = row.get('Currency', row.get('currency', 'USD'))
    
    # Notes
    notes = row.get('Notes', row.get('notes', ''))
    
    txn = Transaction(
        date=date,
        merchant=merchant,
        description=description,
        amount=amount,
        source=source,
        category=category,
        subcategory=subcategory,
        splitwise_id=splitwise_id,
        currency=currency,
        is_shared=bool(splitwise_id),  # If it has a Splitwise ID, it was shared
        written_to_sheet=True,  # Already in sheets
        imported_at=datetime.utcnow().isoformat(),
        notes=f"Imported from Google Sheets. Original notes: {notes}" if notes else "Imported from Google Sheets"
    )
    
    return txn


def migrate_sheet_tab(
    sheets_sync: GoogleSheetsSync,
    worksheet_name: str,
    db_manager: DatabaseManager,
    source: str = 'sheets_import',
    dry_run: bool = False
) -> dict:
    """Migrate one sheet tab to database.
    
    Args:
        sheets_sync: GoogleSheetsSync instance
        worksheet_name: Name of the worksheet tab
        db_manager: DatabaseManager instance
        source: Source identifier for these transactions
        dry_run: If True, preview without inserting
        
    Returns:
        Dictionary with import statistics
    """
    print(f"\n{'[DRY RUN] ' if dry_run else ''}Processing sheet: {worksheet_name}")
    
    # Read data from sheet
    try:
        data = sheets_sync.read_data(worksheet_name)
    except Exception as e:
        print(f"❌ Error reading sheet '{worksheet_name}': {e}")
        return {'attempted': 0, 'imported': 0, 'skipped': 0, 'failed': 0}
    
    if not data:
        print(f"⚠️  No data found in sheet '{worksheet_name}'")
        return {'attempted': 0, 'imported': 0, 'skipped': 0, 'failed': 0}
    
    print(f"Found {len(data)} rows in sheet")
    
    stats = {
        'attempted': len(data),
        'imported': 0,
        'skipped': 0,
        'failed': 0
    }
    
    transactions_to_import = []
    
    for idx, row in enumerate(data, start=1):
        try:
            # Parse row
            txn = parse_sheet_row(row, source=source)
            
            # Skip if no date or amount
            if not txn.date or txn.amount == 0:
                stats['skipped'] += 1
                continue
            
            # Check for duplicates by splitwise_id
            if txn.splitwise_id:
                existing = db_manager.get_transaction_by_splitwise_id(txn.splitwise_id)
                if existing:
                    print(f"⏭️  Row {idx}: Duplicate Splitwise ID {txn.splitwise_id}")
                    stats['skipped'] += 1
                    continue
            
            # Check for potential duplicates by date/merchant/amount
            potential_dupes = db_manager.find_potential_duplicates(
                date=txn.date,
                merchant=txn.merchant,
                amount=txn.amount,
                tolerance_days=1,
                amount_tolerance=0.01
            )
            
            if potential_dupes:
                print(f"⏭️  Row {idx}: Potential duplicate of existing transaction (date={txn.date}, merchant={txn.merchant})")
                stats['skipped'] += 1
                continue
            
            if not dry_run:
                transactions_to_import.append(txn)
            else:
                print(f"  Row {idx}: Would import {txn.date} | {txn.merchant} | ${txn.amount:.2f}")
            
            stats['imported'] += 1
            
        except Exception as e:
            print(f"❌ Error processing row {idx}: {e}")
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
    
    parser = argparse.ArgumentParser(description='Migrate Google Sheets data to database')
    parser.add_argument('--sheet-name', required=True,
                       help='Name of the worksheet tab to import (e.g., "Expenses 2025")')
    parser.add_argument('--source', default='sheets_import',
                       help='Source identifier for imported transactions')
    parser.add_argument('--dry-run', action='store_true',
                       help='Preview without inserting')
    parser.add_argument('--db-path',
                       help='Database path (default: data/transactions.db)')
    
    args = parser.parse_args()
    
    # Initialize
    config = Config()
    db_manager = DatabaseManager(db_path=args.db_path)
    sheets_sync = GoogleSheetsSync(spreadsheet_key=config.spreadsheet_key)
    
    print("=" * 60)
    print("Google Sheets → Database Migration")
    print("=" * 60)
    print(f"Sheet: {args.sheet_name}")
    
    # Migrate
    stats = migrate_sheet_tab(
        sheets_sync=sheets_sync,
        worksheet_name=args.sheet_name,
        db_manager=db_manager,
        source=args.source,
        dry_run=args.dry_run
    )
    
    # Log import (if not dry run)
    if not args.dry_run:
        log = ImportLog(
            timestamp=datetime.utcnow().isoformat(),
            source_type='google_sheets',
            source_identifier=args.sheet_name,
            records_attempted=stats['attempted'],
            records_imported=stats['imported'],
            records_skipped=stats['skipped'],
            records_failed=stats['failed']
        )
        db_manager.log_import(log)
    
    # Print summary
    print("\n" + "=" * 60)
    print("MIGRATION SUMMARY")
    print("=" * 60)
    print(f"Total rows processed: {stats['attempted']}")
    print(f"✅ Imported: {stats['imported']}")
    print(f"⏭️  Skipped (duplicates/invalid): {stats['skipped']}")
    print(f"❌ Failed: {stats['failed']}")
    
    if args.dry_run:
        print("\n⚠️  This was a DRY RUN - no data was inserted")
    
    # Show database stats
    if not args.dry_run:
        print("\n" + "=" * 60)
        print("DATABASE STATS")
        print("=" * 60)
        db_stats = db_manager.get_stats()
        print(f"Total transactions: {db_stats['total_transactions']}")
        print(f"By source:")
        for source, count in db_stats['by_source'].items():
            print(f"  - {source}: {count}")
        print(f"Date range: {db_stats['date_range']['min']} to {db_stats['date_range']['max']}")


if __name__ == '__main__':
    main()
