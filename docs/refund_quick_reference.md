# Refund Processing - Quick Reference

**Updated: Jan 13, 2026 - Simplified Implementation**

## Overview

The refund system automatically detects credits/refunds in your CSV statements and creates corresponding Splitwise expenses. No complex matching logic - just creates expenses with the original statement description for you to manually categorize in Splitwise.

## Import Statement with Refunds

```bash
# Standard import - automatically processes refunds
python src/import_statement/pipeline.py \
  --statement data/raw/jan2026.csv \
  --start-date 2026-01-01 \
  --end-date 2026-01-31

# Check logs for:
# "Detected X credit/refund transactions"
# "Created 1 refund in Splitwise (ID: XXXXXX)"
```

## How It Works

1. **Parser Detection** - `parse_statement.py` identifies refunds via keywords (refund, credit, return) excluding payments
2. **Save to DB** - Pipeline saves refund as `is_refund=True` with `reconciliation_status='pending'`
3. **Create in Splitwise** - RefundProcessor creates expense with:
   - Original statement description (no prefix added)
   - Amount as positive (credit becomes expense you "paid")
   - Split: SELF paid 100%, SELF_EXPENSE owes 100%
   - cc_reference_id from statement (or generated UUID)
4. **Manual Categorization** - You categorize/link in Splitwise UI as needed

## Check Refund Status

```python
from src.database import DatabaseManager

db = DatabaseManager()
conn = db.get_connection()

# Get all refunds from January
cursor = conn.execute('''
    SELECT id, date, description, amount, reconciliation_status, 
           splitwise_id, cc_reference_id
    FROM transactions
    WHERE is_refund = 1 
    AND date LIKE '2026-01%'
    ORDER BY date
''')

print("Refunds in January 2026:")
for row in cursor.fetchall():
    print(f"  {row[1]} | {row[2]:40} | ${abs(row[3]):7.2f} | SW:{row[5]} | Status:{row[4]}")
```
```python
conn = db.get_connection()
cursor = conn.cursor()
cursor.execute("""
    SELECT id, date, merchant, amount, reconciliation_status
    FROM transactions
    WHERE is_refund = 1
    ORDER BY date DESC
""")
refunds = cursor.fetchall()
```

### Find Refunds for Specific Merchant
```python
cursor.execute("""
    SELECT * FROM transactions
    WHERE is_refund = 1
    AND merchant LIKE ?
    ORDER BY date DESC
""", ("%Restaurant%",))
```

### Find Partial Refunds
```python
cursor.execute("""
    SELECT * FROM transactions
    WHERE is_refund = 1
    AND is_partial_refund = 1
    ORDER BY refund_percentage DESC
""")
```

### Find Originals with Credits Applied
```python
cursor.execute("""
    SELECT 
        t.id,
        t.merchant,
        t.amount as original_amount,
        ABS(r.amount) as credit_amount,
        (ABS(r.amount) / t.amount * 100) as credit_percentage,
        (t.amount - ABS(r.amount)) as net_cost
    FROM transactions t
    INNER JOIN transactions r ON r.refund_for_txn_id = t.id
    WHERE t.is_refund = 0
    AND r.is_partial_refund = 1
    ORDER BY credit_percentage DESC
""")
```

### Find Unmatched Refunds
```python
cursor.execute("""
    SELECT * FROM transactions
    WHERE is_refund = 1
    AND reconciliation_status IN ('pending', 'unmatched', 'manual_review')
    ORDER BY date
""")
```

### Audit Refund Linkage
```python
cursor.execute("""
    SELECT 
        r.id as refund_id,
        r.date as refund_date,
        r.merchant,
        r.amount as refund_amount,
        r.refund_match_method,
        r.reconciliation_status,
        o.date as original_date,
        o.amount as original_amount,
        o.splitwise_id as original_sw_id
    FROM transactions r
    LEFT JOIN transactions o ON r.refund_for_txn_id = o.id
    WHERE r.is_refund = 1
    ORDER BY r.date DESC
""")
```

## Troubleshooting

### Refund Not Matched
```python
# Check why refund wasn't matched
refund = db.get_transaction_by_id(refund_id)
print(f"Status: {refund.reconciliation_status}")
print(f"Notes: {refund.notes}")

# Try manual search
original = db.find_original_for_refund(
    refund_amount=refund.amount,
    refund_date=refund.date,
    merchant=refund.merchant,
    cc_reference_id=refund.cc_reference_id,
    date_window_days=180  # Expand search window
)
if original:
    print(f"Found potential match: {original.id}")
else:
    print("No match found - check if original imported")
```

### Verify Refund Created in Splitwise
```python
from src.common.splitwise_client import SplitwiseClient

client = SplitwiseClient()
expense = client.get_expense(refund.splitwise_id)
print(f"Description: {expense.getDescription()}")
print(f"Amount: ${expense.getCost()}")
print(f"Notes: {expense.getNotes()}")
```

## Reconciliation Status Values

- **pending** - Refund imported but not yet matched
- **matched** - Matched to original and Splitwise expense created
- **unmatched** - Could not find original transaction
- **manual_review** - Requires manual investigation

## Key Fields

- `cc_reference_id` - Credit card transaction reference (for matching)
- `is_refund` - True for refunds/credits
- `refund_for_txn_id` - Links to original transaction in database
- `refund_for_splitwise_id` - Links to original Splitwise expense
- `refund_match_method` - How match was made (txn_id, merchant_amount, manual)
- `reconciliation_status` - Current processing status
