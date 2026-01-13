# Refund Processing - Quick Reference

## Import Statement with Refunds

```bash
# Standard import - automatically processes refunds
python src/import_statement/pipeline.py \
  --statement data/raw/jan2026.csv \
  --start-date 2026-01-01 \
  --end-date 2026-01-31

# Check logs for:
# "Processing refunds (matching to original transactions)..."
# "Refund processing summary:"
```

## Process Pending Refunds

```bash
# Preview what would happen
python -m src.import_statement.process_refunds --dry-run --verbose

# Process all pending refunds
python -m src.import_statement.process_refunds --verbose
```

## Check Refund Status

```python
from src.database import DatabaseManager

db = DatabaseManager()

# Get all unmatched refunds
pending = db.get_unmatched_refunds()
print(f"Found {len(pending)} pending refunds")

# Get specific transaction
txn = db.get_transaction_by_id(123)
print(f"Status: {txn.reconciliation_status}")
print(f"Refund for: {txn.refund_for_txn_id}")
print(f"Partial refund: {txn.is_partial_refund}")
print(f"Refund percentage: {txn.refund_percentage:.1f}%")

# Get total refunds for an original transaction (should be 0 or 1 refund)
original_id = 456
total_refunded = db.get_total_refunds_for_original(original_id)
original = db.get_transaction_by_id(original_id)
print(f"Credit applied: ${total_refunded:.2f} of ${original.amount:.2f}")
print(f"Net cost: ${original.amount - total_refunded:.2f}")
```

## Manual Refund Linking

```python
from src.database import DatabaseManager
from src.import_statement.process_refunds import RefundProcessor
from src.common.splitwise_client import SplitwiseClient

db = DatabaseManager()
client = SplitwiseClient()

# Link refund to original manually
db.update_refund_linkage(
    refund_txn_id=456,           # Refund transaction ID
    original_txn_id=123,          # Original transaction ID
    original_splitwise_id=789012, # Original Splitwise expense ID
    match_method="manual"
)

# Create Splitwise expense for manually linked refund
refund = db.get_transaction_by_id(456)
processor = RefundProcessor(db, client)
result = processor.process_refund(refund, dry_run=False)
print(f"Result: {result['status']}")
```

## Common Queries

### Find All Refunds
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
