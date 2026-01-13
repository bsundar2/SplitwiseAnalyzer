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

Current structure (updated Jan 2026 - Phase 1 Complete):

SplitwiseImporter/
├── src/
│   ├── database/               # Local SQLite database layer (NEW - Phase 1)
│   │   ├── __init__.py
│   │   ├── schema.py           # Table definitions
│   │   ├── models.py           # Transaction & ImportLog dataclasses
│   │   └── db_manager.py       # DatabaseManager with CRUD operations
│   ├── db_migration/           # Database migration tools (NEW - Phase 1)
│   │   └── migrate_from_splitwise_api.py # Import from Splitwise API
│   ├── import_statement/       # CSV statement parsing and import pipeline
│   │   ├── pipeline.py         # Main ETL orchestrator
│   │   ├── parse_statement.py  # CSV parsing
│   │   └── categorization.py   # Transaction categorization
│   ├── export/
│   │   └── splitwise_export.py # Fetch and export Splitwise expenses
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
│   └── transactions.db         # SQLite database (NEW - Phase 1)
└── docs/
    ├── database_migration.md   # Phase 1 migration guide
    └── ...

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

🔧 **Recent Session Changes (Jan 12, 2026 - Phase 1 Complete)**
- ✅ Created SQLite database schema with transactions, duplicate_checks, and import_log tables
- ✅ Built DatabaseManager with full CRUD operations and deduplication logic
- ✅ Migrated 1,654 historical transactions from Splitwise API to database
- ✅ Removed obsolete cache-based migration scripts
- ✅ Reorganized structure: migration tools moved to `src/db_migration/`
- ✅ Documentation updated to `docs/database_migration.md`
- ✅ All transactions marked as unwritten to sheets (ready for Phase 2 sync)

🚀 Next Steps - Phase 2: Refactor Pipeline to Use Database

**Import Pipeline Refactor:**
- CSV → Database (with deduplication) → Splitwise → update DB with splitwise_id
- Remove JSON cache dependency, use DatabaseManager instead

**Export Pipeline Refactor:**
- Database → Sheets (only unwritten rows) → mark as written_to_sheet=True
- Implement append-only sheet writes with tracking

**Analysis Layer:**
- Keep raw transaction tabs (2024, 2025, 2026) in sheets
- Create separate aggregate tabs (monthly_summary, category_rollups, budget_tracking)
- Move rolling averages off transaction tabs

See `docs/database_migration.md` for Phase 1 details.

📋 Processing Pipeline Workflow

**Phase 1 (Current): Database Migration**

1. **Migrate historical Splitwise data to database** (One-time setup)
   ```bash
   source .venv/bin/activate
   export PYTHONPATH=/home/balaji94/PycharmProjects/SplitwiseImporter
   
   # Import by year
   python src/db_migration/migrate_from_splitwise_api.py --year 2025
   python src/db_migration/migrate_from_splitwise_api.py --year 2026
   
   # Or import multiple years
   python src/db_migration/migrate_from_splitwise_api.py --years 2023 2024 2025 2026
   
   # Check database stats
   python -c "from src.database import DatabaseManager; print(DatabaseManager().get_stats())"
   ```

**Phase 2 (Next): Refactored Pipeline Flow**
The pipeline will be updated to:

1. **Import statements to Database** - Parse CSV, dedupe, and store in DB
2. **Sync Database to Splitwise** - Push unsynced transactions to Splitwise API
3. **Export Database to Sheets** - Write only new/unwritten transactions to sheets

**Current order for data integrity (until Phase 2):**

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
