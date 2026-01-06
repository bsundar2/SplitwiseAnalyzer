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

Current structure (updated Jan 2026):

SplitwiseImporter/
├── src/
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
│   └── splitwise_expense_details_*.json  # Expense cache
└── docs/

🤖 AI Workflow
You are using:

Windsurf (Codeium) with free SWE-1 model.

Also optionally Claude Haiku 4.5 or GPT-4.1 as your free assistant depending on the editor.

Goal is to feed Copilot/Windsurf the context so it can help you write the code.

This summary provides everything Copilot needs.

📝 Current Status (What Has Been Completed)

✅ **Core Infrastructure**
- Set up development environment on Chromebook using Linux/PyCharm
- Created modular project structure with `src/` subdirectories (import_statement, export, update, common, constants)
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
- 2025 data fully imported (386 Amex transactions, 1,459 total Splitwise expenses)
- Now tracking 2026 expenses in new "Expenses 2026" sheet tab

🔧 **Recent Session Changes (Jan 5, 2026)**
- Updated SpotHero (15 expenses) → Transportation > Parking (subcategory ID: 9)
- Updated Amazon marketplace (19 expenses, excluding AWS) → Home > Household supplies (subcategory ID: 14)
- Updated Costco (17 expenses, only Home/Home - Other) → Home > Household supplies
- Fixed date timezone issue in export (removed `utc=True` from pandas date parsing)
- Updated config/.env: START_DATE=2026-01-01, END_DATE=2026-12-31, EXPENSES_WORKSHEET_NAME=Expenses 2026

🚀 Next Steps for Future Development

- Monitor 2026 expense imports and continue merchant review workflow
- Add more merchants to lookup as new transactions are processed
- Consider adding budget vs actual tracking visualization
- Potential future: Plaid integration (deferred for now)

Environment / Running Locally
--------------------------------
- **Activate virtualenv first:** Always activate the project's Python virtual environment before running scripts or installing packages. Example (typical venv in project root named `.venv`): `source .venv/bin/activate` (Linux/macOS) or `.venv\Scripts\activate` (Windows).
- **CRITICAL: Set PYTHONPATH:** When running Python scripts from the terminal, ALWAYS set `PYTHONPATH` to the project root to ensure `src` module imports work correctly. Example: `PYTHONPATH=/home/balaji94/PycharmProjects/SplitwiseImporter python src/pipeline.py` or `export PYTHONPATH=/home/balaji94/PycharmProjects/SplitwiseImporter` before running commands. Without this, you'll get `ModuleNotFoundError: No module named 'src'`.
- **Use the provided VS Code launch configs:** The repository includes `.vscode/launch.json` with entries like "Splitwise Export (Overwrite)" you can use to run scripts with the proper environment variables. These configs set `envFile` to `config/.env` and set `PYTHONPATH` to the workspace automatically.
- **Install deps into the venv:** Run `pip install -r requirements.txt` after activating the venv so `pandas`, `pygsheets`, and `splitwise` are available.
