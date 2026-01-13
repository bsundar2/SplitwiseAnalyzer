# Database Migration Guide

This guide walks through migrating your Splitwise data into the local SQLite database.

## Overview

The local SQLite database (`data/transactions.db`) serves as the **canonical source of truth** for all transaction data. Google Sheets becomes a "view cache" - a human-readable mirror of your data.

## What's New

- **SQLite database** (`data/transactions.db`) - Stores all transactions
- **Transaction model** - Normalized schema with deduplication, source tracking, and sync status
- **Database manager** - Python API for CRUD operations
- **Migration tool** - Import historical data directly from Splitwise API

## Database Schema

### `transactions` table
- **Core fields**: date, merchant, description, amount (signed)
- **Categorization**: category, subcategory, category_id, subcategory_id
- **Source tracking**: source (amex/visa/splitwise), source_file
- **Characteristics**: is_refund, is_shared, currency
- **Splitwise integration**: splitwise_id, splitwise_deleted_at
- **Sync tracking**: written_to_sheet, sheet_year, sheet_row_id
- **Metadata**: imported_at, updated_at, notes
- **Deduplication**: raw_description, statement_date, raw_amount

### Other tables
- `duplicate_checks` - Track and resolve potential duplicates
- `import_log` - Audit trail for all imports

## Setup Steps

### Import from Splitwise API

Activate your virtual environment first:
```bash
source .venv/bin/activate
export PYTHONPATH=/home/balaji94/PycharmProjects/SplitwiseImporter
```

**Dry run (preview):**
```bash
python src/db_migration/migrate_from_splitwise_api.py --year 2025 --dry-run
```

**Import single year:**
```bash
python src/db_migration/migrate_from_splitwise_api.py --year 2025
```

**Import multiple years:**
```bash
python src/db_migration/migrate_from_splitwise_api.py --years 2023 2024 2025 2026
```

**Import year range:**
```bash
python src/db_migration/migrate_from_splitwise_api.py --year-range 2020 2026
```

The script will:
- Fetch expenses directly from Splitwise API
- Extract your share of each expense
- Map categories and split information
- Skip duplicates (checks by `splitwise_id`)
- Mark transactions as from Splitwise source

### Verify Database

Check what was imported:

```bash
python -c "
from src.database import DatabaseManager
db = DatabaseManager()
stats = db.get_stats()
print(f'Total transactions: {stats[\"total_transactions\"]}')
print(f'By source: {stats[\"by_source\"]}')
print(f'Date range: {stats[\"date_range\"][\"min\"]} to {stats[\"date_range\"][\"max\"]}')
"
```

## Migration Command Reference

**Note:** Always activate venv and set PYTHONPATH first:
```bash
source .venv/bin/activate
export PYTHONPATH=/home/balaji94/PycharmProjects/SplitwiseImporter
```

### Splitwise API Migration

```bash
# Single year with dry run
python src/db_migration/migrate_from_splitwise_api.py --year 2025 --dry-run

# Single year actual import
python src/db_migration/migrate_from_splitwise_api.py --year 2025

# Multiple specific years
python src/db_migration/migrate_from_splitwise_api.py --years 2023 2024 2025 2026

# Year range (inclusive)
python src/db_migration/migrate_from_splitwise_api.py --year-range 2020 2026

# Custom database location
python src/db_migration/migrate_from_splitwise_api.py --year 2025 --db-path /path/to/db.sqlite
```

## Database Location

By default: `data/transactions.db`

To use a different location, pass `--db-path` to migration scripts or set it in your Python code:

```python
from src.database import DatabaseManager
db = DatabaseManager(db_path='/custom/path/transactions.db')
```

## Troubleshooting

**"ModuleNotFoundError: No module named 'src'"**
- Make sure PYTHONPATH is set: `export PYTHONPATH=/home/balaji94/PycharmProjects/SplitwiseImporter`

**"Virtual environment not found"**
- Create it: `python -m venv .venv`
- Install dependencies: `source .venv/bin/activate && pip install -r requirements.txt`

**Duplicates being created**
- API migration checks `splitwise_id` automatically
- Run dry-run first to see what will be imported

**API connection errors**
- Verify credentials in `config/.env`
- Check that `SPLITWISE_API_KEY` is set correctly
- Test connection: `python -c "from src.common.splitwise_client import SplitwiseClient; print(SplitwiseClient().get_current_user_id())"`

## Next Steps

Once migration is complete, you can:

1. **Refactor import pipeline** - Write to DB first, then Splitwise
2. **Update export script** - Read from DB, only write new rows to Sheets
3. **Track sync status** - Mark transactions as `written_to_sheet=True`
4. **Modify existing scripts** - Use DatabaseManager instead of JSON cache

## Database API Examples

```python
from src.database import DatabaseManager, Transaction
from datetime import datetime

# Initialize
db = DatabaseManager()

# Create a transaction
txn = Transaction(
    date='2026-01-12',
    merchant='Starbucks',
    amount=5.67,
    source='amex',
    imported_at=datetime.utcnow().isoformat()
)
txn_id = db.insert_transaction(txn)

# Find by date range
transactions = db.get_transactions_by_date_range('2026-01-01', '2026-01-31')

# Find unwritten (needs sync to sheets)
unwritten = db.get_unwritten_transactions(year=2026)

# Check for duplicates
dupes = db.find_potential_duplicates(
    date='2026-01-12',
    merchant='Starbucks',
    amount=5.67
)

# Update transaction
db.update_transaction(txn_id, {'category': 'Food and drink'})

# Mark as written to sheets
db.mark_written_to_sheet([txn_id], year=2026)

# Get stats
stats = db.get_stats()
```

## Files Created

```
src/
├── database/
│   ├── __init__.py           # Module exports
│   ├── schema.py             # Table definitions
│   ├── models.py             # Transaction & ImportLog dataclasses
│   └── db_manager.py         # DatabaseManager class
└── db_migration/
    ├── __init__.py
    └── migrate_from_splitwise_api.py  # Import from Splitwise API

data/
└── transactions.db           # SQLite database (created on first run)
```
