# Enhanced Transaction Categorization & Filtering Plan

## Executive Summary

This document outlines a two-part feature enhancement for the SplitwiseImporter project:

1. **Transaction Filtering**: Automatically exclude payment/credit transactions from being posted to Splitwise
2. **ML-Enhanced Categorization**: Leverage historical Splitwise data (1,333+ expenses) to improve category prediction accuracy

## ✅ COMPLETED: Merchant Extraction Simplification (Jan 2026)

### What Was Implemented

The merchant name extraction system was completely overhauled and simplified:

- **Simplified extraction logic** - Reduced from 450+ lines to ~60 lines of maintainable code
- **Description field only** - Now extracts merchant names exclusively from the Description column (not Extended Details)
- **Canonical name support** - Uses `canonical_name` field from merchant lookup for consistent display
- **Unified review workflow** - Created `run_review_workflow.py` to chain generate → review → apply steps
- **Required arguments** - Made `generate_review_file.py` require explicit parameters (no defaults)

### Implementation Details

**New Approach:**
1. Parse Description field from CSV (not Extended Details)
2. Remove common prefixes (SP, GglPay, etc.)
3. Split on 2+ spaces, take first part
4. Remove phone numbers and state codes
5. Title case for readability
6. Use canonical_name from merchant lookup if available

**Files Modified:**
- `src/common/utils.py` - Simplified `clean_merchant_name()` function
- `src/import_statement/parse_statement.py` - Fixed column mapping to use Description
- `src/merchant_review/run_review_workflow.py` - NEW unified workflow orchestrator
- `src/merchant_review/generate_review_file.py` - Required arguments added

**Benefits:**
- More reliable extraction with fewer edge cases
- Easier to maintain and debug
- Better canonical name support
- Faster processing with simpler logic

---

## Current State Analysis

### Data Insights
- **Statement Transactions**: 707 total transactions in sample_statement.csv
- **Payment/Credit Transactions**: ~7 (6.7%) - these are refunds, credits, and autopay transactions
- **Historical Splitwise Data**: 1,333 categorized expenses across 36 unique categories
- **Top Categories**: Dining out (429), Groceries (161), General (122), Taxi (100), Gas/fuel (59)

### Current Categorization Logic
- Located in `src/utils.py::infer_category()`
- Uses regex pattern matching from `config/config.yaml`
- Falls back to "Uncategorized/General" when no match found
- Applies to both description and cleaned merchant name

### Existing Filtering
- Currently filters out transactions with:
  - Null/empty categories
  - "Fees & Adjustments" in description
  - Amount <= 0 (credits)

---

## Part 0: Description Cleaning & Normalization

### ✅ COMPLETED (Jan 2026)

This section described the original planned implementation for merchant name extraction from messy credit card descriptions. **The implementation has been completed with a simplified approach.**

**Instead of the complex multi-pattern approach originally planned, the final implementation uses:**

1. **Simple Description field parsing** - Extracts from Description column only (not Extended Details)
2. **Minimal pattern matching** - Removes common prefixes (SP, GglPay) and cleans up basic noise
3. **Canonical name lookup** - Uses merchant_category_lookup.json for consistent naming
4. **~60 lines of code** - Down from 450+ lines in the original complex approach

See `src/common/utils.py::clean_merchant_name()` for the current implementation.

**Status:** Implementation complete and tested with January 2026 transactions.

---
3. **URLs**: `help.uber.com`, `www.domain.com`
4. **Country codes**: `SG`, `CA`, `US` (at end of line)
5. **Extra whitespace**: Multiple spaces between words
6. **Location suffixes**: City/state codes after main merchant name
7. **Special characters**: `*`, `#`, `-` used as separators
8. **Incomplete words**: `TRANA` instead of "TRAVEL", `HEALSINGAPORE` (missing space)

### Implementation Strategy

#### Step 1: Create Description Cleaner Function

New function in `src/utils.py`:

```python
def clean_description_for_splitwise(description: str, config: Optional[Dict] = None) -> str:
    """Clean and normalize transaction descriptions for human readability in Splitwise.
    
    Args:
        description: Raw description from credit card statement
        config: Optional configuration for cleaning rules
        
    Returns:
        str: Clean, human-readable description suitable for Splitwise
        
    Examples:
        >>> clean_description_for_splitwise("GRAB*A-8PXHISMWWU9TASINGAPORE           SG")
        'Grab'
        >>> clean_description_for_splitwise("GglPay GUARDIAN HEALSINGAPORE           SG")
        'Guardian Health'
        >>> clean_description_for_splitwise("UBER EATS           help.uber.com       CA")
        'Uber Eats'
    """
    if not description or not isinstance(description, str):
        return description or ""
    
    config = config or {}
    cleaning_config = config.get("description_cleaning", {})
    
    # Start with original
    cleaned = description.strip()
    
    # 1. Remove transaction IDs (alphanumeric codes after * or -)
    cleaned = re.sub(r'[*-][A-Z0-9]{10,}', '', cleaned)
    
    # 2. Remove payment method prefixes
    payment_prefixes = [
        r'^GglPay\s+',
        r'^ApplePay\s+',
        r'^AMZN\s+Mktp\s+',
        r'^SQ\s*\*\s*',
        r'^Grab\*\s*',
        r'^PayPal\s*\*\s*',
    ]
    for prefix in payment_prefixes:
        cleaned = re.sub(prefix, '', cleaned, flags=re.IGNORECASE)
    
    # 3. Remove URLs
    cleaned = re.sub(r'https?://[^\s]+', '', cleaned)
    cleaned = re.sub(r'www\.[^\s]+', '', cleaned)
    cleaned = re.sub(r'\b[a-z]+\.[a-z]{2,}(?:/[^\s]*)?', '', cleaned, flags=re.IGNORECASE)
    
    # 4. Remove country codes at end (2-letter codes)
    cleaned = re.sub(r'\s+[A-Z]{2}$', '', cleaned)
    
    # 5. Clean up common location patterns
    # Remove city/state codes like "SINGAPORE", "BADUNG - BALI"
    location_patterns = [
        r'\s+SINGAPORE\s*\d*$',
        r'\s+BADUNG\s*-?\s*BALI$',
        r'\s+JAKARTA\s+[A-Z]{3}$',
        r',\s*[A-Z]{2}\s*\d*$',  # ", CA 94103"
    ]
    for pattern in location_patterns:
        cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE)
    
    # 6. Fix concatenated words (missing spaces)
    # Look for lowercase followed by uppercase
    cleaned = re.sub(r'([a-z])([A-Z])', r'\1 \2', cleaned)
    
    # 7. Collapse multiple spaces
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    
    # 8. Remove trailing special characters
    cleaned = re.sub(r'[*#\-\s]+$', '', cleaned)
    
    # 9. Apply custom merchant name mappings (from config)
    merchant_overrides = cleaning_config.get("merchant_overrides", {})
    cleaned_lower = cleaned.lower()
    for pattern, replacement in merchant_overrides.items():
        if re.search(pattern, cleaned_lower):
            cleaned = replacement
            break
    
    # 10. Title case for better readability
    # But preserve all-caps acronyms
    words = cleaned.split()
    formatted_words = []
    for word in words:
        if len(word) <= 3 and word.isupper():
            # Keep short all-caps words (e.g., "USA", "NYC")
            formatted_words.append(word)
        elif word.isupper() and len(word) > 3:
            # Title case long all-caps words
            formatted_words.append(word.title())
        else:
            # Keep mixed case as-is (likely proper nouns)
            formatted_words.append(word)
    cleaned = ' '.join(formatted_words)
    
    # 11. Fallback: if we cleaned too much, return a shortened original
    if not cleaned or len(cleaned) < 3:
        # Take first 50 chars of original, remove transaction IDs
        cleaned = description[:50].strip()
        cleaned = re.sub(r'[*-][A-Z0-9]{10,}', '', cleaned)
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    
    return cleaned
```

#### Step 2: Add Merchant-Specific Overrides

Add to `config/config.yaml`:

```yaml
description_cleaning:
  merchant_overrides:
    # Map common patterns to clean names
    'grab.*taxi': 'Grab'
    'uber\s*eats': 'Uber Eats'
    'uber.*trip': 'Uber'
    'guardian.*health': 'Guardian Health & Beauty'
    'lagardere.*travel': 'Lagardere Travel Retail'
    'hainan.*story': 'The Hainan Story Coffee'
    'marufuku.*ramen': 'Marufuku Ramen'
    'impiana.*vill': 'Impiana Private Villa'
    'whole.*foods': 'Whole Foods'
    'costco.*wholesale': 'Costco'
    
  # Patterns to preserve (don't clean these)
  preserve_patterns:
    - '^[A-Z][a-z]+\s[A-Z][a-z]+$'  # Already clean: "Whole Foods"
    - '^\w+\s*$'  # Single word: "Costco", "Uber"
```

#### Step 3: Integrate with Pipeline

**A. Update `pipeline.py` to clean descriptions and track both versions:**

```python
def process_statement(path, dry_run=True, ...):
    # ... existing code ...
    
    for idx, row in df.reset_index(drop=True).iterrows():
        date = row.get("date")
        raw_desc = row.get("description")
        amount = row.get("amount")
        
        # Clean the description
        from src.utils import clean_description_for_splitwise
        clean_desc = clean_description_for_splitwise(raw_desc)
        
        entry = {
            "date": date,
            "description_raw": raw_desc,        # Keep original for sheets
            "description_clean": clean_desc,     # Use for Splitwise
            "description": clean_desc,           # Default to clean version
            "amount": float(amount),
            # ... rest of fields
        }
        
        # Log when description changes significantly
        if raw_desc != clean_desc:
            LOG.info(
                f"Cleaned: '{raw_desc[:40]}...' → '{clean_desc}'"
            )
        
        # ... rest of processing logic ...
    
    # Create output DataFrame with both columns
    out_df = pd.DataFrame(results)
    
    # Reorder columns to show both descriptions
    column_order = [
        'date', 'description_clean', 'description_raw', 
        'amount', 'category_name', 'status', ...
    ]
    out_df = out_df[column_order]
    
    # Write to CSV and Google Sheets with both columns
    out_df.to_csv(out_path, index=False)
```

**B. Update `src/splitwise_client.py::add_expense_from_txn()` to use cleaned description:**

```python
def add_expense_from_txn(self, txn, cc_reference_id):
    """Add expense with cleaned description to Splitwise."""
    
    # Use cleaned description for Splitwise (already prepared in pipeline)
    expense_data = {
        'date': txn['date'],
        'amount': txn['amount'],
        'description': txn.get('description'),  # This is already cleaned
        # ... rest of the fields
    }
    
    # Optionally store raw description in notes for reference
    raw_desc = txn.get('description_raw')
    if raw_desc and raw_desc != txn.get('description'):
        expense_data['notes'] = f"Original: {raw_desc}"
    
    return self.add_expense(expense_data, cc_reference_id)
```

### Before/After Examples

**Google Sheets Output (with both columns):**

| Date | Description (Clean) | Description (Raw) | Amount | Category | Status |
|------|---------------------|-------------------|--------|----------|--------|
| 12/23/25 | Grab | `GRAB*A-8PXHISMWWU9TASINGAPORE           SG` | $26.72 | Taxi | added |
| 12/23/25 | Guardian Health | `GglPay GUARDIAN HEALSINGAPORE           SG` | $16.07 | Groceries | added |
| 12/23/25 | Uber Eats | `UBER EATS           help.uber.com       CA` | $63.42 | Dining out | added |
| 12/22/25 | Impiana Private Villa | `IMPIANA PRIVATE VILLBADUNG - BALI` | $41.97 | Hotel | cached |

**Splitwise Entry (uses clean description):**
- **Description**: "Grab"
- **Notes**: "Original: GRAB*A-8PXHISMWWU9TASINGAPORE           SG"
- **Amount**: $26.72
- **Category**: Taxi

**A. Unit Tests** in `tests/test_description_cleaning.py`:

```python
import pytest
from src.utils import clean_description_for_splitwise

def test_remove_transaction_ids():
    assert clean_description_for_splitwise(
        "GRAB*A-8PXHISMWWU9TASINGAPORE SG"
    ) == "Grab"

def test_remove_payment_prefixes():
    assert clean_description_for_splitwise(
        "GglPay GUARDIAN HEALSINGAPORE SG"
    ) == "Guardian Health"

def test_remove_urls():
    assert clean_description_for_splitwise(
        "UBER EATS           help.uber.com       CA"
    ) == "Uber Eats"

def test_preserve_clean_descriptions():
    # Already clean descriptions should remain unchanged
    assert clean_description_for_splitwise("Whole Foods") == "Whole Foods"
    assert clean_description_for_splitwise("Costco") == "Costco"
```

**B. Integration Testing** - Review Google Sheets output:

After running pipeline, open the processed CSV or Google Sheet and verify:
1. **description_clean** column has readable merchant names
2. **description_raw** column preserves original for audit
3. Both columns are present and aligned correctly
4. No essential information lost in cleaning

**C. Manual Validation Checklist:**
- [ ] Review first 50 cleaned descriptions
- [ ] Check for over-cleaning (too much info removed)
- [ ] Check for under-cleaning (noise still present)
- [ ] Verify merchant consistency (all Grab rides → "Grab")
- [ ] Compare Splitwise entries - are they readable? # Already clean descriptions should remain unchanged
    assert clean_description_for_splitwise("Whole Foods") == "Whole Foods"
    assert clean_description_for_splitwise("Costco") == "Costco"
```

### Integration Testing

Run on actual statement data:

```python
# In pipeline.py, add logging to compare before/after
df = parse_statement(path)
for idx, row in df.iterrows():
    raw = row['description']
    cleaned = clean_description_for_splitwise(raw)
    if raw != cleaned:
        LOG.info(f"Cleaned: '{raw[:40]}...' → '{cleaned}'")
```

### Expected Outcomes

- **Readability**: 90%+ of Splitwise entries are immediately recognizable merchant names
- **Consistency**: Similar merchants have consistent naming (all Grab rides show as "Grab")
- **Audit Trail**: 100% of raw descriptions preserved in Google Sheets for review
- **Manual Review**: <5% of descriptions need manual editing in Splitwise

### Workflow Benefits

**For Debugging/Auditing:**
1. Open processed CSV or Google Sheet
2. Compare `description_clean` vs `description_raw` columns side-by-side
3. Identify any over-cleaned or problematic entries
4. Add patterns to `config.yaml` to fix edge cases
5. Re-run pipeline to verify improvements

**For Splitwise Posting:**
- Clean descriptions automatically used when creating expenses
- Raw descriptions stored in Splitwise notes field (optional)
- Easy to understand what was actually purchased

### Notes

- Raw descriptions preserved in TWO places: Google Sheets column AND Splitwise notes
- Consider adding a `--skip-cleaning` flag for debugging/testing
- Review cleaned descriptions in sheets after each run to refine patterns
- Can iterate on cleaning rules without losing original data
- Review cleaned descriptions periodically to add new patterns

---

## Part 1: Payment/Credit Transaction Filtering

### Problem
Payment and credit transactions (autopay, refunds, credits) add noise to Splitwise and don't help with budget tracking.

### Detection Patterns

Based on analysis of `sample_statement.csv`, payment/credit transactions have these characteristics:

1. **Negative amounts** (already filtered by `parse_statement.py`)
2. **Keyword patterns in description**:
   - "AUTOPAY PAYMENT"
   - "THANK YOU"
   - "Credit" (when standalone or in "Amex Offer Credit", "Entertainment Credit")
   - "PAYMENT -"
3. **Category field patterns**:
   - "Fees & Adjustments" (already filtered)
   - Empty/null categories

### Implementation Strategy

#### Option A: Enhance Existing Filter (Recommended)
Add to `src/parse_statement.py::parse_csv()` after existing filters:

```python
# Filter out payment/credit transactions
payment_patterns = [
    r'\bAUTOPAY\b',
    r'\bPAYMENT\s*-\s*THANK\s*YOU\b',
    r'\bAmex\s+Offer\s+Credit\b',
    r'^\s*Credit\s*$',  # Standalone "Credit"
    r'\b(Entertainment|Digital)\s+Credit\b',
]

before_payment_filter = len(out)
payment_filter = out["description"].str.contains(
    '|'.join(payment_patterns), case=False, na=False, regex=True
)
out = out[~payment_filter]
payment_filtered = before_payment_filter - len(out)

if payment_filtered > 0:
    LOG.info("Filtered out %d payment/credit transactions", payment_filtered)
```

#### Option B: Configurable Filtering
Move patterns to `config/config.yaml`:

```yaml
transaction_filtering:
  exclude_patterns:
    - pattern: '\bAUTOPAY\b'
      reason: 'Autopay transaction'
    - pattern: '\bPAYMENT\s*-\s*THANK\s*YOU\b'
      reason: 'Payment acknowledgment'
    - pattern: '\bAmex\s+Offer\s+Credit\b'
      reason: 'Promotional credit'
  exclude_categories:
    - 'Fees & Adjustments'
  exclude_negative_amounts: true
```

**Recommendation**: Start with Option A (hardcoded patterns), move to Option B if patterns need frequent updates.

---

## Part 2: ML-Enhanced Categorization

### Problem
Current regex-based categorization has limitations:
- Requires manual pattern maintenance
- Limited context understanding
- High rate of "Uncategorized" results
- Cannot learn from past categorization decisions

### Opportunity
With 1,333+ historical Splitwise expenses already categorized, we can build a data-driven categorization model.

### Proposed Architecture

#### Phase 1: Feature Engineering & Simple Classifier

**Features to Extract from Transactions:**
1. **Merchant name** (cleaned)
2. **Description keywords** (TF-IDF or bag-of-words)
3. **Transaction amount** (bucketed: <$10, $10-50, $50-100, $100+)
4. **Day of week** (weekday vs weekend patterns)
5. **Time of transaction** (if available)
6. **Historical category for same merchant** (lookup cache)

**Training Data:**
- Source: `data/processed/splitwise_expenses.csv`
- Features: description, amount, category
- Target: category (36 classes)
- Training set: 80% (1,066 transactions)
- Validation set: 20% (267 transactions)

**Model Options (in order of complexity):**

1. **Merchant Lookup Table** (Simplest - MVP)
   - Extract unique merchant names from historical data
   - Create direct merchant → category mapping
   - Confidence: "high" for exact matches, "low" for new merchants
   - Expected coverage: 40-60% of transactions

2. **TF-IDF + Logistic Regression** (Recommended for MVP)
   - Vectorize description text using TF-IDF
   - Add amount as additional feature
   - Train multi-class logistic regression
   - Fast inference, interpretable, good baseline
   - Expected accuracy: 70-85%

3. **Gradient Boosting (XGBoost/LightGBM)** (Future enhancement)
   - Better for complex patterns
   - Can handle feature interactions
   - Expected accuracy: 80-90%

4. **Fine-tuned Language Model** (Future consideration)
   - Best for semantic understanding
   - Resource intensive
   - Overkill for this use case

### Implementation Plan

#### Step 1: Create Training Data Pipeline

New file: `src/training/prepare_training_data.py`

```python
def prepare_training_data():
    """Load and prepare historical Splitwise expenses for training."""
    df = pd.read_csv('data/processed/splitwise_expenses.csv')
    
    # Clean and engineer features
    df['merchant_clean'] = df['description'].apply(clean_merchant_name)
    df['amount_bucket'] = pd.cut(df['amount'], 
                                   bins=[0, 10, 50, 100, float('inf')],
                                   labels=['small', 'medium', 'large', 'xlarge'])
    
    # Filter valid categories (exclude "General" as it's too broad)
    df = df[df['category'] != 'General']
    
    return df
```

#### Step 2: Build Merchant Lookup (MVP)

New file: `src/training/build_merchant_lookup.py`

```python
def build_merchant_lookup():
    """Create a merchant → category mapping from historical data."""
    df = prepare_training_data()
    
    # Group by merchant and find most common category
    lookup = {}
    for merchant in df['merchant_clean'].unique():
        merchant_data = df[df['merchant_clean'] == merchant]
        if len(merchant_data) >= 2:  # Require at least 2 occurrences
            category = merchant_data['category'].mode()[0]
            count = len(merchant_data)
            lookup[merchant.lower()] = {
                'category': category,
                'count': count,
                'confidence': min(count / 5.0, 1.0)  # Cap at 1.0
            }
    
    # Save to JSON
    with open('data/merchant_category_lookup.json', 'w') as f:
        json.dump(lookup, f, indent=2)
    
    return lookup
```

#### Step 3: Train ML Model

New file: `src/training/train_categorizer.py`

```python
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.model_selection import train_test_split
import joblib

def train_model():
    """Train a logistic regression model for category prediction."""
    df = prepare_training_data()
    
    # Split data
    X_train, X_test, y_train, y_test = train_test_split(
        df['description'], df['category'], 
        test_size=0.2, random_state=42, stratify=df['category']
    )
    
    # Create pipeline
    model = Pipeline([
        ('tfidf', TfidfVectorizer(max_features=500, ngram_range=(1, 2))),
        ('clf', LogisticRegression(max_iter=1000, class_weight='balanced'))
    ])
    
    # Train
    model.fit(X_train, y_train)
    
    # Evaluate
    train_acc = model.score(X_train, y_train)
    test_acc = model.score(X_test, y_test)
    
    print(f"Training accuracy: {train_acc:.2%}")
    print(f"Test accuracy: {test_acc:.2%}")
    
    # Save model
    joblib.dump(model, 'data/category_model.pkl')
    
    return model
```

#### Step 4: Enhanced Category Inference

Update `src/utils.py::infer_category()`:

```python
def infer_category(transaction: Dict[str, Any]) -> Dict[str, Any]:
    """Infer category using hybrid approach: lookup → ML → regex → default."""
    
    merchant = clean_merchant_name(
        transaction.get("merchant") or transaction.get("description", "")
    )
    description = (transaction.get("description") or "").lower()
    
    # STEP 1: Try merchant lookup (highest confidence)
    lookup = _load_merchant_lookup()
    merchant_key = merchant.lower()
    if merchant_key in lookup:
        result = lookup[merchant_key]
        LOG.info(f"Merchant lookup match: {merchant} → {result['category']}")
        return {
            "category_name": result['category'],
            "confidence": f"high_{result['confidence']:.2f}",
            "method": "merchant_lookup",
            "matched_merchant": merchant
        }
    
    # STEP 2: Try ML model (medium confidence)
    try:
        model = _load_ml_model()
        if model:
            category = model.predict([description])[0]
            proba = model.predict_proba([description])[0].max()
            if proba > 0.6:  # Confidence threshold
                LOG.info(f"ML prediction: {description} → {category} ({proba:.2f})")
                return {
                    "category_name": category,
                    "confidence": f"medium_{proba:.2f}",
                    "method": "ml_model",
                    "probability": proba
                }
    except Exception as e:
        LOG.warning(f"ML model prediction failed: {e}")
    
    # STEP 3: Try regex patterns (existing logic)
    category_config = _load_category_config()
    for category in category_config.get("patterns", []):
        for subcategory in category.get("subcategories", []):
            for pattern in subcategory.get("patterns", []):
                if re.search(pattern, description, re.IGNORECASE) or \
                   re.search(pattern, merchant.lower(), re.IGNORECASE):
                    LOG.info(f"Regex match: {pattern} → {category['name']}/{subcategory['name']}")
                    return {
                        "category_name": subcategory['name'],
                        "confidence": "low",
                        "method": "regex_pattern",
                        "matched_pattern": pattern
                    }
    
    # STEP 4: Default (lowest confidence)
    LOG.info(f"No match found, using default category")
    return {
        "category_name": "General",
        "confidence": "very_low",
        "method": "default"
    }
```

### Evaluation Metrics

Track the following metrics in `pipeline.py`:

1. **Categorization Coverage**: % of transactions with category != "General"
2. **Confidence Distribution**: Breakdown by confidence level (high/medium/low)
3. **Method Usage**: Count of merchant_lookup vs ML vs regex vs default
4. **Manual Review Queue**: Transactions with confidence < threshold

### Integration with pipeline.py

Update the processing loop in [pipeline.py](pipeline.py:41-150):

```python
# After inferring category
entry.update({
    "category_name": category_info.get("category_name"),
    "confidence": category_info.get("confidence"),
    "method": category_info.get("method"),
    "matched_pattern": category_info.get("matched_pattern"),
})
pipeline.py` (integrate cleaning, add dual columns)
  - Update: `src/splitwise_client.py` (use cleaned description)
  - Update: `config/config.yaml` (add merchant overrides)
  - New: `tests/test_description_cleaning.py`
- **Testing**: 
  - Unit tests for cleaning function
  - Manual review of processed CSV with both columns
  - Verify Google Sheets has both `description_clean` and `description_raw`
- **Priority**: Medium - implement alongside other features for comprehensive testing
- **Note**: Dual-column approach allows safe testing without losing datan {cc_reference_id}: "
        f"{desc} → {category_info.get('category_name')}"
    )
```

---

## Implementation Roadmap

### Phase 0: Description Cleaning (Foundation) 
- **Effort**: 4-6 hours
- **Files**: 
  - Update: `src/utils.py` (add `clean_description_for_splitwise()`)
  - Update: `src/splitwise_client.py` (integrate cleaning)
  - Update: `config/config.yaml` (add merchant overrides)
  - New: `tests/test_description_cleaning.py`
- **Testing**: Unit tests + manual review of 50 cleaned descriptions
- **Priority**: High - improves UX immediately

### Phase 1: Payment/Credit Filtering (Immediate)
- **Effort**: 2-4 hours
- **Files**: `src/parse_statement.py`
- **Testing**: Run pipeline with dry-run, verify 7 payment transactions filtered
- **Priority**: High - prevents bad data from entering Splitwise

### Phase 2: Merchant Lookup MVP (Quick Win)
- **Effort**: 4-6 hours
- **Files**: 
  - New: `src/training/build_merchant_lookup.py`
  - Update: `src/utils.py` (integrate lookup in `infer_category()`)
- **Testing**: Measure coverage on sample_statement.csv
- **Priority**: Medium - improves accuracy with minimal effort

### Phase 3: ML Model Training (Enhanced)
- **Effort**: 8-12 hours
- **Files**: 
  - New: `src/training/train_categorizer.py`
  - New: `src/training/prepare_training_data.py`
  - Update: `src/utils.py` (integrate ML model)
- **Dependencies**: scikit-learn (already in requirements.txt)
- **Testing**: Cross-validation, accuracy metrics, confusion matrix
- **Priority**: Medium - highest accuracy gains

### Phase 4: Monitoring & Refinement (Ongoing)
- **Effort**: 2-4 hours/month
- **Tasks**: 
  - Review low-confidence predictions
  - Add new merchant mappings and cleaning patterns
  - Retrain model with new data
  - Audit cleaned descriptions vs raw
- **Priority**: Low - maintenance

---

## Configuration Changes

### Add to config/config.yaml:

```yaml
# Description cleaning
description_cleaning:
  enabled: true
  preserve_original_in_notes: true  # Store raw description in Splitwise notes field
  
  merchant_overrides:
    'grab.*taxi': 'Grab'
    'uber\s*eats': 'Uber Eats'
    'uber.*trip': 'Uber'
    'guardian.*health': 'Guardian Health & Beauty'
    'lagardere.*travel': 'Lagardere Travel Retail'
    'hainan.*story': 'The Hainan Story Coffee'
    'marufuku.*ramen': 'Marufuku Ramen'
    'impiana.*vill': 'Impiana Private Villa'
    'whole.*foods': 'Whole Foods'
    'costco.*wholesale': 'Costco'
  
  preserve_patterns:
    - '^[A-Z][a-z]+\s[A-Z][a-z]+$'  # Already clean two-word names
    - '^\w+$'  # Single clean word

# Transaction filtering
transaction_filtering:
  exclude_payment_patterns:
    - '\bAUTOPAY\b'
    - '\bPAYMENT\s*-\s*THANK\s*YOU\b'
    - '\bAmex\s+Offer\s+Credit\b'
    - '^\s*Credit\s*$'
  exclude_categories:
    - 'Fees & Adjustments'
  exclude_negative_amounts: true

# ML categorization
ml_categorization:
  enabled: true
  model_path: 'data/category_model.pkl'
  merchant_lookup_path: 'data/merchant_category_lookup.json'
  confidence_threshold: 0.6  # Min probability for ML predictions
  min_merchant_count: 2      # Min occurrences for lookup
  retrain_threshold_days: 90 # Retrain model every N days
```

---

## Expected Outcomes

### Description Cleaning
- **Before**: `GRAB*A-8PXHISMWWU9TASINGAPORE           SG` (messy, technical)
- **After**: `Grab` (clean, human-readable)
- **Impact**: 90%+ of descriptions become immediately recognizable
- **Benefit**: Better Splitwise UX, easier manual review, consistent naming

### Filtering
- **Before**: 707 transactions → 7 invalid payments/credits might be posted
- **After**: 700 valid transactions → 0 invalid transactions posted
- **Impact**: 100% elimination of payment/credit noise

### Categorization Accuracy

| Method | Coverage | Accuracy | Confidence |
|--------|----------|----------|------------|
| Current (regex only) | ~30-40% | ~70% | Low |
| + Merchant Lookup | ~60-70% | ~85% | High |
| + ML Model | ~85-95% | ~80% | Medium |
| Combined (Hybrid) | **~95%** | **~85%** | Varied |

### Uncategorized Rate
- **Before**: Estimated 30-40% go to "General/Uncategorized"
- **After**: Expected <10% go to "General/Uncategorized"

### Overall Quality Improvement
- **Readability**: 10/10 vs 4/10 (raw statements)
- **Accuracy**: 85% vs 70% (current regex)
- **Coverage**: 95% vs 60% (current approach)
- **User Satisfaction**: Minimal manual cleanup needed

---

## Future Enhancements

1. **Active Learning**: Flag low-confidence predictions for manual review, use feedback to retrain
2. **Temporal Patterns**: Detect recurring expenses (subscriptions) and auto-categorize
3. **Amount-based Rules**: "Costco + $150+ → Groceries" vs "Costco + $30 → Gas/fuel"
4. **Category Suggestions**: Show top 3 likely categories with probabilities in UI
5. **A/B Testing**: Compare regex vs ML performance over time
6. **Integration with Budget Tracking**: Feed categorized expenses directly into budget vs actual reports

---

## Dependencies

### New Python Packages (if needed):
```txt
scikit-learn>=1.3.0  # Already in requirements.txt
joblib>=1.3.0        # Usually bundled with scikit-learn
```

### New Data Files:
- `data/merchant_category_lookup.json` - Generated by training script
- `data/category_model.pkl` - Trained ML model
- `data/training_metrics.json` - Model evaluation results

---

## Testing Strategy

1. **Unit Tests**:
   - Test payment filtering patterns
   - Test merchant lookup with known merchants
   - Test ML model inference

2. **Integration Tests**:
   - Run pipeline on sample_statement.csv
   - Compare output before/after
   - Verify no payments posted

3. **Validation**:
   - Manual review of 50 random categorizations
   - Compare against Splitwise categories
   - Calculate precision/recall

---
Description Cleaning**:
- >90% of descriptions are human-readable without manual editing
- Zero loss of essential merchant/transaction information
- <5% of cleaned descriptions flagged for manual review
- Consistent naming across similar merchants

✅ **Payment Filtering**:
- Zero payment/credit transactions posted to Splitwise
- <1% false positives (valid transactions filtered)

✅ **Categorization**:
- <10% transactions categorized as "General/Uncategorized"
- >80% accuracy on manual validation sample
- >90% coverage (non-default category assigned)

✅ **Maintainability**:
- Model retraining script runs in <5 minutes
- Clear logging for debugging miscategorizations and cleaning issues
- Configuration-driven for easy pattern updates
- Original raw data preserved for audit trail
✅ **Payment Filtering**:
- Zero payment/credit transactions posted to Splitwise
- < 1% false positives (valid transactions filtered)

✅ **Categorization**:
- <10% transactions categorized as "General/Uncategorized"
- >80% accuracy on manual validation sample
- >90% coverage (non-default category assigned)

✅ **Maintainability**:
- Model retraining script runs in <5 minutes
- Clear logging for debugging miscategorizations
- Configuration-driven for easy pattern updates
