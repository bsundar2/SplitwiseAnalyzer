# Monthly Statement Processing Workflow

This guide covers the automated monthly workflow for processing credit card statements and syncing to Google Sheets.

## Overview

The monthly workflow consists of four steps:
1. **Import** - Parse CSV statement and add transactions to Splitwise
2. **Sync** - Pull latest data from Splitwise API to database (updates splits, payments)
3. **Export** - Write filtered transactions from database to Google Sheets
4. **Summaries** - Generate monthly budget analysis and spending patterns (Phase 4)

## Quick Reference

### Recommended: Automated Pipeline

Run all three steps with a single command:

```bash
export PYTHONPATH=/home/balaji94/PycharmProjects/SplitwiseImporter

# Full workflow with new statement
python src/export/monthly_export_pipeline.py \
  --statement data/raw/jan2026.csv \
  --year 2026 \
  --start-date 2026-01-01 \
  --end-date 2026-01-31

# Sync and export only (no new statement)
python src/export/monthly_export_pipeline.py --year 2026 --sync-only

# Append-only mode (only export unwritten transactions)
python src/export/monthly_export_pipeline.py --year 2026 --sync-only --append-only

# Dry run to preview
python src/export/monthly_export_pipeline.py \
  --statement data/raw/jan2026.csv \
  --year 2026 \
  --dry-run
```

### Manual Steps (for troubleshooting)

If you need to run steps individually:

```bash
# Step 1: Import statement
python src/import_statement/pipeline.py \
  --statement data/raw/jan2026.csv \
  --start-date 2026-01-01 \
  --end-date 2026-01-31

# Step 2: Sync database
python src/db_sync/sync_from_splitwise.py --year 2026 --live

# Step 3: Export to sheets
python src/export/splitwise_export.py \
  --source database \
  --year 2026 \
  --worksheet "Expenses 2026" \
  --overwrite
```

## Workflow Details

### Step 1: Import Statement

**What it does:**
- Parses CSV credit card statement
- Categorizes transactions using merchant lookup (216+ merchants)
- Detects duplicates using cc_reference_id
- Creates expenses in Splitwise API
- Saves to local database with splitwise_id

**Key flags:**
- `--statement` - Path to CSV file
- `--start-date` / `--end-date` - Filter date range
- `--dry-run` - Preview without creating expenses

**What gets saved:**
- Transaction metadata (date, amount, merchant, category)
- cc_reference_id from statement
- Splitwise ID after creation
- Default split: 50/50 with partner (can be edited in Splitwise)

### Step 2: Sync Database

**What it does:**
- Fetches latest expense data from Splitwise API
- Compares with local database
- Updates changed transactions (splits, amounts, categories)
- Marks deleted expenses
- Populates payment information (Paid/Owe/With)

**Why this matters:**
- Splitwise is the source of truth for manual edits
- You can fix splits, delete duplicates, change categories in Splitwise
- Sync brings those changes back to the database
- Payment details (who paid, who owes) are only available via API

**Key flags:**
- `--year` - Year to sync
- `--live` - Apply changes (without this, dry run mode)
- `--verbose` - Show detailed comparison output

**What gets updated:**
- Transaction amounts, descriptions, categories
- Split information (is_shared flag, participant names)
- Payment details in notes field
- Deleted status for removed expenses

### Step 3: Export to Sheets

**What it does:**
- Reads transactions from database
- Filters out Payment transactions
- Formats as 12-column export
- Writes to Google Sheets
- Marks transactions as written_to_sheet

**Key flags:**
- `--source database` - Use database as source (recommended)
- `--year` - Filter by year
- `--worksheet` - Target sheet name
- `--overwrite` - Replace all rows (vs append)
- `--dry-run` - Preview without writing

**What gets exported:**
12 columns in this order:
1. Date
2. Amount
3. Category
4. Description
5. Details (cc_reference_id only)
6. Split Type (split/self)
7. Participant Names
8. My Paid
9. My Owed
10. My Net
11. Splitwise ID
12. Transaction Fingerprint

**What gets filtered:**
- Payment transactions (description="Payment" AND category="General")
- Deleted transactions (marked in database)
- Transactions with no user participation

## Common Scenarios

### Processing a New Monthly Statement

```bash
# Download statement from credit card website
# Save as data/raw/feb2026.csv

# Run full pipeline
python src/export/monthly_export_pipeline.py \
  --statement data/raw/feb2026.csv \
  --year 2026 \
  --start-date 2026-02-01 \
  --end-date 2026-02-28
```

### After Making Manual Edits in Splitwise

If you deleted duplicates, fixed splits, or changed categories in Splitwise:

```bash
# Sync and export (no new statement)
python src/export/monthly_export_pipeline.py --year 2026 --sync-only
```

### Incremental Updates (Append-Only Mode)

For ongoing monthly tracking without re-exporting everything:

```bash
# Only export transactions not yet written to sheets
python src/export/monthly_export_pipeline.py --year 2026 --sync-only --append-only
```

**How it works:**
- Tracks `written_to_sheet` flag in database
- Only exports transactions where `written_to_sheet = False`
- Marks transactions as written after successful export
- Prevents duplicate exports and unnecessary overwrites
- Ideal for mid-month updates or historical month corrections

**When to use:**
- Adding new transactions to an existing month
- After manual Splitwise edits that added/updated transactions
- Incremental updates without full refresh

**When NOT to use:**
- Initial month setup (use overwrite mode)
- Major data cleanup or reformatting
- When you need to re-export everything

### Refreshing Google Sheets

To re-export all data with latest formatting:

```bash
python src/export/splitwise_export.py \
  --source database \
  --year 2026 \
  --worksheet "Expenses 2026" \
  --overwrite
```

## Troubleshooting

### "Duplicate transaction" errors during import

This is normal! The pipeline checks for duplicates and skips them. If you see this message, it means the transaction already exists in Splitwise.

### Missing payment information in export

Run the sync script to pull payment details from Splitwise:

```bash
python src/db_sync/sync_from_splitwise.py --year 2026 --live
```

### Transactions show $0 amounts or missing splits

Database is out of sync with Splitwise. Run sync script:

```bash
python src/db_sync/sync_from_splitwise.py --year 2026 --live
```

### Export shows wrong transaction count

Check if Payment transactions are being counted:

```bash
# Preview with dry run
python src/export/splitwise_export.py \
  --source database \
  --year 2026 \
  --dry-run
```

Payment transactions are filtered from sheets but remain in database.

## Best Practices

1. **Always use dry run first** - Preview changes before applying
2. **Sync after import** - Get payment details from Splitwise
3. **Edit in Splitwise, sync to DB** - Never edit database directly
4. **Use automated pipeline** - Reduces errors from manual steps
5. **Check export preview** - Verify transaction count before overwriting

## Architecture

```
CSV Statement → Import → Splitwise API → Save to DB
                              ↓
                    [Manual edits in Splitwise]
                              ↓
Database ← Sync ← Splitwise API (updates, deletes)
   ↓
Export (filtered) → Google Sheets
```

**Why this flow:**
- Splitwise = Source of truth for manual edits
- Database = Fast queries, offline access
- Sheets = Filtered view for budget tracking

## Next Steps

Phase 4 will add:
- Budget vs actual tracking
- Monthly summary tabs
- Category rollups
- Append-only sheet updates (no overwrite)
