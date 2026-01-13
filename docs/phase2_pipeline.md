# Phase 2: Database-First Import Pipeline

## Overview

Phase 2 implements a **Splitwise-as-source-of-truth** workflow where:

1. Credit card statements are imported to Splitwise API first
2. Successful Splitwise expenses are then saved to the local database
3. Manual edits in Splitwise can be synced back to the database
4. Database tracks Splitwise IDs for reconciliation

This ensures the database always reflects the current state of Splitwise, including any manual adjustments you make (splits, deletions, category changes).

## Architecture

```
┌─────────────────┐
│  Credit Card    │
│   Statement     │
│   (CSV file)    │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│   Pipeline      │  1. Parse CSV
│  process_       │  2. Add to Splitwise
│  statement()    │  3. Save to Database
└────────┬────────┘
         │
         ├──────────────┬──────────────┐
         ▼              ▼              ▼
┌──────────────┐ ┌─────────────┐ ┌──────────────┐
│  Splitwise   │ │  Local DB   │ │ Google       │
│     API      │ │ (SQLite)    │ │ Sheets       │
│              │ │             │ │              │
│ (Source of   │ │ (Cached     │ │ (View only)  │
│  Truth)      │ │  State)     │ │              │
└──────┬───────┘ └──────┬──────┘ └──────────────┘
       │                │
       │  Manual edits  │
       │  (splits,      │
       │   deletes)     │
       │                │
       └────────┬───────┘
                │
         ┌──────▼──────┐
         │  Sync       │
         │  Script     │
         └─────────────┘
```

## Key Components

### 1. Import Pipeline (`src/import_statement/pipeline.py`)

The pipeline now saves transactions to the database after successfully creating them in Splitwise:

```python
# After Splitwise expense is created
sid = client.add_expense_from_txn(...)

# Save to database
db_txn = Transaction(
    date=date,
    merchant=merchant,
    amount=amount,
    splitwise_id=sid,  # Link to Splitwise
    source="amex",
    is_shared=True,
    ...
)
db_txn_id = db.insert_transaction(db_txn)
```

**Important**: Database saves happen **after** Splitwise API calls succeed. If Splitwise fails, nothing is saved to DB.

### 2. Sync Script (`src/db_sync/sync_from_splitwise.py`)

Syncs database with current Splitwise state. Detects and applies:

- **Updates**: Changes to amount, date, description, category
- **Deletions**: Marks DB transactions as deleted if removed from Splitwise
- **Split changes**: Updates amounts if splits are modified

### 3. Database Manager Updates

New methods in `src/database/db_manager.py`:

```python
# Update transaction with Splitwise ID
update_splitwise_id(txn_id, splitwise_id)

# Update transaction from Splitwise data
update_transaction_from_splitwise(splitwise_id, expense_data)

# Mark as deleted
mark_deleted_by_splitwise_id(splitwise_id)

# Get all transactions with Splitwise IDs
get_transactions_with_splitwise_ids(start_date, end_date)
```

## Workflow

### Importing New Statements

```bash
# Activate environment
source .venv/bin/activate
export PYTHONPATH=/home/balaji94/PycharmProjects/SplitwiseImporter

# Import credit card statement
# This will:
# 1. Parse CSV
# 2. Add expenses to Splitwise
# 3. Save successful additions to database
python src/import_statement/pipeline.py \
  --statement data/raw/jan2026.csv \
  --start-date 2026-01-01 \
  --end-date 2026-01-31 \
  --no-sheet  # Skip sheets for now

# Check what was imported
python -c "
from src.database import DatabaseManager
db = DatabaseManager()
print(db.get_stats())
"
```

### Syncing After Manual Edits

After making changes in Splitwise (editing splits, deleting expenses, changing categories):

```bash
# Dry run first (see what will change)
python src/db_sync/sync_from_splitwise.py \
  --year 2026 \
  --dry-run \
  --verbose

# Apply changes
python src/db_sync/sync_from_splitwise.py \
  --year 2026 \
  --live

# Or sync specific date range
python src/db_sync/sync_from_splitwise.py \
  --start-date 2026-01-01 \
  --end-date 2026-01-31 \
  --live
```

### Typical Monthly Workflow

```bash
# 1. Download credit card statement to data/raw/

# 2. Import to Splitwise + Database
python src/import_statement/pipeline.py \
  --statement data/raw/feb2026.csv \
  --start-date 2026-02-01 \
  --end-date 2026-02-28

# 3. Review in Splitwise web/mobile app
#    - Adjust splits for shared expenses
#    - Delete duplicate/incorrect entries
#    - Fix categories if needed

# 4. Sync changes back to database
python src/db_sync/sync_from_splitwise.py --year 2026 --live

# 5. Export to Google Sheets (Phase 3 - not yet implemented)
# python src/export/export_to_sheets.py --year 2026
```

## Database Schema Highlights

Key fields for Phase 2 tracking:

```sql
CREATE TABLE transactions (
    id INTEGER PRIMARY KEY,
    
    -- Core transaction data
    date TEXT NOT NULL,
    merchant TEXT NOT NULL,
    amount REAL NOT NULL,
    
    -- Splitwise integration
    splitwise_id INTEGER UNIQUE,           -- Links to Splitwise expense
    splitwise_deleted_at TEXT,             -- Timestamp if deleted in Splitwise
    
    -- Source tracking
    source TEXT NOT NULL,                  -- amex, visa, splitwise, manual
    source_file TEXT,                      -- Original CSV filename
    
    -- Sync tracking
    written_to_sheet BOOLEAN DEFAULT 0,    -- Phase 3: sheets sync status
    
    -- Metadata
    imported_at TEXT NOT NULL,             -- When first created
    updated_at TEXT,                       -- Last sync/update time
    notes TEXT
);
```

## Command Reference

### Import Pipeline

```bash
# Basic import (dry run)
python src/import_statement/pipeline.py \
  --statement data/raw/statement.csv \
  --dry-run \
  --no-sheet

# Live import with date range
python src/import_statement/pipeline.py \
  --statement data/raw/statement.csv \
  --start-date 2026-01-01 \
  --end-date 2026-01-31

# Batch processing (limit + offset)
python src/import_statement/pipeline.py \
  --statement data/raw/statement.csv \
  --limit 50 \
  --offset 0

# Reprocess specific merchant
python src/import_statement/pipeline.py \
  --statement data/raw/statement.csv \
  --merchant-filter "Amazon"
```

### Sync Script

```bash
# Dry run (default) - see changes without applying
python src/db_sync/sync_from_splitwise.py --year 2026

# Dry run with verbose output
python src/db_sync/sync_from_splitwise.py \
  --year 2026 \
  --verbose

# Apply changes (live mode)
python src/db_sync/sync_from_splitwise.py \
  --year 2026 \
  --live

# Sync specific date range
python src/db_sync/sync_from_splitwise.py \
  --start-date 2026-01-01 \
  --end-date 2026-03-31 \
  --live
```

### Database Queries

```bash
# Check database stats
python -c "from src.database import DatabaseManager; import json; print(json.dumps(DatabaseManager().get_stats(), indent=2))"

# View recent transactions
python -c "
from src.database import DatabaseManager
db = DatabaseManager()
txns = db.get_transactions_by_date_range('2026-01-01', '2026-01-31')
for t in txns[:10]:
    print(f'{t.date} | {t.merchant:30} | \${t.amount:7.2f} | SW:{t.splitwise_id}')
"

# Check for transactions without Splitwise IDs
python -c "
from src.database import DatabaseManager
db = DatabaseManager()
conn = db.get_connection()
cursor = conn.cursor()
cursor.execute('SELECT COUNT(*) FROM transactions WHERE splitwise_id IS NULL')
print(f'Transactions without Splitwise ID: {cursor.fetchone()[0]}')
conn.close()
"
```

## Error Handling

### If Splitwise API Call Fails

- Transaction is **not saved** to database
- Error logged in processed CSV output
- Can retry by re-running pipeline (cache prevents duplicates)

### If Database Save Fails

- Splitwise expense **already created** (cannot be undone automatically)
- Warning logged with Splitwise ID
- Can manually add to DB using:

```python
from src.database import DatabaseManager, Transaction
from datetime import datetime

db = DatabaseManager()
txn = Transaction(
    date="2026-01-15",
    merchant="Failed Merchant",
    amount=50.00,
    splitwise_id=12345,  # From Splitwise
    source="amex",
    imported_at=datetime.utcnow().isoformat(),
)
db.insert_transaction(txn)
```

### If Sync Detects Unexpected Changes

- Dry run shows all changes before applying
- Review output carefully before running with `--live`
- Changes can be reverted by re-syncing or manual SQL updates

## Phase 3 Preview

Next phase will implement:

1. **Export to Google Sheets**: Only write unwritten transactions
2. **Mark as written**: Track `written_to_sheet` flag
3. **Append-only sheets**: Never overwrite, only append new rows
4. **Summary tabs**: Monthly rollups, budget tracking

## Troubleshooting

### "ModuleNotFoundError: No module named 'src'"

Always set `PYTHONPATH` before running:

```bash
export PYTHONPATH=/home/balaji94/PycharmProjects/SplitwiseImporter
```

Or use VS Code launch configurations which set this automatically.

### Duplicate transactions in database

Check for duplicates:

```python
from src.database import DatabaseManager
db = DatabaseManager()

# Find by merchant and date
dups = db.find_potential_duplicates(
    date="2026-01-15",
    merchant="Amazon",
    amount=29.99,
)
print(f"Found {len(dups)} potential duplicates")
```

### Splitwise ID exists but transaction not in DB

Run sync to fetch from Splitwise:

```bash
# This will create a migration/backfill tool in a future update
# For now, manually check Splitwise and add to DB
```

## Best Practices

1. **Always dry-run first**: Use `--dry-run` for imports, default for sync
2. **Backup database**: Copy `data/transactions.db` before major operations
3. **Review Splitwise weekly**: Make edits in Splitwise, then sync to DB
4. **Sync after edits**: Run sync script after making changes in Splitwise
5. **Check stats regularly**: Use `db.get_stats()` to monitor data quality

## See Also

- [Phase 1: Database Migration](database_migration.md)
- [Phase 3: Google Sheets Export](phase3_sheets_export.md) (coming soon)
- [Database Schema](../src/database/schema.py)
- [Import Pipeline](../src/import_statement/pipeline.py)
- [Sync Script](../src/db_sync/sync_from_splitwise.py)
