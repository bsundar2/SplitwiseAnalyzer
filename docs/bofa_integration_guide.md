# Bank of America (BoFA) Statement Integration Guide

## Overview

The SplitwiseImporter now supports Bank of America credit card and checking account statements in addition to American Express (Amex) statements. The bank type is determined by the **folder structure** - no auto-detection needed, making it streamlined and predictable.

## Supported Banks

### American Express (Amex)
- **Location**: `data/raw/amex/amex2026.csv`
- **Required columns**: Date, Description, Amount
- **Optional columns**: Extended Details, Category
- **Category mapping**: amex_category_mapping.json

### Bank of America (BoFA)
- **Location**: `data/raw/bofa/bofa_card1_2026.csv` (multiple cards supported)
- **Required columns**: Posted Date, Reference Number, Payee, Amount  
- **Optional columns**: Address
- **Category mapping**: bofa_category_mapping.json

## Folder Structure

```
data/raw/
├── amex/
│   ├── amex2025.csv
│   ├── amex2026.csv
│   └── ... (one file per year)
└── bofa/
    ├── bofa_card1_2026.csv      # First BoFA card
    ├── bofa_card2_2026.csv      # Second BoFA card
    └── ... (add more cards as needed)
```

## Quick Start

### Import BoFA Statement

Place your BoFA CSV in the `data/raw/bofa/` folder and run:

```bash
python src/import_statement/pipeline.py \
  --statement data/raw/bofa/bofa_card1_2026.csv \
  --start-date 2026-01-01 \
  --end-date 2026-01-31
```

The bank type is automatically determined from the folder path - no `--bank` argument needed!

### Import Amex Statement

Place your Amex CSV in the `data/raw/amex/` folder and run:

```bash
python src/import_statement/pipeline.py \
  --statement data/raw/amex/amex2026.csv \
  --start-date 2026-01-01 \
  --end-date 2026-01-31
```

## CSV Format Examples

### Bank of America Statement Format

**Location**: `data/raw/bofa/bofa_card1_2026.csv`

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
- Amount column contains negative values for transactions

### American Express Statement Format

**Location**: `data/raw/amex/amex2026.csv`

```
Date,Description,Extended Details,Category,Amount
01/15/2026,GEICO AUTO PAY,12345678,"Travel-Lodging",-200.00
01/12/2026,AMAZON.COM,87654321,"Merchandise & Supplies-General Retail",-50.00
```

**Key features**:
- Location in `data/raw/amex/` folder determines parsing format
- Includes "Category" column from Amex
- Amount column contains negative values for transactions

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
4. **Move to `data/raw/bofa/` directory** (important for bank detection!)
5. **Rename file** with descriptive name (e.g., `bofa_card1_feb2026.csv` or `bofa_card2_feb2026.csv`)

### Step 2: Preview (Dry Run)

```bash
python src/import_statement/pipeline.py \
  --statement data/raw/bofa/bofa_card1_2026.csv \
  --dry-run \
  --start-date 2026-02-01 \
  --end-date 2026-02-28
```

This shows:
- Number of transactions parsed
- **Bank type automatically detected from folder** ✓
- Column mapping
- Categorization results (without creating expenses in Splitwise)

### Step 3: Import to Splitwise

```bash
python src/import_statement/pipeline.py \
  --statement data/raw/bofa/bofa_card1_2026.csv \
  --start-date 2026-02-01 \
  --end-date 2026-02-28
```

This:
- Detects BoFA from `data/raw/bofa/` folder
- Categorizes transactions using BoFA merchant mappings
- Creates Splitwise expenses
- Syncs to Google Sheets
- Exports transaction summaries

### Step 4: Process Second BoFA Card (if applicable)

```bash
python src/import_statement/pipeline.py \
  --statement data/raw/bofa/bofa_card2_2026.csv \
  --start-date 2026-02-01 \
  --end-date 2026-02-28
```

### Step 5: Sync Database

If you made manual edits in Splitwise, sync back to database:

```bash
python src/db_sync/sync_from_splitwise.py --year 2026 --live
```

## Troubleshooting

### Issue: "Cannot determine bank from file path"

**Cause**: File is not in the correct folder structure.

**Solution**: Move your file to the correct folder:
- BoFA statements → `data/raw/bofa/bofa_*.csv`
- Amex statements → `data/raw/amex/amex_*.csv`

Example:
```bash
# Wrong location
cp mystatement.csv data/raw/mystatement.csv

# Correct location
cp mystatement.csv data/raw/bofa/bofa_card1_2026.csv
```

### Issue: Transactions getting wrong categories

**Solution**: Add or update the merchant mapping in `config/bofa_category_mapping.json`:

```bash
# 1. Check which merchants are being categorized incorrectly
python src/import_statement/pipeline.py --statement data/raw/bofa/bofa_card1_2026.csv --dry-run

# 2. Find the merchant name in output
# 3. Edit config/bofa_category_mapping.json
# 4. Add/update mapping for that merchant
# 5. Re-run import
```

### Issue: Duplicate transactions detected

**Solution**: BoFA uses transaction reference numbers as unique IDs. Duplicates are detected by:
- `Reference Number` (primary key)
- Transaction amount + date (secondary check)

If you see duplicate errors, verify the reference numbers are unique in your CSV.

### Issue: Amex statement showing as wrong bank

**Cause**: Amex CSV file is in `data/raw/bofa/` folder instead of `data/raw/amex/`

**Solution**: Move to correct folder:
```bash
mv data/raw/bofa/amex_2026.csv data/raw/amex/amex_2026.csv
```

## Advanced: Custom Column Mapping (if needed)

If your BoFA or Amex export has non-standard column names, edit `config/bank_config.json`:

```json
{
  "banks": {
    "bofa": {
      "date_column": "Transaction Date",      // Change from "Posted Date"
      "description_columns": ["Merchant"],    // Change from "Payee"
      "amount_column": "Debit",               // Change from "Amount"
      ...
    }
  }
}
```

Then run normally - the bank is determined from the folder path:

```bash
python src/import_statement/pipeline.py --statement data/raw/bofa/custom_bofa.csv
```

## Adding Support for Other Banks

To add support for a new bank (e.g., Chase):

1. **Create the folder structure**:
```bash
mkdir -p data/raw/chase
```

2. **Add bank configuration** in `config/bank_config.json`:

```json
{
  "banks": {
    "chase": {
      "name": "Chase Bank",
      "date_column": "Transaction Date",
      "description_columns": ["Description"],
      "amount_column": "Amount",
      "reference_column": "Reference Number"
    }
  },
  "detection_rules": {
    "chase": {
      "required_columns": ["Transaction Date", "Description", "Amount"]
    }
  }
}
```

3. **Create category mapping** in `config/chase_category_mapping.json`:

```json
{
  "MERCHANT_KEYWORD": "Category > Subcategory",
  ...
}
```

4. **Test with a sample file**:

```bash
cp data/raw/amex/sample.csv data/raw/chase/chase_2026.csv
python src/import_statement/pipeline.py --statement data/raw/chase/chase_2026.csv --dry-run
```

## Questions or Issues?

See `docs/monthly_workflow.md` for complete workflow guide.
