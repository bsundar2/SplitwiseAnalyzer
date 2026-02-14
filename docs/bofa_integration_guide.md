# Bank of America (BoFA) Statement Integration Guide

## Overview

The SplitwiseImporter now supports Bank of America credit card and checking account statements in addition to American Express (Amex) statements. The system auto-detects the bank format based on CSV column names.

## Supported Banks

### American Express (Amex)
- **Required columns**: Posted Date, Description, Amount
- **Optional columns**: Extended Details, Category
- **Auto-detection**: YES
- **Category mapping**: amex_category_mapping.json

### Bank of America (BoFA)
- **Required columns**: Posted Date, Reference Number, Payee, Amount  
- **Optional columns**: Address
- **Auto-detection**: YES
- **Category mapping**: bofa_category_mapping.json

## Quick Start

### Automatic Bank Detection (Recommended)

The system auto-detects the bank format from your CSV headers:

```bash
python src/import_statement/pipeline.py \
  --statement data/raw/bofa_statement.csv \
  --start-date 2026-01-01 \
  --end-date 2026-01-31
```

### Explicit Bank Specification

To force a specific bank format:

```bash
# BoFA statement
python src/import_statement/pipeline.py \
  --statement data/raw/bofa_statement.csv \
  --bank bofa \
  --start-date 2026-01-01 \
  --end-date 2026-01-31

# Amex statement (explicit, though not needed with auto-detect)
python src/import_statement/pipeline.py \
  --statement data/raw/amex_statement.csv \
  --bank amex \
  --start-date 2025-01-01 \
  --end-date 2025-12-31
```

## CSV Format Examples

### Bank of America Statement Format

```
Posted Date,Reference Number,Payee,Address,Amount
02/07/2026,24692166037100644977891,"GEICO *AUTO 800-841-3000 DC","800-841-3000  DC ",-920.03
02/03/2026,24011106033900017404645,"COBS SPAINNY 212-7146655 NY","212-7146655   NY ",-210.00
01/15/2026,24045596013005269016943,"IMMIGRATION VISA TANZA DAR ES SALAAM","",-50.75
```

**Key differences from Amex**:
- Uses "Payee" instead of "Description"
- Uses "Reference Number" instead of "Extended Details"
- Includes optional "Address" field
- No built-in "Category" column (uses merchant-based categorization)

### American Express Statement Format

```
Posted Date,Description,Extended Details,Category,Amount
01/15/2026,GEICO AUTO PAY,12345678,"Travel-Lodging",-200.00
01/12/2026,AMAZON.COM,87654321,"Merchandise & Supplies-General Retail",-50.00
```

## Category Mapping

### BoFA Merchant-to-Category Mapping

The `config/bofa_category_mapping.json` file contains merchant keyword mappings. Examples:

```json
{
  "GEICO": "Life > Insurance",
  "COBS SPAIN": "Entertainment > Other",
  "GROCERIES": "Food and drink > Groceries",
  "GAS STATION": "Transportation > Gas/fuel",
  "RESTAURANT": "Food and drink > Dining out",
  ...
}
```

**How it works**:
1. Transaction merchant name is cleaned (phone numbers, addresses removed)
2. Cleaned merchant is matched against BoFA mapping (substring, case-insensitive)
3. If match found, uses BoFA-specific category
4. Falls back to merchant lookup table if no BoFA mapping
5. Uses pattern matching if no explicit merchant mapping

### Adding New BoFA Merchant Mappings

To add a new merchant to the BoFA mapping:

1. Open `config/bofa_category_mapping.json`
2. Add the merchant keyword and its category:

```json
{
  ...
  "YOUR_MERCHANT_NAME": "Category > Subcategory",
  ...
}
```

3. Use keywords that will match merchant descriptions in BoFA statements
4. Categories must match Splitwise categories (e.g., "Life > Insurance")

**Example additions**:

```json
{
  "CHASE BANK": "Uncategorized > General",
  "PAYPAL": "Uncategorized > General",
  "WALMART": "Home > Household supplies",
  "TARGET": "Home > Household supplies",
  "WHOLE FOODS": "Food and drink > Groceries",
  "BEST BUY": "Home > Electronics",
  "UBER": "Transportation > Taxi",
  "HOTEL": "Transportation > Hotel"
}
```

## Workflow: Processing BoFA Statements

### Step 1: Export BoFA Statement

1. Log into Bank of America online banking
2. Go to your Credit Card or Checking Account
3. Select date range and export as CSV
4. Save to `data/raw/` directory (e.g., `data/raw/bofa_february.csv`)

### Step 2: Preview (Dry Run)

```bash
python src/import_statement/pipeline.py \
  --statement data/raw/bofa_february.csv \
  --dry-run \
  --start-date 2026-02-01 \
  --end-date 2026-02-28
```

This shows:
- Number of transactions parsed
- Detected bank format
- Column mapping
- Categorization results (without creating expenses in Splitwise)

### Step 3: Import to Splitwise

```bash
python src/import_statement/pipeline.py \
  --statement data/raw/bofa_february.csv \
  --start-date 2026-02-01 \
  --end-date 2026-02-28
```

This:
- Parses the BoFA statement
- Detects bank format automatically
- Categorizes transactions using BoFA merchant mappings
- Creates Splitwise expenses
- Syncs to Google Sheets
- Exports transaction summaries

### Step 4: Review & Sync

If you need to sync any manual Splitwise edits back to the database:

```bash
python src/db_sync/sync_from_splitwise.py --year 2026 --live
```

## Troubleshooting

### Issue: Statement not detected as BoFA

**Solution**: Ensure CSV has exactly these column names:
- `Posted Date`
- `Reference Number`
- `Payee`
- `Amount`

Check your CSV file first row to verify column names match exactly.

### Issue: Transactions getting wrong categories

**Solution**: Add or update the merchant mapping in `config/bofa_category_mapping.json`:

```bash
# 1. Check which merchants are being categorized incorrectly
python src/import_statement/pipeline.py --statement data/raw/bofa.csv --dry-run

# 2. Find the merchant name in output
# 3. Edit config/bofa_category_mapping.json
# 4. Add mapping for that merchant
# 5. Re-run import
```

### Issue: Duplicate transactions detected

**Solution**: BoFA uses transaction reference numbers as unique IDs. Duplicates are detected by:
- `Reference Number` (primary key)
- Transaction amount + date (secondary check)

If you see duplicate errors, verify the reference numbers are unique in your CSV.

## Advanced: Custom Column Mapping

If your BoFA export has different column names, edit `config/bank_config.json`:

```json
{
  "banks": {
    "bofa": {
      "date_column": "Transaction Date",      // Change from "Posted Date"
      "description_columns": ["Merchant"],    // Add alternatives
      "amount_column": "Debit/Credit",        // Change from "Amount"
      ...
    }
  }
}
```

Then run with explicit bank specification:

```bash
python src/import_statement/pipeline.py \
  --statement data/raw/custom_bofa.csv \
  --bank bofa
```

## Integration with Automated Pipeline

Once you have BoFA statements working, use the monthly pipeline for full automation:

```bash
export PYTHONPATH=/home/balaji94/PycharmProjects/SplitwiseImporter

# Full pipeline: Import BoFA → Sync DB → Export to Sheets → Generate Summaries
python src/export/monthly_export_pipeline.py \
  --statement data/raw/bofa_february.csv \
  --year 2026 \
  --start-date 2026-02-01 \
  --end-date 2026-02-28
```

This runs all four steps in sequence:
1. **Import** - Parse BoFA CSV and add to Splitwise
2. **Sync** - Pull updates from Splitwise to database
3. **Export** - Write transactions to Google Sheets
4. **Summaries** - Generate monthly budget analysis

## Supported CSV Column Names

### BoFA Auto-Detection Rules

The system looks for these exact column names:

```
Required: Posted Date, Reference Number, Payee, Amount
Optional: Address
```

If your CSV doesn't have these exact names, use the `--bank bofa` flag explicitly, or edit `config/bank_config.json`.

### Amex Auto-Detection Rules

```
Required: Posted Date, Description, Amount
Optional: Extended Details, Category
```

## Adding Support for Other Banks

To add support for a new bank (e.g., Chase, Discover):

1. **Create bank configuration** in `config/bank_config.json`:

```json
{
  "banks": {
    "chase": {
      "name": "Chase Bank",
      "date_column": "Transaction Date",
      "description_columns": ["Description"],
      "amount_column": "Amount",
      "reference_column": "Reference Number",
      "category_mapping_file": "chase_category_mapping.json"
    }
  },
  "detection_rules": {
    "chase": {
      "required_columns": ["Transaction Date", "Description", "Amount"]
    }
  }
}
```

2. **Create category mapping** in `config/chase_category_mapping.json`:

```json
{
  "MERCHANT_KEYWORD": "Category > Subcategory",
  ...
}
```

3. **Test auto-detection**:

```bash
python src/import_statement/pipeline.py --statement data/raw/chase.csv --dry-run
```

4. Update this guide with the new bank details

## Questions or Issues?

See `docs/monthly_workflow.md` for complete workflow guide.
