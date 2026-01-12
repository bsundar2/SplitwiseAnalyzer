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
# Unified review workflow (recommended - runs all steps)
python src/merchant_review/run_review_workflow.py --processed-csv data/processed/your_statement.csv.processed.csv --batch 20

# Or run steps individually:
# 1. Generate review file
python src/merchant_review/generate_review_file.py --processed-csv data/processed/your_statement.csv.processed.csv --output data/processed/merchant_names_for_review.csv

# 2. Start interactive review (batch of 20)
python src/merchant_review/review_merchants.py --batch 20

# 3. Check progress
python src/merchant_review/review_merchants.py --stats

# 4. Apply your corrections to update the configuration
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
│   │   ├── run_review_workflow.py   # Unified workflow orchestrator (NEW)
│   │   ├── generate_review_file.py  # Generate review CSV from processed data
│   │   ├── review_merchants.py      # Interactive review tool
│   │   └── apply_review_feedback.py # Apply corrections to config
│   ├── common/                 # Shared utilities
│   │   ├── splitwise_client.py # Splitwise API wrapper
│   │   ├── sheets_sync.py      # Google Sheets integration
│   │   └── utils.py            # Common helper functions (simplified merchant extraction)
│   └── constants/              # Configuration constants
├── config/                     # Credentials and mappings
│   ├── .env                    # API keys (not in git)
│   ├── merchant_category_lookup.json  # 219+ merchant→category mappings
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
✅ **Smart Merchant Extraction** - Extract clean merchant names from Description field with simple, maintainable logic  
✅ **Unified Review Workflow** - Single command to generate, review, and apply merchant corrections  
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

### Monthly Expense Processing Pipeline

**IMPORTANT:** Follow this order to ensure proper data flow and chronological sorting:

1. **Import credit card statements to Splitwise**
   ```bash
   # Parse and add new transactions to Splitwise
   python src/import_statement/pipeline.py --statement data/raw/amex_jan2026.csv
   ```

2. **Export Splitwise to Google Sheets** (use overwrite mode)
   ```bash
   # Export with overwrite to maintain chronological sorting
   python src/export/splitwise_export.py --start-date 2026-01-01 --end-date 2026-12-31 --overwrite
   ```

**Why this order matters:**
- Credit card statements may contain retroactive/backdated transactions (e.g., processing delays)
- Splitwise must be updated first with all transactions for the period
- Overwrite mode re-sorts all expenses chronologically, placing backdated entries in correct position
- Append mode would place retroactive expenses at the bottom, breaking chronological order

**Note:** Always use `--overwrite` when exporting after importing statements to maintain proper sorting.

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
DRY_RUN_WORKSHEET_NAME=Amex Imports
```

**Note:** Update `START_DATE`, `END_DATE`, and `EXPENSES_WORKSHEET_NAME` at the start of each year to automatically target the new year's data.

## Tips & Best Practices

- **Always set PYTHONPATH** before running commands: `export PYTHONPATH=/path/to/SplitwiseImporter`
- **Use dry-run first** to preview changes before committing to Splitwise
- **Review merchants regularly** to improve auto-categorization accuracy
- **Process large statements in batches** to handle API rate limits gracefully
- **Use --overwrite for exports** to get a clean dataset with deleted transactions filtered out
- **Check logs** in terminal output for detailed processing information
- **Follow the processing pipeline order**: Import statements to Splitwise first, then export to sheets with `--overwrite`
- **Update config/.env dates** at the start of each year (START_DATE, END_DATE, EXPENSES_WORKSHEET_NAME)

## Automation Considerations

The expense processing workflow can be automated with these steps:

1. **Statement Download**: Automate CSV download from credit card provider (or manual upload to `data/raw/`)
2. **Import to Splitwise**: Run `pipeline.py` with new statement
3. **Export to Sheets**: Run `splitwise_export.py --overwrite` after import completes
4. **Verification**: Check logs for import/export counts and any errors

**Recommended schedule:**
- Run pipeline monthly after credit card statement is available
- Use `--overwrite` mode to handle any retroactive transactions
- Monitor merchant review file for new merchants needing categorization

**Future enhancements:**
- Cron job or GitHub Actions for scheduled execution
- Email/Slack notifications on completion or errors
- Automatic merchant review aggregation and reporting

## Troubleshooting

**Import fails with "ModuleNotFoundError"**: Set PYTHONPATH to project root  
**Duplicate expenses created**: Check cache in `data/splitwise_expense_details_*.json`  
**Wrong categories**: Review and correct in `config/merchant_category_lookup.json`  
**Deleted expenses appearing**: Use `--overwrite` flag when exporting to filter them out  
**Date mismatch (one day off)**: Fixed in export - dates no longer use UTC conversion  
**Category updates not reflected**: Run export with `--overwrite` after bulk updates  
**Wrong year data**: Update `START_DATE`, `END_DATE`, and `EXPENSES_WORKSHEET_NAME` in `config/.env`

## Recent Updates (Jan 2026)

### Merchant Extraction Overhaul
- ✅ **Simplified merchant name extraction** - Rewrote `clean_merchant_name()` from 450+ lines to ~60 lines
- ✅ **Description field only** - Now uses simple Description column parsing instead of complex Extended Details multi-line extraction
- ✅ **Canonical name support** - Uses `canonical_name` from merchant lookup for consistent display names (e.g., "Kristyne" → "American Airlines")
- ✅ **Removed legacy code** - Cleaned up ~450 lines of unmaintainable extraction logic
- ✅ **Unified review workflow** - Created `run_review_workflow.py` to chain generate → review → apply steps automatically
- ✅ **Required arguments** - Made `generate_review_file.py` require explicit arguments (no defaults)

### Category Updates & Data Processing
- ✅ Fixed date timezone issue causing one-day discrepancy between Splitwise UI and sheets
- ✅ Updated merchant categories: SpotHero → Transportation/Parking, Amazon → Home/Household supplies, Costco → Home/Household supplies
- ✅ Switched to 2026 tracking (config/.env updated with new dates and "Expenses 2026" worksheet)
- ✅ Successfully imported January 2026 transactions (12 transactions processed)
- ✅ Added bulk category update workflow documentation

### Technical Improvements
- ✅ Fixed column mapping in `parse_statement.py` to use Description field correctly
- ✅ Improved merchant lookup with 219+ merchant entries
- ✅ Better error handling and validation throughout workflow

