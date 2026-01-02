# Merchant Review System - Quick Demo

This demonstrates the merchant review workflow you now have available.

## What You Have

You now have a complete merchant review system with:

### 1. **Interactive Review Tool** (`src/review_merchants.py`)
   - Review merchants one-by-one with a friendly CLI interface
   - Approve correct extractions or provide corrections
   - Auto-saves progress every 10 transactions
   - Resume anytime from where you left off

### 2. **Feedback Application Tool** (`src/apply_review_feedback.py`)
   - Applies your corrections to the merchant lookup config
   - Shows detailed report of changes
   - Analyzes patterns to suggest algorithm improvements
   - Moves reviewed items to archive

### 3. **Helper Script** (`review.sh`)
   - Simple commands to run the workflow
   - Handles environment setup automatically

## Example Workflow

Let's walk through a complete example:

### Step 1: Run Pipeline to Generate Review Data

```bash
# Process your statement
export PYTHONPATH=/home/balaji94/PycharmProjects/SplitwiseImporter
source .venv/bin/activate
python src/pipeline.py --statement data/raw/amex2025.csv
```

This creates `data/processed/merchant_names_for_review.csv` with entries like:

| date | amount | description | expected_merchant | category_name | expected_category |
|------|--------|-------------|-------------------|---------------|-------------------|
| 2025-12-26 | 750.0 | ZII7Npgai Fd... | Wow Auto Detailers | Transportation | Transportation |
| 2025-12-25 | 97.01 | Telecom... | Google Fi | Uncategorized | Uncategorized |
| 2025-12-25 | 2.99 | Cable & PAY... | Hulu | Utilities | Utilities |

You currently have **2,284 transactions** to review!

### Step 2: Start Reviewing (Interactive)

```bash
# Review 20 merchants at a time
./review.sh start --batch 20
```

**Example interaction:**

```
================================================================================
Transaction 1 of 2284
================================================================================

Date:        2025-12-26
Amount:      $750.00

Raw Description:
ZII7NpgaiFd squareup.com/receipts
GglPay WOW AUTO DETAILERS
San Francisco
CA
squareup.com/receipts

────────────────────────────────────────────────────────────────────────────────
Extracted Merchant:  Wow Auto Detailers
Current Category:    Transportation
Current Subcategory: Car
================================================================================

Action [a/c/s/q/h]: a
✓ Approved

================================================================================
Transaction 2 of 2284
================================================================================

Date:        2025-12-25
Amount:      $97.01

Raw Description:
A1439NXM    TELECOM SERVICE
GOOGLE *FI T43VHB
G.CO/HELPPAY#
CA
TELECOM SERVICE

────────────────────────────────────────────────────────────────────────────────
Extracted Merchant:  Google Fi
Current Category:    Uncategorized
Current Subcategory: General
================================================================================

Action [a/c/s/q/h]: c

Provide corrections (press Enter to keep current value):
Merchant name [Google Fi]: 
Category [Uncategorized]: Utilities
Subcategory [General]: TV/Phone/Internet
✓ Correction saved

================================================================================
Transaction 3 of 2284
================================================================================
...

💾 Auto-saved progress (10/2284)
```

After reviewing 20, you can:
- Press **[q]** to quit and save
- Or continue reviewing more

### Step 3: Check Your Progress

```bash
./review.sh stats
```

**Output:**
```
📊 Review statistics:

================================================================================
REVIEW STATISTICS
================================================================================
Approved: 103
Corrected: 17
Skipped: 0
Total reviewed: 120

Recent corrections:
  Google Fi → Google Fi
    Category: Uncategorized → Utilities
  Uber Trip → Uber
    Category: Transportation → Transportation
  ...
```

### Step 4: Apply Your Corrections

```bash
# Preview changes first
./review.sh apply --dry-run
```

**Output:**
```
Loaded feedback:
  Approved:  103 entries
  Corrected: 17 entries
  Skipped:   0 entries

🔍 DRY RUN - No changes will be saved

================================================================================
FEEDBACK APPLICATION REPORT
================================================================================

Summary:
  Added:     98 new merchant mappings
  Updated:   5 existing mappings
  Unchanged: 103 approved existing mappings
  Total:     103 changes applied

────────────────────────────────────────────────────────────────────────────────
Recent Changes:
────────────────────────────────────────────────────────────────────────────────

✓ Added (98 merchants):
  • Wow Auto Detailers
    → Transportation / Car
  • Google Fi
    → Utilities / TV/Phone/Internet
  • Hulu
    → Utilities / TV/Phone/Internet
  ...

✓ Updated (5 merchants):
  • Uber Trip → Uber
    Subcategory: Taxi → Ride Share
  ...

================================================================================

💡 Run without --dry-run to apply these changes
```

When ready:
```bash
./review.sh apply
```

This updates `config/merchant_category_lookup.json` with your corrections!

### Step 5: Re-run Pipeline to See Improvements

```bash
python src/pipeline.py --statement data/raw/amex2025.csv
```

Now the pipeline will use your corrections, so:
- "Google Fi" will be categorized as Utilities/TV/Phone/Internet
- "Uber Trip" will be normalized to "Uber"
- And so on for all your corrections!

### Step 6: Continue Reviewing

```bash
# Continue from where you left off (transaction 121)
./review.sh continue 120
```

## Tips for Efficient Reviewing

### 1. Review in Sessions
Don't try to do all 2,284 at once! Break it up:
```bash
./review.sh start --batch 50  # Morning session
./review.sh continue 50       # Afternoon session
./review.sh continue 100      # Evening session
```

### 2. Focus on High-Impact Items First
The most common merchants appear multiple times in your review file. Correcting these has the biggest impact on your data quality.

### 3. Use Keyboard Shortcuts
- **[a]** for approve (most common)
- **[c]** for correct
- **[s]** for skip (review later)
- **[q]** to quit and save

### 4. Provide Consistent Names
When correcting:
- Use Title Case: "Starbucks" not "STARBUCKS"
- Be concise: "Target" not "Target Corporation Store #2341"
- Remove locations: "Safeway" not "Safeway - San Francisco"

### 5. Common Categories

Based on your config:
- **Food and drink**: Restaurants, grocery, coffee
- **Transportation**: Uber, Lyft, gas, parking  
- **Utilities**: Phone, internet, streaming (Hulu, Netflix)
- **Life**: Healthcare, insurance, gym
- **Shopping**: Amazon, retail stores
- **Entertainment**: Movies, hobbies
- **General**: Miscellaneous

## Current Status

Your review file currently has:
- **2,284 unique transaction entries**
- Located at: `data/processed/merchant_names_for_review.csv`
- **0 reviewed so far** (ready for you to start!)

## Next Steps

1. **Start reviewing**: `./review.sh start --batch 20`
2. **Review a few batches** to get a feel for it
3. **Apply your corrections**: `./review.sh apply`
4. **Re-run pipeline** to see improvements
5. **Repeat** until you've reviewed all merchants

The more you review, the smarter the system becomes! Your corrections get saved to the merchant lookup and will be reused automatically.

## Questions?

See the full guide: [docs/merchant_review_workflow.md](merchant_review_workflow.md)

---

**Happy reviewing! 🎯**
