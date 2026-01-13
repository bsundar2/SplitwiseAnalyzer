# Phase 4: Budget Tracking & Analysis

**Status**: Complete (Jan 13, 2026)

## Overview

Phase 4 adds automated budget tracking and analysis capabilities to the expense processing pipeline. Monthly summaries are now generated automatically and stored in both the database and Google Sheets, with intelligent change detection to avoid unnecessary updates.

## Key Features

### 1. Database-Backed Monthly Summaries

**New Table**: `monthly_summaries`

Stores computed monthly aggregates for fast comparison:

```sql
CREATE TABLE monthly_summaries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    year_month TEXT NOT NULL UNIQUE,       -- YYYY-MM format
    total_spent_net REAL NOT NULL,
    avg_transaction REAL NOT NULL,
    transaction_count INTEGER NOT NULL,
    total_paid REAL NOT NULL,
    total_owed REAL NOT NULL,
    cumulative_spending REAL NOT NULL,
    mom_change REAL NOT NULL,
    written_to_sheet BOOLEAN DEFAULT 0,
    calculated_at TEXT NOT NULL,
    updated_at TEXT
);
```

**Benefits:**
- Fast comparison without reading from Google Sheets
- Local cache of calculated values
- Audit trail of when summaries were computed
- Single source of truth for summary data

### 2. Idempotent Updates

**Smart Change Detection:**
- Compares new calculations against database values
- Only updates sheets when data actually changes
- Uses 0.01 tolerance for floating-point comparisons
- Tracks which months need updating vs appending

**Workflow:**
1. Calculate monthly summary from transactions
2. Check if month exists in database
3. Compare all values with 0.01 tolerance
4. If changed: update database → update/append sheet
5. If unchanged: skip (truly idempotent)

### 3. Integrated Pipeline

**4-Step Automated Pipeline:**
```bash
python src/export/monthly_export_pipeline.py --year 2026 --sync-only --append-only
```

Steps:
1. **Sync** - Pull updates from Splitwise to database
2. **Export** - Write new transactions to sheets (append-only)
3. **Summaries** - Calculate and update monthly summaries
4. **Success** - All steps complete with detailed logging

### 4. Budget Analysis

**5 Analysis Types:**

1. **Monthly Summary** (implemented)
   - Total Spent (Net), Avg Transaction, Transaction Count
   - Total Paid, Total Owed
   - Cumulative Spending, Month-over-Month Change
   - Written to "Monthly Summary" sheet

2. **Category Breakdown** (calculated, not written)
   - Spending by category with percentages
   - Transaction counts per category
   - Sorted by total spent

3. **Budget vs Actual** (calculated, not written)
   - Compares against `config/budget_2026.json`
   - Shows variance $ and variance %
   - Status: Over/Under budget

4. **Monthly Trends** (calculated, not written)
   - 3-month rolling averages
   - Year-to-date trends

5. **Category by Month** (calculated, not written)
   - Pivot table: categories × months
   - Total column for category summaries

### 5. Smart Category Mapping

**Transaction → Budget Categories:**

The system maps 20+ transaction categories to Splitwise budget format:

```python
category_mapping = {
    "Rent": "Home - Rent",
    "Dining out": "Food and drink - Dining out",
    "Groceries": "Food and drink - Groceries",
    "Gas/fuel": "Transportation - Gas/fuel",
    "Taxi": "Transportation - Taxi",
    "Plane": "Transportation - Plane",
    "Parking": "Transportation - Parking",
    "Electronics": "Home - Electronics",
    "Household supplies": "Home - Household supplies",
    "Medical expenses": "Life - Medical expenses",
    # ... 10+ more mappings
}
```

## Architecture Changes

### Database Layer

**New Methods in DatabaseManager:**

```python
# Save or update monthly summary
db.save_monthly_summary(
    year_month="2026-01",
    total_spent_net=4272.98,
    avg_transaction=101.74,
    transaction_count=42,
    total_paid=11813.27,
    total_owed=7540.29,
    cumulative_spending=4272.98,
    mom_change=0.0,
    written_to_sheet=False
)

# Get summary for specific month
summary = db.get_monthly_summary("2026-01")

# Get all summaries for a year
summaries = db.get_all_monthly_summaries(year=2026)

# Mark as written to sheets
db.mark_monthly_summary_written("2026-01")
```

### Constants Organization

**Moved to `src/constants/gsheets.py`:**
```python
# Worksheet names for summary sheets
WORKSHEET_MONTHLY_SUMMARY = "Monthly Summary"
WORKSHEET_CATEGORY_BREAKDOWN = "Category Breakdown"
WORKSHEET_BUDGET_VS_ACTUAL = "Budget vs Actual"
WORKSHEET_MONTHLY_TRENDS = "Monthly Trends"
```

### Exception Handling

**Fail-Fast Approach:**
- Removed all try-catch blocks from pipeline scripts
- Exceptions now bubble up immediately
- Easier debugging with full stack traces
- Follows `coding_style.md` Rule 3: fail fast

**Files Updated:**
- `src/export/monthly_export_pipeline.py`
- `src/export/generate_summaries.py`
- `src/export/splitwise_export.py`

## Usage

### Generate Budget Summaries

```bash
# Full pipeline (recommended)
python src/export/monthly_export_pipeline.py --year 2026 --sync-only --append-only

# Summaries only (standalone)
python src/export/generate_summaries.py --year 2026

# Dry run to preview
python src/export/generate_summaries.py --year 2026 --dry-run

# Custom budget file
python src/export/generate_summaries.py --year 2026 --budget config/budget_2026.json
```

### Output Example

```
Writing summaries to Google Sheets...

✓ Monthly Summary: 1 updated, 2 appended, 9 unchanged
   https://docs.google.com/spreadsheets/d/...
```

## Configuration

### Budget File

`config/budget_2026.json`:

```json
{
  "Home - Rent": 32400.0,
  "Life - Taxes": 12000.0,
  "Food and drink - Dining out": 10500.0,
  "Transportation - Car": 7000.0,
  "Food and drink - Groceries": 5500.0,
  "Transportation - Plane": 5000.0,
  "Transportation - Taxi": 3360.0,
  ...
}
```

**Total Budget**: $113,517 across 32 categories

## Performance

**Database vs Sheets Comparison:**

| Approach | Read Time | Write Time | Network Calls |
|----------|-----------|------------|---------------|
| Read from Sheets | ~2-3s | ~1-2s per row | 2-3 per month |
| Read from Database | ~0.01s | ~1-2s per row | 1-2 per month |

**Savings**: 2-3 seconds per pipeline run + more reliable offline operation

## Testing

**Dry Run Mode:**
```bash
python src/export/generate_summaries.py --year 2026 --dry-run
```

Shows:
- All calculated summaries
- Comparison results
- What would be written
- No actual changes made

**Append-Only Verification:**
```bash
# First run - writes all months
python src/export/monthly_export_pipeline.py --year 2026 --sync-only --append-only

# Second run - should show "No changes needed"
python src/export/monthly_export_pipeline.py --year 2026 --sync-only --append-only
```

## Future Enhancements

**Phase 5 Candidates:**

1. **Additional Summary Sheets**
   - Enable Category Breakdown sheet
   - Enable Budget vs Actual sheet
   - Enable Monthly Trends sheet
   - Add command-line flags to control which sheets

2. **Alerting & Notifications**
   - Email/Slack on over-budget categories
   - Monthly spending reports
   - Anomaly detection (unusual spending)

3. **Advanced Analytics**
   - Spending predictions
   - Category trend analysis
   - Year-over-year comparisons
   - Budget recommendations

4. **Automation**
   - Scheduled pipeline runs (cron/GitHub Actions)
   - Automatic statement downloads
   - Monthly summary emails

## Troubleshooting

**Table doesn't exist error:**
```bash
# Initialize the database schema
python3 -c "from src.database import DatabaseManager; DatabaseManager()"
```

**Or manually create table:**
```bash
python3 << EOF
import sqlite3
from src.database.schema import MONTHLY_SUMMARIES_TABLE
conn = sqlite3.connect("data/transactions.db")
conn.executescript(MONTHLY_SUMMARIES_TABLE)
conn.commit()
conn.close()
EOF
```

**Summaries not updating:**
- Check if data actually changed (0.01 tolerance)
- Verify transactions exist in database
- Run with `--dry-run` to see calculated values
- Check logs for comparison results

**Wrong budget values:**
- Update `config/budget_2026.json`
- Ensure category names match Splitwise format
- Check category mapping in `generate_summaries.py`

## Code Quality

**Black Formatting:**
```bash
python3 -m black src/
```

All code follows:
- Black code style
- `coding_style.md` guidelines
- No broad exception catching
- Fail-fast error handling
