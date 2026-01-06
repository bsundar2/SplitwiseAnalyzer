# SplitwiseImporter

A Python project to import Splitwise expenses, process credit card statements, categorize expenses, and sync to Google Sheets for budget tracking.

## Setup
1. Create a virtual environment: `python -m venv .venv`
2. Activate the environment: `source .venv/bin/activate`
3. Install dependencies: `pip install -r requirements.txt`
4. Add your API keys to `config/.env`
5. Set PYTHONPATH: `export PYTHONPATH=/home/balaji94/PycharmProjects/SplitwiseImporter`

## Quick Start

### Process a Credit Card Statement
```bash
# Parse and categorize transactions
python src/import_statement/pipeline.py --statement data/raw/your_statement.csv

# Dry run to preview without saving
python src/import_statement/pipeline.py --statement data/raw/your_statement.csv --dry-run

# Process specific batch (useful for large statements)
python src/import_statement/pipeline.py --statement data/raw/your_statement.csv --limit 50 --offset 0

# Append results to existing Google Sheet
python src/import_statement/pipeline.py --statement data/raw/your_statement.csv --append

# Filter by merchant (selective reprocessing)
python src/import_statement/pipeline.py --statement data/raw/your_statement.csv --merchant-filter "Headway" --offset 0
```

### Review & Improve Merchant Extraction

The pipeline automatically generates a review file for extracted merchant names. Review and correct them to improve future processing:

```bash
# Start interactive review (batch of 20)
python src/merchant_review/review_merchants.py --batch 20

# Check progress
python src/merchant_review/review_merchants.py --stats

# Apply your corrections to update the configuration
python src/merchant_review/apply_review_feedback.py

# Re-run pipeline to see improvements
python src/import_statement/pipeline.py --statement data/raw/your_statement.csv
```

### Export Splitwise Data
```bash
# Export all Splitwise expenses for a date range
python src/export/splitwise_export.py --start-date 2025-01-01 --end-date 2025-12-31

# Export and sync to Google Sheets (append mode)
python src/export/splitwise_export.py --start-date 2025-01-01 --end-date 2025-12-31 --sheet-name "Splitwise 2025"

# Overwrite sheet with fresh data (removes duplicates, filters deleted transactions)
python src/export/splitwise_export.py --start-date 2025-01-01 --end-date 2025-12-31 --overwrite

# Export Splitwise categories to a separate sheet
python src/export/splitwise_export.py --start-date 2025-01-01 --end-date 2025-12-31 --overwrite --export-categories
```

### Update Existing Splitwise Expenses

```bash
# Fix self-expenses with incorrect 50/50 splits (make them 100% owed)
python src/update/update_self_expenses.py --start-date 2025-01-01 --end-date 2025-12-31

# Dry run to preview changes
python src/update/update_self_expenses.py --start-date 2025-01-01 --end-date 2025-12-31 --dry-run

# Update a specific expense by ID
python src/update/update_self_expenses.py --expense-id 1234567890

# Limit number of updates (for testing)
python src/update/update_self_expenses.py --start-date 2025-01-01 --limit 10
```

### Bulk Category Updates

Update categories for existing Splitwise expenses in bulk by merchant name or current category:

```bash
# Update all SpotHero expenses to Transportation > Parking
python src/update/bulk_update_categories.py --merchant "SpotHero" --subcategory parking

# Update Amazon (excluding AWS) to Household supplies
python src/update/bulk_update_categories.py --merchant "Amazon" --exclude "AWS" --subcategory household_supplies

# Update Costco expenses currently in "Home - Other" to Household supplies
python src/update/bulk_update_categories.py --merchant "Costco" --current-category "Home - Other" --subcategory-id 14

# Dry run to preview changes
python src/update/bulk_update_categories.py --merchant "SpotHero" --subcategory parking --dry-run

# Skip confirmation prompt
python src/update/bulk_update_categories.py --merchant "Costco" --subcategory household_supplies --yes
```

**Common Subcategory Options:**
- `parking` (ID: 9) - Transportation > Parking
- `household_supplies` (ID: 14) - Home > Household supplies
- `home_other` (ID: 28) - Home > Other
- `medical` (ID: 38) - Life > Medical expenses
- `groceries` (ID: 1) - Food and drink > Groceries
- `dining_out` (ID: 2) - Food and drink > Dining out

See `src/constants/splitwise.py` (SUBCATEGORY_IDS) for the full list of available subcategories.

Or use `--subcategory-id` with any Splitwise subcategory ID.

## Project Structure

```
SplitwiseImporter/
├── src/
│   ├── import_statement/       # CSV statement parsing and import pipeline
│   │   ├── pipeline.py         # Main ETL pipeline orchestrator
│   │   ├── parse_statement.py  # CSV parsing and normalization
│   │   └── categorization.py   # Transaction categorization logic
│   ├── export/                 # Splitwise data export
│   │   └── splitwise_export.py # Fetch and export Splitwise expenses
│   ├── update/                 # Bulk update utilities
│   │   ├── update_self_expenses.py # Fix self-expense splits
│   │   └── bulk_update_categories.py # Bulk category updates
│   ├── merchant_review/        # Interactive merchant review workflow
│   │   ├── review_merchants.py # Interactive review tool
│   │   └── apply_review_feedback.py # Apply corrections
│   ├── common/                 # Shared utilities
│   │   ├── splitwise_client.py # Splitwise API wrapper
│   │   ├── sheets_sync.py      # Google Sheets integration
│   │   └── utils.py            # Common helper functions
│   └── constants/              # Configuration constants
├── config/                     # Credentials and mappings
│   ├── .env                    # API keys (not in git)
│   ├── merchant_category_lookup.json  # Merchant→category mappings
│   ├── amex_category_mapping.json     # Amex category mappings
│   └── gsheets_authentication.json    # Google Sheets credentials
├── data/
│   ├── raw/                    # Raw credit card statements
│   └── processed/              # Processed outputs and review files
├── docs/                       # Documentation
└── notebooks/                  # Jupyter analysis notebooks
```

## Key Features

✅ **CSV Statement Parsing** - Automatically detect and parse credit card statements  
✅ **Smart Merchant Extraction** - Extract clean merchant names from messy descriptions  
✅ **Interactive Merchant Review** - Review and correct merchant names to improve accuracy  
✅ **Auto-categorization** - Map transactions to Splitwise categories using merchant lookup  
✅ **Batch Processing** - Process large statements in chunks with `--limit` and `--offset`  
✅ **Merchant Filtering** - Selectively reprocess transactions by merchant name  
✅ **Splitwise Integration** - Add expenses to Splitwise with proper categorization  
✅ **Deleted Transaction Filtering** - Automatically filter out deleted expenses from exports  
✅ **Google Sheets Sync** - Write results to your budget tracking sheet (append or overwrite)  
✅ **Duplicate Detection** - Avoid re-processing using local cache and remote API checks  
✅ **Bulk Updates** - Update existing Splitwise expenses (fix splits, categories, etc.)  
✅ **Category Export** - Export all Splitwise categories and subcategories to sheets

## Common Workflows

### First-Time Statement Import
1. Place your CSV statement in `data/raw/`
2. Run dry-run to preview: `python src/import_statement/pipeline.py --statement data/raw/statement.csv --dry-run`
3. Review merchant extractions in `data/processed/merchant_names_for_review.csv`
4. Correct any issues: `python src/merchant_review/review_merchants.py`
5. Run actual import: `python src/import_statement/pipeline.py --statement data/raw/statement.csv`

### Large Statement Processing (Batch Mode)
```bash
# Process in batches of 50 transactions
python src/import_statement/pipeline.py --statement data/raw/big_statement.csv --limit 50 --offset 0
python src/import_statement/pipeline.py --statement data/raw/big_statement.csv --limit 50 --offset 50 --append
python src/import_statement/pipeline.py --statement data/raw/big_statement.csv --limit 50 --offset 100 --append
# ... continue until done
```

### Monthly Budget Sync
```bash
# Export current month's Splitwise expenses
python src/export/splitwise_export.py --start-date 2025-01-01 --end-date 2025-01-31 --sheet-name "Jan 2025"

# Full year export with categories
python src/export/splitwise_export.py --start-date 2025-01-01 --end-date 2025-12-31 --overwrite --export-categories
```

## Configuration Files

### merchant_category_lookup.json
Maps merchant names to Splitwise categories. Auto-updated through merchant review workflow.

```json
{
  "spothero": {
    "canonical_name": "SpotHero",
    "category": "Transportation",
    "subcategory": "Parking",
    "confidence": 0.95
  }
}
```

### Environment Variables (.env)
Required API credentials and default settings:

```env
# Splitwise API
SPLITWISE_CONSUMER_KEY=your_key_here
SPLITWISE_CONSUMER_SECRET=your_secret_here
SPLITWISE_API_KEY=your_api_key_here

# Google Sheets
SPREADSHEET_KEY=your_google_sheets_key

# Default date range and worksheet (change for new year)
START_DATE=2026-01-01
END_DATE=2026-12-31
EXPENSES_WORKSHEET_NAME=Expenses 2026
DRY_RUN_WORKSHEET_NAME=Splitwise Dry Runs
```

**Note:** Update `START_DATE`, `END_DATE`, and `EXPENSES_WORKSHEET_NAME` at the start of each year to automatically target the new year's data.

## Tips & Best Practices

- **Always set PYTHONPATH** before running commands: `export PYTHONPATH=/path/to/SplitwiseImporter`
- **Use dry-run first** to preview changes before committing to Splitwise
- **Review merchants regularly** to improve auto-categorization accuracy
- **Process large statements in batches** to handle API rate limits gracefully
- **Use --overwrite for exports** to get a clean dataset with deleted transactions filtered out
- **Check logs** in terminal output for detailed processing information

## Troubleshooting

**Import fails with "ModuleNotFoundError"**: Set PYTHONPATH to project root  
**Duplicate expenses created**: Check cache in `data/splitwise_expense_details_*.json`  
**Wrong categories**: Review and correct in `config/merchant_category_lookup.json`  
**Deleted expenses appearing**: Use `--overwrite` flag when exporting to filter them out  
**Date mismatch (one day off)**: Fixed in export - dates no longer use UTC conversion  
**Category updates not reflected**: Run export with `--overwrite` after bulk updates  
**Wrong year data**: Update `START_DATE`, `END_DATE`, and `EXPENSES_WORKSHEET_NAME` in `config/.env`

## Recent Updates (Jan 2026)

- ✅ Fixed date timezone issue causing one-day discrepancy between Splitwise UI and sheets
- ✅ Updated merchant categories: SpotHero → Transportation/Parking, Amazon → Home/Household supplies, Costco → Home/Household supplies
- ✅ Switched to 2026 tracking (config/.env updated with new dates and "Expenses 2026" worksheet)
- ✅ Added bulk category update workflow documentation

