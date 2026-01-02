# 🎯 Merchant Review - Quick Reference Card

## Current Status
- **385** transactions ready to review
- **266** unique merchants
- **0** reviewed so far

## Quick Commands

```bash
# Preview what needs review
./review.sh preview 5

# Start reviewing (20 at a time)
./review.sh start --batch 20

# Check progress
./review.sh stats

# Apply corrections to config
./review.sh apply

# Re-run pipeline with improvements
python src/pipeline.py --statement data/raw/amex2025.csv
```

## During Review: Actions

| Key | Action | When to Use |
|-----|--------|-------------|
| **a** | Approve | Merchant name & category are correct |
| **c** | Correct | Need to fix merchant name or category |
| **s** | Skip | Not sure, review later |
| **q** | Quit | Save progress and exit |
| **h** | Help | Show instructions |

## Example Session

```bash
# 1. Preview merchants
./review.sh preview 5

# 2. Review 20 merchants
./review.sh start --batch 20
   # Press 'a' to approve correct ones
   # Press 'c' to correct wrong ones
   # Press 'q' when done

# 3. Check what you did
./review.sh stats

# 4. Preview changes
./review.sh apply --dry-run

# 5. Apply changes
./review.sh apply

# 6. Re-run pipeline
python src/pipeline.py --statement data/raw/amex2025.csv
```

## Naming Best Practices

✅ **Good:**
- "Starbucks"
- "Target"  
- "Uber"
- "Google Fi"

❌ **Avoid:**
- "STARBUCKS COFFEE"
- "Target #2341 San Francisco"
- "Uber Technologies Inc."
- "GOOGLE *FI T43VHB"

## Common Categories

| Category | Examples |
|----------|----------|
| **Food and drink** | Restaurants, grocery stores, Starbucks |
| **Transportation** | Uber, Lyft, gas stations, parking |
| **Utilities** | Phone, internet, Hulu, Netflix |
| **Life** | Healthcare, insurance, gym |
| **Shopping** | Amazon, clothing, electronics |
| **Entertainment** | Movies, concerts, hobbies |
| **General** | Miscellaneous |

## Files Reference

| File | What It Does |
|------|--------------|
| `merchant_names_for_review.csv` | Merchants waiting for your review |
| `merchant_review_feedback.json` | Your corrections (auto-saved) |
| `done_merchant_names_for_review.csv` | Already reviewed (archive) |
| `merchant_category_lookup.json` | Master config (updated by apply) |

## Tips

💡 **Review in batches** - Do 20-50 at a time, not all 266 at once

💡 **Auto-save** - Progress saved every 10 transactions automatically

💡 **Resume anytime** - Quit with 'q' and continue later with:
```bash
./review.sh continue 50  # Continue from transaction 50
```

💡 **High-frequency first** - Common merchants appear multiple times, review them for biggest impact

💡 **Consistent names** - Use Title Case and remove locations/IDs

## Need Help?

- Full guide: [docs/merchant_review_workflow.md](merchant_review_workflow.md)
- Demo walkthrough: [docs/review_demo.md](review_demo.md)
- Summary: [docs/merchant_review_summary.md](merchant_review_summary.md)

---

**Ready to start? Run:** `./review.sh preview 5`
