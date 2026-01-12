# Merchant Review Workflow

This guide explains how to review merchant names and categories extracted by the pipeline, provide corrections, and use those corrections to improve the algorithm.

## Overview

The merchant review workflow consists of three main steps:

1. **Generate Review Data** - Extract unique merchants from processed CSV for review
2. **Review & Provide Feedback** - Use the interactive review tool to correct merchant names and categories
3. **Apply Feedback** - Update the merchant lookup configuration with your corrections

### Unified Workflow (Recommended)

For convenience, use `run_review_workflow.py` to execute all three steps automatically:

```bash
python src/merchant_review/run_review_workflow.py --processed-csv data/processed/statement.csv.processed.csv --batch 20
```

This will:
1. Generate the review file from your processed CSV
2. Launch the interactive review tool (batch of 20)
3. Apply approved corrections to the merchant lookup config

### Individual Steps (Advanced)

You can also run each step separately for more control (see sections below).

## Files Involved

| File | Purpose |
|------|---------|
| `src/merchant_review/run_review_workflow.py` | **NEW** Unified workflow - runs all steps automatically |
| `src/merchant_review/generate_review_file.py` | Generate review CSV from processed transactions |
| `src/merchant_review/review_merchants.py` | Interactive review tool |
| `src/merchant_review/apply_review_feedback.py` | Apply corrections to merchant lookup |
| `data/processed/merchant_names_for_review.csv` | Generated merchants for review |
| `data/processed/merchant_review_feedback.json` | Stores your feedback (approved, corrected, skipped) |
| `data/processed/done_merchant_names_for_review.csv` | Archive of reviewed merchants |
| `config/merchant_category_lookup.json` | Master lookup file updated with your corrections |

## Step 1: Generate Review Data

Generate a review file from your processed CSV statement:

```bash
# Set PYTHONPATH for module imports
export PYTHONPATH=/home/balaji94/PycharmProjects/SplitwiseImporter

# Generate review file from processed CSV (required arguments)
python src/merchant_review/generate_review_file.py \
  --processed-csv data/processed/your_statement.csv.processed.csv \
  --output data/processed/merchant_names_for_review.csv
```

**Note:** Both arguments are required. The script will fail if either is missing.

This creates `merchant_names_for_review.csv` with unique merchant entries that aren't already in your merchant lookup.

## Step 2: Interactive Review

Use the interactive review tool to go through merchants one by one:

```bash
# Start reviewing (will review ALL merchants)
python src/review_merchants.py

# Review in batches of 20
python src/review_merchants.py --batch 20

# Continue from where you left off (e.g., transaction 50)
python src/review_merchants.py --start 50

# Check statistics
python src/review_merchants.py --stats
```

### Review Actions

For each merchant, you can:

- **[a] Approve** - The extracted merchant name and category are correct
- **[c] Correct** - Provide the correct merchant name and/or category
- **[s] Skip** - Skip this merchant for now (you can review it later)
- **[q] Quit** - Save progress and exit (you can resume later)
- **[h] Help** - Show instructions again

### Review Screen Example

```
================================================================================
Transaction 15 of 234
================================================================================

Date:        2025-12-23
Amount:      $26.72

Raw Description:
61d376545a5 TAXICAB & LIMOUSINE
GRAB*A-8PXHISMWWU9TAV
SINGAPORE
SG

────────────────────────────────────────────────────────────────────────────────
Extracted Merchant:  Grab
Current Category:    Transportation
Current Subcategory: Taxi
================================================================================

Action [a/c/s/q/h]:
```

### Providing Corrections

When you choose **[c] Correct**, you'll be prompted:

```
Provide corrections (press Enter to keep current value):
Merchant name [Grab]: 
Category [Transportation]: 
Subcategory [Taxi]: 
```

Just type the correct value, or press Enter to keep the current value.

## Step 3: Apply Feedback

After reviewing merchants, apply your feedback to update the configuration:

```bash
# Preview what will change (dry run)
python src/apply_review_feedback.py --dry-run

# Apply changes and analyze patterns
python src/apply_review_feedback.py --analyze

# Just apply changes
python src/apply_review_feedback.py
```

This will:
1. Update `config/merchant_category_lookup.json` with your corrections
2. Move reviewed entries to `done_merchant_names_for_review.csv`
3. Remove reviewed entries from `merchant_names_for_review.csv`
4. Show a summary of changes

### Report Example

```
================================================================================
FEEDBACK APPLICATION REPORT
================================================================================

Summary:
  Added:     45 new merchant mappings
  Updated:   12 existing mappings
  Unchanged: 103 approved existing mappings
  Total:     57 changes applied

────────────────────────────────────────────────────────────────────────────────
Recent Changes:
────────────────────────────────────────────────────────────────────────────────

✓ Added (45 merchants):
  • Wow Auto Detailers
    → Transportation / Car
  • Guardian Health & Beauty
    → Life / Medical expenses
  ...

✓ Updated (12 merchants):
  • Uber Trip → Uber
    Category: Transportation → Transportation
    Subcategory: Taxi → Ride Share
  ...

================================================================================
```

## Step 4: Re-run Pipeline

After applying feedback, re-run the pipeline to see the improvements:

```bash
python src/pipeline.py --statement data/raw/your_statement.csv
```

The pipeline will now use your corrections when processing transactions.

## Tips & Best Practices

### 1. Review in Batches

Don't try to review everything at once. Use `--batch` to review 20-50 at a time:

```bash
python src/review_merchants.py --batch 20
```

### 2. Focus on High-Frequency Merchants First

The review file contains duplicate entries for merchants that appear multiple times. Reviewing these first has the biggest impact.

### 3. Use Consistent Naming

When correcting merchant names, use consistent formatting:
- **Title Case**: "Starbucks Coffee" not "STARBUCKS COFFEE" or "starbucks coffee"
- **Common Names**: "Uber" not "Uber Technologies Inc."
- **Remove Locations**: "Target" not "Target #2341" or "Target San Francisco"

### 4. Category Guidelines

Use these standard categories (based on your `amex_category_mapping.json`):

| Category | Examples |
|----------|----------|
| Food and drink | Restaurants, grocery stores, coffee shops |
| Transportation | Uber, Lyft, gas stations, parking |
| Utilities | Internet, phone, electricity, streaming services |
| Life | Healthcare, insurance, gym memberships |
| Entertainment | Movies, concerts, hobbies |
| Shopping | Amazon, clothing stores, electronics |
| General | Miscellaneous expenses |

### 5. Save Frequently

The tool auto-saves every 10 transactions, but you can quit anytime with **[q]** to save progress.

### 6. Check Statistics

Before and after reviewing, check your progress:

```bash
python src/review_merchants.py --stats
```

### 7. Analyze Patterns

After applying feedback, use `--analyze` to see common correction patterns:

```bash
python src/apply_review_feedback.py --analyze
```

This helps identify systematic issues in the extraction algorithm that you might want to fix.

## Workflow Diagram

```
┌─────────────────────┐
│   Run Pipeline      │
│ (parse statement)   │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────────────────┐
│ merchant_names_for_review.csv   │
│ (unique merchants extracted)    │
└──────────┬──────────────────────┘
           │
           ▼
┌─────────────────────┐
│  Review Merchants   │◄──── Resume with --start
│  (interactive CLI)  │
└──────────┬──────────┘
           │
           ▼
┌──────────────────────────┐
│ merchant_review_feedback │
│        .json             │
└──────────┬───────────────┘
           │
           ▼
┌─────────────────────┐
│  Apply Feedback     │
│  (update config)    │
└──────────┬──────────┘
           │
           ▼
┌────────────────────────────────┐
│ merchant_category_lookup.json  │
│ (updated with corrections)     │
└────────────────────────────────┘
           │
           ▼
┌─────────────────────┐
│   Run Pipeline      │
│  (uses updated      │
│   configurations)   │
└─────────────────────┘
```

## Troubleshooting

### "Review file not found"

Run the pipeline first to generate the review file:
```bash
python src/pipeline.py --statement data/raw/your_statement.csv
```

### "All transactions have been reviewed"

Great! Check if there are any skipped items you want to revisit:
```bash
python src/review_merchants.py --stats
```

### Want to Re-review Something

Edit `merchant_review_feedback.json` and remove the entry from `approved` or `corrected` arrays.

### Reset Everything

To start fresh:
```bash
rm data/processed/merchant_review_feedback.json
rm data/processed/done_merchant_names_for_review.csv
# The next pipeline run will regenerate the review file
```

## Advanced: Bulk Corrections

If you have many similar corrections, you can edit `merchant_review_feedback.json` directly:

```json
{
  "approved": [],
  "corrected": [
    {
      "description_raw": "...",
      "expected_merchant": "UBER EATS",
      "corrected_merchant": "Uber Eats",
      "category_name": "Food and drink",
      "corrected_category": "Food and drink",
      "subcategory_name": "Dining out",
      "corrected_subcategory": "Dining out"
    }
  ],
  "skipped": []
}
```

Then run:
```bash
python src/apply_review_feedback.py
```

## Next Steps

Once you've reviewed and applied feedback for a batch of merchants:

1. Re-run the pipeline to verify improvements
2. Check the categorization accuracy
3. Review any remaining merchants
4. Consider updating the extraction rules in `src/utils.py` if you see patterns

---

**Happy reviewing! 🎯**
