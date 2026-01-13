📘 Project Summary — Splitwise + CSV Budget & Expense Tracker
🎯 Goal of the Project

Build a Python-based workflow that:

Processes CSV credit-card/bank statements (no PDF parsing).

Identifies which expenses belong in Splitwise, and automatically adds them to Splitwise using its API.

Pulls all Splitwise expenses (yours + shared) into a structured dataframe.

Uses this data to track budget vs. actuals for the year.

Writes summary data into a Google Sheet you already use for tracking investments & finances.

Avoids complexity early — no Plaid integration for now.

Should run locally on a Chromebook using Pycharm or a Jupyter environment.

🧩 Key Components
1. CSV Statement Processing

You will download monthly statements as .csv from your unlinked credit card.

Script requirements:

Parse CSV rows.

Normalize fields (date, amount, category, merchant).

Detect which transactions need to be added to Splitwise.

Avoid duplicates—track previously inserted items.

2. Splitwise API Integration

Using the Splitwise v3 OAuth API.

You will manually generate an API key via:

https://secure.splitwise.com/apps

Create a Personal Access Token (consumer key + secret).

Script can:

Add expenses.

Fetch all Splitwise activities.

Normalize them into a pandas DataFrame for downstream use.

3. Budget vs Actual Tracking

You maintain yearly budget buckets (e.g., Food, Gas, Insurance).

Your script should:

Load a YAML/JSON budget file (e.g., budget_2025.json).

Load Splitwise expenses + your CSV bank expenses.

Categorize transactions.

Summarize monthly and yearly totals.

Output a consolidated dataframe.

4. Google Sheets Sync

Using gspread or Google Sheets API v4.

Write:

Monthly spending totals

Category breakdown

Cumulative budget vs actual charts

Sheet will update from local script execution.

5. Project Structure

Current structure (updated Jan 12, 2026 - Phase 2 Complete):

SplitwiseImporter/
├── src/
│   ├── database/               # Local SQLite database layer (Phase 1)
│   │   ├── __init__.py
│   │   ├── schema.py           # Table definitions
│   │   ├── models.py           # Transaction & ImportLog dataclasses
│   │   └── db_manager.py       # DatabaseManager with CRUD operations
│   ├── db_sync/                # Unified sync utilities (Phase 1 & 2)
│   │   ├── __init__.py
│   │   └── sync_from_splitwise.py # Sync DB with Splitwise (insert/update/delete)
│   ├── import_statement/       # CSV statement parsing and import pipeline
│   │   ├── pipeline.py         # Main ETL orchestrator (Phase 2: Splitwise → DB)
│   │   ├── parse_statement.py  # CSV parsing
│   │   └── categorization.py   # Transaction categorization
│   ├── export/
│   │   ├── splitwise_export.py # Unified export (Splitwise API or database)
│   │   └── monthly_export_pipeline.py # Automated monthly workflow (import→sync→export)
│   ├── update/
│   │   ├── update_self_expenses.py # Fix self-expense splits
│   │   └── bulk_update_categories.py # Bulk category updates
│   ├── merchant_review/        # Interactive merchant review workflow
│   │   ├── review_merchants.py
│   │   └── apply_review_feedback.py
│   ├── common/                 # Shared utilities
│   │   ├── splitwise_client.py # Splitwise API wrapper
│   │   ├── sheets_sync.py      # Google Sheets integration
│   │   └── utils.py
│   └── constants/              # Configuration constants
├── config/
│   ├── .env                    # API keys & default settings
│   ├── merchant_category_lookup.json  # 216+ merchant mappings
│   ├── amex_category_mapping.json
│   └── gsheets_authentication.json
├── data/
│   ├── raw/                    # Raw CSV statements
│   ├── processed/              # Processed outputs
│   └── transactions.db         # SQLite database (1,672 transactions)
└── docs/
    ├── database_sync_guide.md  # Complete database & sync guide (Phase 1 & 2)
    └── ...

**Removed Files (Phase 2 cleanup):**
- review.sh (merchant review complete with 216+ merchants)
- data/splitwise_cache.json (replaced with database duplicate detection)
- src/constants/config.py:CACHE_PATH (no longer needed)

🤖 AI Workflow
You are using:

Windsurf (Codeium) with free SWE-1 model.

Also optionally Claude Haiku 4.5 or GPT-4.1 as your free assistant depending on the editor.

Goal is to feed Copilot/Windsurf the context so it can help you write the code.

This summary provides everything Copilot needs.

📝 Current Status (What Has Been Completed)

✅ **Phase 1: Local Database as Source of Truth (Complete - Jan 2026)**
- SQLite database (`data/transactions.db`) - Canonical source for all transactions
- Database schema with comprehensive transaction model (deduplication, source tracking, sync status)
- DatabaseManager API for CRUD operations
- Direct Splitwise API migration tool (1,654 transactions imported: 2025 + 2026)
- Google Sheets positioned as "view cache" not primary ledger
- Import audit trail with import_log table

✅ **Phase 2: Splitwise-First Import Pipeline (Complete - Jan 12, 2026)**
- Import pipeline saves to database after successful Splitwise API creation
- Splitwise is source of truth - database reflects Splitwise state
- Sync script (`src/db_sync/sync_from_splitwise.py`) to pull updates/deletes from Splitwise
- DatabaseManager extended with sync methods (update_transaction_from_splitwise, mark_deleted_by_splitwise_id)
- Manual Splitwise edits (splits, deletes, categories) can be synced back to database
- Workflow: CSV → Splitwise → Database → [manual edits in Splitwise] → Sync back to DB
- JSON cache removed - pure database-driven duplicate detection by cc_reference_id
- Category inference runs for all transactions (including duplicates) for proper sheet reporting
- Fixed duplicate detection to only check cc_reference_id (allows legitimate duplicate transactions)

✅ **Core Infrastructure**
- Set up development environment on Chromebook using Linux/PyCharm
- Created modular project structure with `src/` subdirectories
- Implemented SplitwiseClient wrapper with API integration, caching, and deleted expense filtering
- Built Google Sheets sync functionality with gspread
- CSV parsing and normalization for credit card statements

✅ **Import Pipeline**
- Full ETL pipeline for importing credit card statements to Splitwise
- Batch processing support (`--limit`, `--offset`, `--append`)
- Merchant filtering for selective reprocessing (`--merchant-filter`)
- Duplicate detection using local cache and remote API checks
- Auto-categorization using merchant lookup with 216+ merchants configured
- Interactive merchant review workflow for improving extraction accuracy

✅ **Export & Sync**
- Export Splitwise expenses to Google Sheets with filtering
- Deleted transaction filtering (DELETED_AT_FIELD constant)
- Payment and settlement filtering (excludes "Settle all balances", "Payment")
- Zero-participation filtering (excludes expenses where user not involved)
- Date formatting fixed (removed UTC timezone conversion to prevent date shifts)
- Support for both append and overwrite modes

✅ **Bulk Updates**
- Bulk category updates script (src/update/bulk_update_categories.py) for updating expenses by merchant/category
- Self-expense split fixing (50/50 → 100% owed) via update_self_expenses.py
- Category reassignment workflows (SpotHero → Parking, Amazon → Household supplies, Costco → Household supplies)
- Support for predefined subcategory names (parking, household_supplies, medical, etc.)

✅ **Configuration & Data**
- Merchant category lookup with 216+ merchants
- Category mappings: Transportation/Parking, Home/Household supplies, etc.
- 2025 data fully imported (1,609 Splitwise expenses in database)
- 2026 data imported (45 Splitwise expenses in database)
- Now tracking 2026 expenses in new "Expenses 2026" sheet tab

**Recent Session Changes (Jan 12, 2026 - Phase 3 Complete)**
- ✅ Created unified export script (splitwise_export.py) supporting both Splitwise API and database sources
- ✅ Database export includes all 12 columns matching Splitwise format
- ✅ Payment transactions filtered from sheets (remain in database)
- ✅ Details column simplified (only cc_reference_id or blank)
- ✅ Removed Friends Split column (redundant with Participant Names)
- ✅ Updated sync script to populate payment information from Splitwise API
- ✅ Created monthly_export_pipeline.py to automate full workflow
- ✅ Added dry-run support to all export/sync scripts
- ✅ Converted hardcoded strings to constants throughout codebase
- ✅ Updated documentation with automated pipeline examples

✅ **Phase 3: Google Sheets Export & Monthly Pipeline (Complete - Jan 12, 2026)**
- Unified export script supports both Splitwise API and database sources
- Database export with full 12-column format matching Splitwise API
- Payment transaction filtering (excluded from sheets but kept in DB)
- Simplified details column (only cc_reference_id or blank)
- Sync script updates payment information from Splitwise API
- **Automated monthly pipeline** - Single command runs import → sync → export
- Column order: Date, Amount, Category, Description, Details, Split Type, Participant Names, My Paid, My Owed, My Net, Splitwise ID, Transaction Fingerprint

🚀 Next Steps - Phase 4: Budget Tracking & Analysis

**Analysis Layer:**
- Keep raw transaction tabs (2024, 2025, 2026) in sheets
- Create separate aggregate tabs (monthly_summary, category_rollups, budget_tracking)
- Move rolling averages off transaction tabs

**Append-only Export:**
- Database → Sheets (only unwritten rows) → mark as written_to_sheet=True
- Avoid full overwrite for historical months

See `docs/database_sync_guide.md` for Phase 1 & 2 architecture details.

**Workflow - Automated Monthly Pipeline (Recommended)**

The automated pipeline runs all three steps in sequence:

```bash
# Full pipeline: Import new statement → Sync DB → Export to sheets
export PYTHONPATH=/home/balaji94/PycharmProjects/SplitwiseImporter
python src/export/monthly_export_pipeline.py \
  --statement data/raw/jan2026.csv \
  --year 2026 \
  --start-date 2026-01-01 \
  --end-date 2026-01-31

# Sync and export only (no new statement)
python src/export/monthly_export_pipeline.py --year 2026 --sync-only

# Dry run to preview all changes
python src/export/monthly_export_pipeline.py \
  --statement data/raw/jan2026.csv \
  --year 2026 \
  --dry-run
```

**Individual Commands (for troubleshooting):**

If you need to run steps separately:

1. Import statement to Splitwise:
```bash
python src/import_statement/pipeline.py \
  --statement data/raw/jan2026.csv \
  --start-date 2026-01-01 \
  --end-date 2026-01-31
```

2. Sync database with Splitwise (updates payment info):
```bash
python src/db_sync/sync_from_splitwise.py --year 2026 --live
```

3. Export to Google Sheets:
```bash
python src/export/splitwise_export.py \
  --source database \
  --year 2026 \
  --worksheet "Expenses 2026" \
  --overwrite
```

**Why this order:**
- Splitwise is the source of truth (manual edits happen there)
- Database reflects current Splitwise state via sync
- Sync script populates payment information (Paid/Owe/With) from Splitwise API
- Must sync after importing statements to get complete transaction data
- Export uses database as source (faster, offline-capable, consistent)

**Key Features:**
- Payment transactions filtered from sheets (remain in DB)
- Details column shows only cc_reference_id
- 12 columns: Date, Amount, Category, Description, Details, Split Type, Participant Names, My Paid, My Owed, My Net, Splitwise ID, Fingerprint
- Dry run mode available for all scripts
- Overwrite mode for full refresh

See [docs/monthly_workflow.md](docs/monthly_workflow.md) for complete workflow guide with troubleshooting tips.

**Phase 2 (Complete): Splitwise-First Pipeline Flow**
```bash
source .venv/bin/activate
export PYTHONPATH=/home/balaji94/PycharmProjects/SplitwiseImporter

python src/import_statement/pipeline.py \
  --statement data/raw/jan2026.csv \
  --start-date 2026-01-01 \
  --end-date 2026-01-31
```

**Sync with Splitwise (handles inserts/updates/deletes):**
```bash
# Dry run first (see what would change)
python src/db_sync/sync_from_splitwise.py --year 2026 --dry-run --verbose

# Apply changes (inserts new, updates existing, marks deleted)
python src/db_sync/sync_from_splitwise.py --year 2026 --live

# Initial migration for historical data (same command)
python src/db_sync/sync_from_splitwise.py --year 2025 --live
```

**Why this flow:**
- Splitwise is the source of truth (manual edits happen there)
- Database reflects current Splitwise state
- Unified sync script handles:
  - **New expenses**: Insert into DB (migration behavior)
  - **Updated expenses**: Update amount, description, category, etc.
  - **Deleted expenses**: Mark as deleted in DB
- Can re-sync anytime to get latest Splitwise state
- Same tool for both initial migration and ongoing sync
- Duplicate detection: cc_reference_id only (allows legitimate duplicates like 2 plane tickets)

# Initial migration for historical data (same command)
python src/db_sync/sync_from_splitwise.py --year 2025 --live
```

**Why this flow:**
- Splitwise is the source of truth (manual edits happen there)
- Database reflects current Splitwise state
- Unified sync script handles:
  - **New expenses**: Insert into DB (migration behavior)
  - **Updated expenses**: Update amount, description, category, etc.
  - **Deleted expenses**: Mark as deleted in DB
- Can re-sync anytime to get latest Splitwise state
- Same tool for both initial migration and ongoing sync

**Phase 3 (Next): Sheets Export**

The export pipeline will be updated to:

1. **Export Database to Sheets** - Write only unwritten transactions
2. **Mark as written** - Track `written_to_sheet` flag  
3. **Append-only sheets** - Never overwrite, only append new rows
4. **Summary tabs** - Monthly rollups, budget tracking

**Current order for data integrity (until Phase 3):**

1. **Import statements to Splitwise** - Parse CSV and add transactions using pipeline.py
2. **Export Splitwise to Sheets** - Always use --overwrite mode after importing statements

**Why this order:**
- Credit card statements may contain backdated transactions (processing delays, corrections)
- Splitwise must be updated with all transactions first
- Overwrite mode re-fetches and re-sorts all expenses chronologically
- Append mode would break sorting by placing backdated entries at the bottom

**Automation potential:**
- Monthly scheduled runs after statement availability
- Automatic merchant review aggregation
- Email/Slack notifications for completion/errors
- GitHub Actions or cron-based execution

Environment / Running Locally
--------------------------------
- **Activate virtualenv first:** Always activate the project's Python virtual environment before running scripts or installing packages. Example (typical venv in project root named `.venv`): `source .venv/bin/activate` (Linux/macOS) or `.venv\Scripts\activate` (Windows).
- **CRITICAL: Set PYTHONPATH:** When running Python scripts from the terminal, ALWAYS set `PYTHONPATH` to the project root to ensure `src` module imports work correctly. Example: `PYTHONPATH=/home/balaji94/PycharmProjects/SplitwiseImporter python src/pipeline.py` or `export PYTHONPATH=/home/balaji94/PycharmProjects/SplitwiseImporter` before running commands. Without this, you'll get `ModuleNotFoundError: No module named 'src'`.
- **Use the provided VS Code launch configs:** The repository includes `.vscode/launch.json` with entries like "Splitwise Export (Overwrite)" you can use to run scripts with the proper environment variables. These configs set `envFile` to `config/.env` and set `PYTHONPATH` to the workspace automatically.
- **Install deps into the venv:** Run `pip install -r requirements.txt` after activating the venv so `pandas`, `pygsheets`, and `splitwise` are available.
