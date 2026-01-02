# SplitwiseImporter

A Python project to import Splitwise expenses, process credit card statements, categorize expenses, and sync to Google Sheets for budget tracking.

## Setup
1. Create a virtual environment: `python -m venv venv`
2. Install dependencies: `pip install -r requirements.txt`
3. Add your API keys to `config/.env`
4. Set PYTHONPATH: `export PYTHONPATH=/home/balaji94/PycharmProjects/SplitwiseImporter`

## Quick Start

### Process a Credit Card Statement
```bash
# Parse and categorize transactions
python src/pipeline.py --statement data/raw/your_statement.csv

# Dry run to preview without saving
python src/pipeline.py --statement data/raw/your_statement.csv --dry-run
```

### Review & Improve Merchant Extraction

The pipeline automatically generates a review file for extracted merchant names. Review and correct them to improve future processing:

```bash
# Start interactive review (batch of 20)
python src/review_merchants.py --batch 20

# Check progress
python src/review_merchants.py --stats

# Apply your corrections to update the configuration
python src/apply_review_feedback.py

# Re-run pipeline to see improvements
python src/pipeline.py --statement data/raw/your_statement.csv
```

**See [Merchant Review Workflow](docs/merchant_review_workflow.md) for detailed instructions.**

### Export Splitwise Data
```bash
# Export all Splitwise expenses for a date range
python src/splitwise_export.py --start-date 2025-01-01 --end-date 2025-12-31

# Export and sync to Google Sheets
python src/splitwise_export.py --start-date 2025-01-01 --end-date 2025-12-31 --sheet-name "Splitwise 2025"
```

## Structure
- **src/**: Core modules (parsing, categorization, Splitwise API, Google Sheets sync)
- **config/**: Credentials and category mappings
- **data/**: Raw statements and processed outputs
- **docs/**: Documentation and guides
- **notebooks/**: Analysis notebooks
- **tests/**: Unit/integration tests

## Key Features

✅ **CSV Statement Parsing** - Automatically detect and parse credit card statements  
✅ **Smart Merchant Extraction** - Extract clean merchant names from messy descriptions  
✅ **Interactive Review** - Review and correct merchant names to improve accuracy  
✅ **Auto-categorization** - Map transactions to budget categories  
✅ **Splitwise Integration** - Export and sync with Splitwise expenses  
✅ **Google Sheets Sync** - Write results to your budget tracking sheet  
✅ **Duplicate Detection** - Avoid re-processing the same transactions

