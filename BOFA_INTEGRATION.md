# BoFA Integration - Quick Reference

## Files Added/Modified

### New Files (3)
- ✅ `src/import_statement/bank_config.py` - Bank configuration management
- ✅ `config/bank_config.json` - Multi-bank configuration
- ✅ `config/bofa_category_mapping.json` - BoFA merchant mappings

### Modified Files (4)  
- ✅ `src/import_statement/parse_statement.py` - Multi-bank parsing
- ✅ `src/common/utils.py` - Bank-specific categorization
- ✅ `src/import_statement/pipeline.py` - Bank parameter handling
- ✅ Documentation files added (2)

## Usage

### Auto-Detection (Recommended)
```bash
python src/import_statement/pipeline.py --statement data/raw/bofa_statement.csv
```

### Explicit Bank
```bash
python src/import_statement/pipeline.py --statement data/raw/bofa_statement.csv --bank bofa
```

### With Date Range
```bash
python src/import_statement/pipeline.py \
  --statement data/raw/bofa_statement.csv \
  --start-date 2026-02-01 \
  --end-date 2026-02-28
```

## BoFA CSV Format

Required columns:
- `Posted Date` (MM/DD/YYYY format)
- `Reference Number` (unique transaction ID)
- `Payee` (merchant name)
- `Amount` (negative for debits/transactions)

Optional:
- `Address` (merchant address)

## Category Mapping

Edit `config/bofa_category_mapping.json` to add merchant mappings:

```json
{
  "YOUR_MERCHANT": "Category > Subcategory",
  "WHOLE_FOODS": "Food and drink > Groceries",
  "BEST_BUY": "Home > Electronics"
}
```

## Key Features

✅ Auto-detection (detects BoFA vs Amex automatically)
✅ Bank-specific categorization (uses bofa_category_mapping.json first)
✅ Backward compatible (existing Amex workflows unchanged)
✅ Database integration (same as Amex)
✅ Google Sheets sync (same format as Amex)
✅ Extensible (easy to add Chase, Discover, etc.)

## Test Results

All validation tests passed:
- ✅ Module imports
- ✅ BoFA auto-detection
- ✅ Amex auto-detection
- ✅ Transaction parsing (3 transactions @ $1,180.78)
- ✅ BoFA categorization (bank_specific_bofa confidence)
- ✅ Mapping loading (46 merchant entries)
- ✅ CLI argument parsing

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Not detected as BoFA | Check CSV columns: Posted Date, Reference Number, Payee, Amount |
| Wrong categories | Add/update mapping in `config/bofa_category_mapping.json` |
| Duplicates | Reference Number must be unique |

## Documentation

- [BoFA Integration Guide](docs/bofa_integration_guide.md) - Comprehensive guide with examples
- [Onboarding Summary](docs/bofa_onboarding_summary.md) - Technical details and architecture
- [Monthly Workflow](docs/monthly_workflow.md) - Full pipeline documentation

## Support

For issues or questions, see the documentation files above.

To add new bank support, follow the pattern documented in `docs/bofa_integration_guide.md` under "Adding Support for Other Banks".
