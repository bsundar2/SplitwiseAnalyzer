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

A recommended layout (already discussed):

project/
│
├── README.md
├── SUMMARY.md        # This file
│
├── data/
│   ├── raw_statements/
│   ├── processed/
│   └── splitwise_cache.json
│
├── config/
│   ├── credentials.json
│   └── budget_2025.json
│
├── src/
│   ├── splitwise_client.py
│   ├── csv_parser.py
│   ├── expense_classifier.py
│   ├── google_sheets_sync.py
│   └── main.py
│
└── requirements.txt

🤖 AI Workflow
You are using:

Windsurf (Codeium) with free SWE-1 model.

Also optionally Claude Haiku 4.5 or GPT-4.1 as your free assistant depending on the editor.

Goal is to feed Copilot/Windsurf the context so it can help you write the code.

This summary provides everything Copilot needs.

📝 Current Status (What You Have Done)

Set up a development environment on a Chromebook using Linux/Pycharm.

Fixed symlink for PyCharm.

Decided to avoid VS Code.

Attached free AI (Windsurf SWE-1).

Decided not to begin with Plaid.

Decided not to do PDF parsing.

Established high-level architecture.

Requested project scaffolding (provided earlier).

🚀 Next Steps for Copilot

Ask Copilot to:

Generate the splitwise_client.py wrapper (OAuth + basic API calls).

Implement csv_parser.py to read & normalize transactions.

Design the expense classification system (simple mapping → category).

Create a dataframe merge process to combine CSV + Splitwise data.

Create the Google Sheets sync function.

Tie everything together in main.py with CLI flags.

Environment / Running Locally
--------------------------------
- **Activate virtualenv first:** Always activate the project's Python virtual environment before running scripts or installing packages. Example (typical venv in project root named `.venv`): `source .venv/bin/activate` (Linux/macOS) or `.venv\Scripts\activate` (Windows).
- **CRITICAL: Set PYTHONPATH:** When running Python scripts from the terminal, ALWAYS set `PYTHONPATH` to the project root to ensure `src` module imports work correctly. Example: `PYTHONPATH=/home/balaji94/PycharmProjects/SplitwiseImporter python src/pipeline.py` or `export PYTHONPATH=/home/balaji94/PycharmProjects/SplitwiseImporter` before running commands. Without this, you'll get `ModuleNotFoundError: No module named 'src'`.
- **Use the provided VS Code launch configs:** The repository includes `.vscode/launch.json` with entries like "Splitwise Export (Overwrite)" you can use to run scripts with the proper environment variables. These configs set `envFile` to `config/.env` and set `PYTHONPATH` to the workspace automatically.
- **Install deps into the venv:** Run `pip install -r requirements.txt` after activating the venv so `pandas`, `pygsheets`, and `splitwise` are available.
