# Database & Sync Guide

Complete guide for the local SQLite database and Splitwise synchronization system.

## Overview

The system uses a **Splitwise-as-source-of-truth** architecture:

- **Splitwise API**: Source of truth for all transactions
- **Local SQLite Database**: Synced mirror of Splitwise data
- **Google Sheets**: View-only cache (Phase 3)

## Architecture

```
┌─────────────┐
│ Credit Card │
│  Statement  │
│  (CSV)      │
└──────┬──────┘
       │
       ▼
┌─────────────┐  1. Parse CSV
│  Pipeline   │  2. Add to Splitwise
│  process_   │  3. Save to Database
│  statement  │
└──────┬──────┘
       │
       ├───────────┬───────────┐
       ▼           ▼           ▼
┌──────────┐ ┌──────────┐ ┌──────────┐
│Splitwise │ │Local DB  │ │ Google   │
│   API    │◄┤(SQLite)  │ │ Sheets   │
│          │ │          │ │          │
│(Source of│ │(Synced   │ │(View     │
│Truth)    │ │Mirror)   │ │Cache)    │
└────┬─────┘ └──────────┘ └──────────┘
     │            ▲
     │ Manual     │
     │ Edits      │
     └────────────┘
          │
   ┌──────▼──────┐
   │  Unified    │  • Insert new
   │   Sync      │  • Update changed
   │   Script    │  • Mark deleted
   └─────────────┘
```

## Database Schema

### `transactions` table
- **Core**: date, merchant, description, amount (signed)
- **Categorization**: category, subcategory, category_id, subcategory_id
- **Source tracking**: source (amex/visa/splitwise), source_file
- **Characteristics**: is_refund, is_shared, currency
- **Splitwise integration**: splitwise_id, splitwise_deleted_at
- **Sync tracking**: written_to_sheet, sheet_year, sheet_row_id
- **Metadata**: imported_at, updated_at, notes
- **Deduplication**: raw_description, statement_date, raw_amount

### Other tables
- `duplicate_checks` - Track potential duplicates
- `import_log` - Audit trail for all operations

---

## Getting Started

### Prerequisites

```bash
# Activate virtual environment
source .venv/bin/activate

# Set Python path (required for imports)
export PYTHONPATH=/home/balaji94/PycharmProjects/SplitwiseImporter
```

### Initial Historical Import

Import existing Splitwise data into the database:

```bash
# Dry run first (see what would be imported)
python src/db_sync/sync_from_splitwise.py --year 2025 --dry-run --verbose

# Import 2025 data
python src/db_sync/sync_from_splitwise.py --year 2025 --live

# Import multiple years
python src/db_sync/sync_from_splitwise.py --years 2023 2024 2025 2026 --live
```

### Verify Import

```bash
python -c "
from src.database import DatabaseManager
import json
db = DatabaseManager()
print(json.dumps(db.get_stats(), indent=2))
"
```

Expected output:
```json
{
  "total_transactions": 1654,
  "by_source": {"splitwise": 1654},
  "in_splitwise": 1654,
  "date_range": {"min": "2025-01-01", "max": "2026-01-12"}
}
```

---

## Unified Sync Script

The `sync_from_splitwise.py` script handles **all** Splitwise ↔ Database operations:

### What It Does

```python
for each expense in Splitwise:
    if not in database:
        → INSERT (migration/new expense)
    elif changed:
        → UPDATE (sync existing)

for each transaction in database:
    if not in Splitwise:
        → MARK DELETED
```

### Use Cases

| Scenario | Command | Result |
|----------|---------|--------|
| Initial migration | `--year 2025 --live` | Inserts all 2025 Splitwise expenses |
| Add missing expenses | `--year 2026 --live` | Inserts only new expenses |
| Sync after edits | `--year 2026 --live` | Updates changed, marks deleted |
| Check before apply | `--year 2026 --dry-run` | Shows what would change (safe) |
| Multi-year sync | `--years 2024 2025 --live` | Syncs multiple years |

### Command Reference

```bash
# Dry run (default, safe mode)
python src/db_sync/sync_from_splitwise.py --year 2026

# Dry run with verbose output (shows all transactions)
python src/db_sync/sync_from_splitwise.py --year 2026 --verbose

# Live mode (apply changes)
python src/db_sync/sync_from_splitwise.py --year 2026 --live

# Specific date range
python src/db_sync/sync_from_splitwise.py \
  --start-date 2026-01-01 \
  --end-date 2026-03-31 \
  --live

# Multiple years at once
python src/db_sync/sync_from_splitwise.py --years 2025 2026 --live
```

### Output Example

```
Syncing database with Splitwise
Date range: 2026-01-01 to 2026-12-31
Mode: LIVE
============================================================

📊 Fetching transactions from database...
   Found 45 transactions with Splitwise IDs in DB

📥 Fetching expenses from Splitwise API...
   Found 48 expenses in Splitwise

🔄 Processing 48 expenses from Splitwise...

  ➕ NEW: ID 12345 | Starbucks | 2026-01-15 | $5.50
  ✏️  UPDATED: ID 12340 | Amazon | amount: $25.00 → $27.50
  🗑️  DELETED: ID 12320 | Duplicate entry | 2026-01-10 | $10.00

Sync Summary
============================================================
  Expenses checked:        48
  New (inserted):          3
  Updated:                 2
  Marked as deleted:       1
  Unchanged:               42
  Errors:                  0
============================================================
```

---

## Complete Workflow

### Monthly Credit Card Import

```bash
# 1. Import new credit card statement
python src/import_statement/pipeline.py \
  --statement data/raw/jan2026.csv \
  --start-date 2026-01-01 \
  --end-date 2026-01-31

# Result: Transactions added to Splitwise + Database

# 2. Manual review in Splitwise app/website
# - Adjust splits (50/50, custom amounts, etc.)
# - Delete unwanted/duplicate transactions
# - Fix categories or descriptions
# - Add missing transactions manually

# 3. Sync changes back to database
python src/db_sync/sync_from_splitwise.py --year 2026 --live

# Result: Database now reflects all Splitwise changes

# 4. (Phase 3) Export to Google Sheets
# python src/export/export_to_sheets.py --year 2026
```

### Import Pipeline Details

When you run `pipeline.py`:

1. **Parse CSV** - Extract transactions from statement
2. **Add to Splitwise** - Create expense via API
3. **Save to Database** - Store with `splitwise_id` link
4. **Error Handling** - DB save failures logged, don't block Splitwise

```python
# What happens in pipeline.py
sid = client.add_expense_from_txn(txn_dict, ...)  # Splitwise first

# Then save to database
db_txn = Transaction(
    date=date,
    merchant=merchant,
    amount=amount,
    splitwise_id=sid,  # Link to Splitwise
    source="amex",
    ...
)
db_txn_id = db.insert_transaction(db_txn)
```

---

## Import Pipeline Commands

```bash
# Basic import (dry run)
python src/import_statement/pipeline.py \
  --statement data/raw/statement.csv \
  --dry-run \
  --no-sheet

# Live import with date range
python src/import_statement/pipeline.py \
  --statement data/raw/jan2026.csv \
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

---

## Database API Reference

### Basic Operations

```python
from src.database import DatabaseManager, Transaction
from datetime import datetime

# Initialize
db = DatabaseManager()

# Create transaction
txn = Transaction(
    date='2026-01-12',
    merchant='Starbucks',
    amount=5.67,
    source='amex',
    imported_at=datetime.utcnow().isoformat()
)
txn_id = db.insert_transaction(txn)

# Batch insert
transactions = [txn1, txn2, txn3]
ids = db.insert_transactions_batch(transactions)

# Get by ID
txn = db.get_transaction_by_id(txn_id)

# Get by Splitwise ID
txn = db.get_transaction_by_splitwise_id(12345)
```

### Queries

```python
# Date range
transactions = db.get_transactions_by_date_range(
    '2026-01-01', 
    '2026-01-31'
)

# Unwritten (need sync to sheets)
unwritten = db.get_unwritten_transactions(year=2026)

# By source
amex_txns = db.get_transactions_by_source('amex')

# With Splitwise IDs
sw_txns = db.get_transactions_with_splitwise_ids(
    '2026-01-01',
    '2026-01-31'
)

# Find duplicates
dupes = db.find_potential_duplicates(
    date='2026-01-12',
    merchant='Starbucks',
    amount=5.67,
    tolerance_days=3,
    amount_tolerance=0.01
)
```

### Updates

```python
# Update fields
db.update_transaction(txn_id, {
    'category': 'Food and drink',
    'notes': 'Business lunch'
})

# Update from Splitwise data
db.update_transaction_from_splitwise(splitwise_id, expense_data)

# Update Splitwise ID
db.update_splitwise_id(txn_id, splitwise_id)

# Mark deleted
db.mark_deleted_by_splitwise_id(splitwise_id)

# Mark written to sheets
db.mark_written_to_sheet([txn_id1, txn_id2], year=2026)
```

### Statistics

```python
# Get comprehensive stats
stats = db.get_stats()
print(f"Total: {stats['total_transactions']}")
print(f"By source: {stats['by_source']}")
print(f"In Splitwise: {stats['in_splitwise']}")
print(f"Date range: {stats['date_range']}")

# Get import history
history = db.get_import_history(source_type='splitwise_sync')
```

---

## Troubleshooting

### ModuleNotFoundError

```bash
# Always set PYTHONPATH before running scripts
export PYTHONPATH=/home/balaji94/PycharmProjects/SplitwiseImporter
```

Or add to `~/.bashrc`:
```bash
export PYTHONPATH=/home/balaji94/PycharmProjects/SplitwiseImporter
```

### Virtual Environment Not Found

```bash
# Create venv
python -m venv .venv

# Activate
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### Splitwise API Connection Errors

```bash
# Verify credentials in config/.env
cat config/.env | grep SPLITWISE

# Test connection
python -c "
from src.common.splitwise_client import SplitwiseClient
client = SplitwiseClient()
print(f'Connected as user ID: {client.get_current_user_id()}')
"
```

### Duplicate Transactions

The sync script automatically handles duplicates by checking `splitwise_id`. If you suspect duplicates:

```python
from src.database import DatabaseManager
db = DatabaseManager()

# Find potential duplicates
dupes = db.find_potential_duplicates(
    date="2026-01-15",
    merchant="Amazon",
    amount=29.99
)
print(f"Found {len(dupes)} potential duplicates")
for d in dupes:
    print(f"  ID {d.id}: {d.date} | {d.merchant} | ${d.amount} | SW:{d.splitwise_id}")
```

### Database Save Failures

If `pipeline.py` logs "Failed to save transaction to database":

1. Expense **already created** in Splitwise (cannot undo)
2. Note the Splitwise ID from log
3. Manually sync to pull it into DB:

```bash
python src/db_sync/sync_from_splitwise.py --year 2026 --live
```

### Checking What Would Change

Always run dry-run first:

```bash
python src/db_sync/sync_from_splitwise.py --year 2026 --dry-run --verbose
```

Review output carefully before running with `--live`.

---

## Database Location

**Default**: `data/transactions.db`

**Custom location**:
```python
from src.database import DatabaseManager
db = DatabaseManager(db_path='/custom/path/transactions.db')
```

**Backup database**:
```bash
cp data/transactions.db data/transactions.db.backup.$(date +%Y%m%d)
```

---

## Quick Command Reference

### Initial Setup
```bash
# One-time: Import historical data
python src/db_sync/sync_from_splitwise.py --years 2024 2025 2026 --live
```

### Monthly Import
```bash
# Import statement
python src/import_statement/pipeline.py \
  --statement data/raw/feb2026.csv \
  --start-date 2026-02-01 \
  --end-date 2026-02-28

# Sync after manual edits
python src/db_sync/sync_from_splitwise.py --year 2026 --live
```

### Database Queries
```bash
# Check stats
python -c "from src.database import DatabaseManager; import json; print(json.dumps(DatabaseManager().get_stats(), indent=2))"

# View recent transactions
python -c "
from src.database import DatabaseManager
db = DatabaseManager()
txns = db.get_transactions_by_date_range('2026-01-01', '2026-01-31')
for t in txns[:10]:
    print(f'{t.date} | {t.merchant:30} | \${t.amount:7.2f} | SW:{t.splitwise_id}')
"
```

---

## Files & Structure

```
src/
├── database/
│   ├── __init__.py           # Module exports
│   ├── schema.py             # Table definitions
│   ├── models.py             # Transaction & ImportLog dataclasses
│   └── db_manager.py         # DatabaseManager class
├── db_sync/
│   ├── __init__.py
│   └── sync_from_splitwise.py  # Unified sync tool
└── import_statement/
    └── pipeline.py           # CSV import pipeline

data/
└── transactions.db           # SQLite database
```

---

## Next Steps (Phase 3)

1. **Export to Sheets** - Only write unwritten transactions
2. **Mark as Written** - Track `written_to_sheet` flag
3. **Append-Only** - Never overwrite sheet data
4. **Summary Tabs** - Monthly rollups, budget tracking

---

## Best Practices

1. **Always dry-run first** - Use `--dry-run` for sync, saves from mistakes
2. **Backup database** - Copy `transactions.db` before major operations
3. **Review Splitwise weekly** - Make edits in Splitwise, then sync to DB
4. **Sync after edits** - Run sync script after making changes in Splitwise
5. **Check stats regularly** - Use `db.get_stats()` to monitor data quality
6. **Set PYTHONPATH** - Always export before running scripts

---

## See Also

- [Project Structure](../README.md)
- [Import Pipeline](../src/import_statement/pipeline.py)
- [Sync Script](../src/db_sync/sync_from_splitwise.py)
- [Database Schema](../src/database/schema.py)
