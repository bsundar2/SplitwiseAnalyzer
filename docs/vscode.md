# Run in VS Code

What is provided: example VS Code launch configurations and tasks at `.vscode/launch.json` and `.vscode/tasks.json` to run the two primary scripts used during development: `src/splitwise_export.py` and `src/pipeline.py`.

Quick steps to use in VS Code:

1. Open the workspace folder in VS Code.
2. Select your Python interpreter (Command Palette → "Python: Select Interpreter") and pick your virtual environment (for example `.venv/bin/python`).
3. Open the Run and Debug view (left sidebar) and choose one of the configurations (e.g., "Run splitwise_export.py" or "Run pipeline.py"). Press F5 to run with debugging or Ctrl+F5 to run without debugging.
4. Alternatively, use the Terminal → Run Task... menu and choose one of the example tasks ("Run splitwise_export (example)" or "Run pipeline (dry-run)").

Example arguments (update in `.vscode/launch.json` as needed):

- `src/splitwise_export.py` example: `--start-date 2025-01-01 --end-date 2025-12-31 --sheet-name "MyFinanceSheet"`
- `src/pipeline.py` example: `--statement data/raw/sample_statement.csv --dry-run`

Notes:

- The provided launch configs use the integrated terminal so your selected interpreter / venv will be used if configured in VS Code.
- If your Python interpreter setting variable differs, edit `.vscode/tasks.json` and `.vscode/launch.json` to point to your interpreter (for example `${workspaceFolder}/.venv/bin/python`).
- Customize the `args` in `.vscode/launch.json` to change defaults when launching from the Run view.
