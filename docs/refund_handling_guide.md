# Refund and Credit Handling Guide

## Overview

The Splitwise Importer now includes a robust, idempotent system for handling refunds and credits from credit card statements. Refunds are automatically matched to their original transactions and created in Splitwise with the same category and split ratios.

**Phase 6 Update**: Refund detection keywords now centralized in `src/constants/splitwise.py` as `REFUND_KEYWORDS` tuple for better maintainability.

## Key Principles

1. **Refunds reduce actual spending** - Negative Splitwise expenses are created
2. **Category preservation** - Refunds inherit the original transaction's category
3. **Split fairness** - Refunds mirror the original split ratios exactly
4. **Auditability** - Complete linkage trail from refund → original transaction
5. **Idempotency** - Safe to re-run indefinitely, no duplicate refunds created

## Architecture

### Database Schema

The `transactions` table includes refund tracking fields:

```sql
-- Refund identification
cc_reference_id TEXT                   -- Credit card reference ID for matching
is_refund BOOLEAN                      -- True if this is a refund/credit

-- Refund linkage
refund_for_txn_id INTEGER              -- Links to original transaction DB ID
refund_for_splitwise_id INTEGER        -- Links to original Splitwise expense ID
refund_created_at TEXT                 -- When refund was created in Splitwise
reconciliation_status TEXT             -- pending, matched, unmatched, manual_review
refund_match_method TEXT               -- txn_id, merchant_amount, manual
```

### Workflow

```
CSV Statement Import
        ↓
    Detect Refunds (negative amount)
        ↓
    Store in Database (reconciliation_status=pending)
        ↓
    Match to Original Transaction
        ├── By cc_reference_id (preferred)
        └── By merchant + amount + date window (fallback)
        ↓
    Check Idempotency (refund already exists?)
        ↓
    Create Negative Splitwise Expense
        ├── Same category/subcategory as original
        ├── Same participants and split ratios (reversed)
        └── Notes link to original expense
        ↓
    Update Database Linkage
        └── reconciliation_status=matched
```

## Usage

### Automatic Processing (Recommended)

Refunds are processed automatically after importing statements:

```bash
# Import statement - refunds are detected and stored
python src/import_statement/pipeline.py \
  --statement data/raw/jan2026.csv \
  --start-date 2026-01-01 \
  --end-date 2026-01-31

# Refunds are automatically matched and created in Splitwise
# Check logs for "Processing refunds..." section
```

### Manual Refund Processing

Process pending refunds separately (useful for troubleshooting):

```bash
# Dry run - preview what would happen
python -m src.import_statement.process_refunds --dry-run --verbose

# Live run - process all pending refunds
python -m src.import_statement.process_refunds --verbose
```

### Check Pending Refunds

Query database for unmatched refunds:

```python
from src.database import DatabaseManager

db = DatabaseManager()
pending = db.get_unmatched_refunds()

print(f"Found {len(pending)} pending refunds:")
for refund in pending:
    print(f"  - {refund.date}: {refund.merchant} ${refund.amount:.2f}")
    print(f"    Status: {refund.reconciliation_status}")
```

## Matching Logic

### Strategy 1: cc_reference_id Match (Preferred)

- Most reliable method
- Uses credit card transaction reference ID
- Supports both full and partial refunds
- Match criteria:
  - `cc_reference_id` (same for refund and original)
  - `refund_amount` ≤ `original_amount` (allows partial refunds)
  - `is_refund = 0` (must be original, not another refund)

### Strategy 2: Merchant + Amount + Date Window (Fallback)

- Used when cc_reference_id not available
- Searches for matching:
  - `merchant` (exact match)
  - `refund_amount` ≤ `original_amount` (allows partial refunds)
  - `date` (refund date within 90 days after original)
- Returns closest match by amount if multiple found
- Prefers most recent transaction

### Partial Refund Support

The system automatically detects and handles partial refunds and credits:

- **Full refund**: Refund ≥ 95% of original amount (e.g., $98 refund on $100, allowing for $2 return fee)
- **Partial refund**: Refund < 95% of original amount
- **One refund per transaction**: System allows only one refund/credit per original transaction
- **Percentage calculation**: Records refund as % of original
- **Net cost tracking**: Always shows remaining cost after refund

Example use cases:
```
# Full refund with return fee
Original: $100 item
Refund: -$95 (refund minus $5 restocking fee)
Splitwise: "REFUND: Item XYZ"
Notes: "Refund amount: $95.00 of $100.00 (95.0%) / Net cost: $5.00"

# Amex hotel credit
Original: $2000 hotel booking
Credit: -$300 (Amex travel credit, 15%)
Splitwise: "REFUND (15%): Hotel XYZ"
Notes: "Refund amount: $300.00 of $2000.00 (15.0%) / Net cost: $1,700.00"

# Restaurant refund for poor service  
Original: $150 dinner
Credit: -$30 (20% discount applied)
Splitwise: "REFUND (20%): Restaurant ABC"
Notes: "Refund amount: $30.00 of $150.00 (20.0%) / Net cost: $120.00"

# Full refund (100%)
Original: $100 cancelled reservation
Refund: -$100 (100% refund)
Splitwise: "REFUND: Restaurant ABC"
Notes: "Refund amount: $100.00 of $100.00 (100.0%) / Net cost: $0.00"
```

### Unmatched Handling

If no original transaction found:
- `reconciliation_status` set to `manual_review`
- Logged with reason for manual investigation
- Does NOT create Splitwise expense automatically

## Splitwise Refund Creation

Refunds are created as **negative expenses** with:

### Same Category
```python
category_id = original.category_id
subcategory_id = original.subcategory_id
```

### Reversed Split
Original expense:
```
SELF_EXPENSE paid: $100.00, owed: $0.00
Current user paid: $0.00, owed: $100.00
```

Refund expense:
```
SELF_EXPENSE paid: $0.00, owed: $100.00  # Reversed
Current user paid: $100.00, owed: $0.00  # Reversed
```

### Descriptive Notes
```
Description: REFUND: Original Merchant Name
Notes:
  REFUND for Splitwise expense 123456789
  Original cc_reference_id: ABC123DEF456
  Refund cc_reference_id: XYZ789GHI012
```

## Idempotency Guarantees

### Check Before Creating
```python
# Prevents duplicate refunds for same original transaction
if db.has_existing_refund_for_original(original_txn_id, refund_amount):
    return "duplicate"
```

### Uniqueness Enforced By
1. **cc_reference_id** - Each refund has unique reference ID
2. **refund_for_txn_id** - One refund per original transaction
3. **amount match** - Prevents multiple refunds of same amount

### Safe Re-runs
- Re-importing same statement: Refunds detected but not duplicated
- Re-running process_pending_refunds.py: Skips already-matched refunds
- Manual edits in Splitwise: Database syncs back latest state

## Audit Trail

### Database Tracking
```sql
SELECT 
  r.id as refund_id,
  r.date as refund_date,
  r.merchant,
  r.amount as refund_amount,
  r.refund_for_txn_id as original_id,
  r.refund_for_splitwise_id as original_sw_id,
  r.refund_match_method,
  r.reconciliation_status,
  o.date as original_date,
  o.amount as original_amount
FROM transactions r
LEFT JOIN transactions o ON r.refund_for_txn_id = o.id
WHERE r.is_refund = 1
ORDER BY r.date DESC;
```

### Splitwise Notes
Every refund expense includes:
- Original Splitwise expense ID
- Original cc_reference_id
- Refund cc_reference_id
- Clear "REFUND:" prefix in description

## Common Scenarios

### Scenario 1: Full Refund
```
Original: $150 dinner at Restaurant ABC
Refund: -$150 credit from Restaurant ABC
Result: Matched by cc_reference_id, negative expense created
Splitwise: "REFUND: Restaurant ABC"
Notes: "Refund amount: $150.00 of $150.00 (100.0%) / Net cost: $0.00"
```

### Scenario 2: Full Refund with Return Fee
```
Original: $100 online purchase
Refund: -$95 (minus $5 restocking fee)
Result: Matched as full refund (95%+)
Splitwise: "REFUND: Amazon - Widget XYZ"
Notes: "Refund amount: $95.00 of $100.00 (95.0%) / Net cost: $5.00"
Net spending: $5 (the return fee you paid)
```

### Scenario 3: Partial Credit (Amex Travel)
```
Original: $2000 hotel booking at Marriott
Credit: -$300 (Amex travel credit, 15%)
Result: Matched as partial refund (15%)
Splitwise: "REFUND (15%): Marriott Hotel"
Notes: "Refund amount: $300.00 of $2000.00 (15.0%) / Net cost: $1,700.00"
Net spending: $1700
```

### Scenario 4: Restaurant Discount/Refund
```
Original: $150 dinner
Credit: -$30 (service issue discount, 20%)
Result: Matched as partial refund (20%)
Splitwise: "REFUND (20%): Restaurant ABC"
Notes: "Refund amount: $30.00 of $150.00 (20.0%) / Net cost: $120.00"
Net spending: $120
```

### Scenario 5: Multiple Purchases Same Day
```
Original 1: $25 at Coffee Shop (txn_id: ABC123)
Original 2: $25 at Coffee Shop (txn_id: ABC456)
Refund: -$25 at Coffee Shop (txn_id: ABC123)
Result: Matched by cc_reference_id to Original 1 only
```

### Scenario 6: Late Refund Processing
```
Original: $100 purchase in December 2025
Refund: -$100 credit in January 2026
Result: Matched by merchant+amount+date (within 90-day window)
```

## Troubleshooting

### Refund Not Matched

**Check reconciliation status:**
```python
refund = db.get_transaction_by_id(refund_id)
print(refund.reconciliation_status)  # Should be "unmatched" or "manual_review"
print(refund.notes)  # Contains reason
```

**Common reasons:**
- Original transaction not in database yet
- Amount mismatch (partial refund)
- Merchant name differs between purchase and refund
- Original transaction deleted from Splitwise

**Manual fix:**
```python
# Link refund to original manually
db.update_refund_linkage(
    refund_txn_id=123,
    original_txn_id=456,
    original_splitwise_id=789012,
    match_method="manual"
)

# Then create Splitwise expense
processor = RefundProcessor(db, client)
result = processor.process_refund(refund, dry_run=False)
```

### Duplicate Refund Created

**Should not happen** - system prevents this via idempotency checks.

If it does occur:
1. Check database for duplicate entries
2. Delete duplicate Splitwise expense manually
3. Report issue (indicates bug)

### Original Transaction Missing Splitwise ID

**Symptom:** Refund marked as "unmatched" with error "Original not in Splitwise"

**Fix:**
1. Import original transaction first
2. Sync database with Splitwise
3. Re-run refund processing

```bash
python src/import_statement/pipeline.py --statement original_statement.csv
python src/db_sync/sync_from_splitwise.py --year 2026 --live
python src/import_statement/process_pending_refunds.py
```

## Google Sheets Integration

Refunds flow naturally into sheets as negative values:

### Export Behavior
- Refund transactions have negative amounts
- Category totals automatically reduced
- Budget tracking reflects refunds
- No special filtering needed

### Summary Impact
```
Monthly Summary:
  Total Spent: $5,000
  Refunds: -$200
  Net Spending: $4,800  ← Automatically calculated
```

## Migration Notes

### Upgrading Existing Database

If you have an existing database without refund fields:

```bash
# 1. Backup database
cp data/transactions.db data/transactions_backup.db

# 2. Schema will auto-update on first run
python -c "from src.database import DatabaseManager; DatabaseManager()"

# 3. Verify new columns exist
sqlite3 data/transactions.db "PRAGMA table_info(transactions);"
```

### Processing Historical Refunds

If you have old refunds in Splitwise but not linked:

```python
# Query database for unlinked refunds (negative amounts without refund_for_txn_id)
# Manually link using db.update_refund_linkage()
# Or re-import statements to detect and link automatically
```

## Best Practices

1. **Always include cc_reference_id** in statements
   - Most reliable matching method
   - Prevents false matches

2. **Import statements chronologically**
   - Original transaction must exist before refund
   - Avoids "unmatched" status

3. **Review unmatched refunds monthly**
   - Check logs after imports
   - Investigate manual_review cases

4. **Don't delete original expenses** from Splitwise
   - Breaks refund linkage
   - Keep deleted transactions in database

5. **Use dry-run mode for testing**
   - Verify matching logic
   - Preview before creating expenses

## API Reference

### RefundProcessor

```python
from src.import_statement.process_refunds import RefundProcessor

processor = RefundProcessor(db=db_manager, client=splitwise_client)

# Process single refund
result = processor.process_refund(refund_txn, dry_run=False)

# Process all pending
summary = processor.process_all_pending_refunds(dry_run=False)
```

### DatabaseManager Refund Methods

```python
from src.database import DatabaseManager

db = DatabaseManager()

# Find original for refund
original = db.find_original_for_refund(
    refund_amount=150.00,
    refund_date="2026-01-15",
    merchant="Restaurant ABC",
    cc_reference_id="ABC123",
    date_window_days=90
)

# Get unmatched refunds
pending = db.get_unmatched_refunds()

# Check for existing refund
exists = db.has_existing_refund_for_original(
    original_txn_id=123,
    refund_amount=150.00
)

# Update refund linkage
db.update_refund_linkage(
    refund_txn_id=456,
    original_txn_id=123,
    original_splitwise_id=789012,
    match_method="txn_id"
)

# Mark as unmatched
db.mark_refund_as_unmatched(
    refund_txn_id=456,
    reason="Original not found"
)
```

## Future Enhancements

Potential improvements for Phase 6:

1. **Partial Refund Support**
   - Match refunds that don't equal original amount
   - Track multiple refunds for same original

2. **Smart Matching**
   - Machine learning for merchant name variations
   - Fuzzy date matching with confidence scores

3. **Refund Notifications**
   - Email alerts for unmatched refunds
   - Monthly reconciliation reports

4. **Bulk Manual Linking**
   - UI for manually matching refunds
   - Batch approval workflow

5. **Splitwise API Improvements**
   - Native refund/reversal transactions
   - Explicit refund linkage in API
