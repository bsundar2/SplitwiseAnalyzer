"""Migration script to add refund tracking columns to existing database.

This script is IDEMPOTENT - it can be run multiple times safely:
- Checks which columns already exist before adding them
- Only adds missing columns
- Creates indexes with IF NOT EXISTS
- No data rows are inserted or modified

Run this script to add the new refund-related columns to an existing
transactions table that was created before the refund feature was added.

Usage:
    # Dry run to preview changes
    python -m src.database.migrate_refund_columns --dry-run
    
    # Apply changes
    python -m src.database.migrate_refund_columns
    
    # Specify custom database path
    python -m src.database.migrate_refund_columns --db-path /path/to/db.db
"""

import argparse
import sqlite3
from pathlib import Path

from src.common.utils import LOG


def get_existing_columns(cursor) -> set:
    """Get list of existing column names in transactions table."""
    cursor.execute("PRAGMA table_info(transactions)")
    return {row[1] for row in cursor.fetchall()}


def migrate_database(db_path: str, dry_run: bool = False):
    """Add refund tracking columns to transactions table.
    
    This function is IDEMPOTENT:
    - Checks existing schema before making changes
    - Only adds columns that don't already exist
    - Indexes created with IF NOT EXISTS
    - Safe to run multiple times
    
    Args:
        db_path: Path to SQLite database file
        dry_run: If True, preview changes without modifying database
    """
    LOG.info("=" * 60)
    LOG.info("Refund Columns Migration Script")
    LOG.info("=" * 60)
    LOG.info("Database: %s", db_path)
    LOG.info("Mode: %s", "DRY RUN (no changes)" if dry_run else "LIVE (will modify database)")
    LOG.info("Idempotency: Safe to run multiple times")
    LOG.info("=" * 60)
    
    # Connect to database
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Check existing columns
        existing_cols = get_existing_columns(cursor)
        LOG.info("Found %d existing columns in transactions table", len(existing_cols))
        
        # Define new refund columns to add
        new_columns = [
            ("cc_reference_id", "TEXT", None),
            ("refund_for_txn_id", "INTEGER", None),
            ("refund_for_splitwise_id", "INTEGER", None),
            ("refund_created_at", "TEXT", None),
            ("reconciliation_status", "TEXT", "'pending'"),
            ("refund_match_method", "TEXT", None),
            ("is_partial_refund", "BOOLEAN", "0"),
            ("refund_percentage", "REAL", None),
        ]
        
        # Check which columns need to be added
        columns_to_add = [
            (name, dtype, default) 
            for name, dtype, default in new_columns 
            if name not in existing_cols
        ]
        
        if not columns_to_add:
            LOG.info("\n" + "=" * 60)
            LOG.info("✓ All refund columns already exist - no migration needed")
            LOG.info("✓ Database is up to date - safe to run refund processing")
            LOG.info("=" * 60)
            return
        
        LOG.info("\nColumns to add: %d", len(columns_to_add))
        for name, dtype, default in columns_to_add:
            default_str = f" DEFAULT {default}" if default else ""
            LOG.info("  - %s %s%s", name, dtype, default_str)
        
        if dry_run:
            LOG.info("\nDry run - no changes made")
            return
        
        # Add each column
        LOG.info("\nAdding columns...")
        for name, dtype, default in columns_to_add:
            default_clause = f" DEFAULT {default}" if default else ""
            sql = f"ALTER TABLE transactions ADD COLUMN {name} {dtype}{default_clause}"
            LOG.info("  Executing: %s", sql)
            cursor.execute(sql)
        
        # Create new indexes
        LOG.info("\nCreating indexes...")
        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_cc_reference ON transactions(cc_reference_id)",
            "CREATE INDEX IF NOT EXISTS idx_is_refund ON transactions(is_refund)",
            "CREATE INDEX IF NOT EXISTS idx_refund_for_txn ON transactions(refund_for_txn_id)",
            "CREATE INDEX IF NOT EXISTS idx_reconciliation_status ON transactions(reconciliation_status)",
        ]
        
        for sql in indexes:
            LOG.info("  Executing: %s", sql)
            cursor.execute(sql)
        
        # Commit changes
        conn.commit()
        LOG.info("\n✓ Migration completed successfully")
        
        # Verify
        new_cols = get_existing_columns(cursor)
        LOG.info("✓ Transactions table now has %d columns", len(new_cols))
        
    except Exception as e:
        conn.rollback()
        LOG.error("✗ Migration failed: %s", e)
        raise
    finally:
        conn.close()


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Add refund tracking columns to existing database"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without modifying database",
    )
    parser.add_argument(
        "--db-path",
        default="data/transactions.db",
        help="Path to database file (default: data/transactions.db)",
    )
    
    args = parser.parse_args()
    
    # Resolve database path
    db_path = Path(args.db_path)
    if not db_path.is_absolute():
        # Assume relative to project root
        project_root = Path(__file__).parent.parent.parent
        db_path = project_root / db_path
    
    if not db_path.exists():
        LOG.error("Database file not found: %s", db_path)
        return 1
    
    migrate_database(str(db_path), dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv("config/.env")
    
    exit(main())
