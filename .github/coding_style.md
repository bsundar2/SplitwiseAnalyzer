Coding Style Guide — Project conventions

Purpose
-------
This small guide captures a few project-specific rules so future edits are consistent and readable. It focuses on exception handling, logging, and avoiding magic strings.

Rule 1 — Do not catch ImportError or use broad excepts
-----------------------------------------------------
Do not catch ImportError. If a dependency is required, let ImportError propagate so missing libraries fail fast and are visible to the user.

Also avoid bare `except:` and prefer not to use `except Exception:` unless you have a documented, specific recovery plan. Let unexpected errors propagate rather than silently masking failures.

Bad:
```python
try:
    import pygsheets
except ImportError:
    # silently skip
    pass
```

Good:
```python
import pygsheets  # let ImportError propagate and surface missing dependency
```

If you must catch a class of errors, prefer a specific exception (e.g., `OSError`, `ValueError`) and handle it with a clear recovery or a logged re-raise.

Rule 2 — Prefer specific exceptions where possible
-------------------------------------------------
Catching specific exceptions (ValueError, KeyError, TypeError, OSError, etc.) is preferred. Only use broader catches when you truly intend to handle any runtime error and when you log it and re-raise if appropriate.

Rule 3 — No silent broad catches; fail fast
-----------------------------------------
If you cannot choose a concrete exception class, allow the exception to propagate so the failure is visible and can be addressed. Silent failures make debugging much harder.

Rule 4 — Avoid magic strings and numbers; use constants
------------------------------------------------------
Do not sprinkle identical literal strings or numeric literals across the codebase. Pull repeated or meaningful literals into module-level constants with descriptive names.

Bad:
```python
worksheet = sheet.worksheet_by_title("Splitwise Expenses")
parser.add_argument("--worksheet-name", default="Splitwise Expenses")
```

Good:
```python
DEFAULT_WORKSHEET_NAME = "Splitwise Expenses"
# ... later ...
worksheet = sheet.worksheet_by_title(DEFAULT_WORKSHEET_NAME)
parser.add_argument("--worksheet-name", default=DEFAULT_WORKSHEET_NAME)
```

Rule 5 — Small helpers and flattened control flow
------------------------------------------------
Avoid deeply nested try/except blocks. Break functionality into small helper functions with a single responsibility (e.g., `_apply_column_formats`). Helpers make try/except scoping explicit and easier to test.

Rule 6 — Logging
----------------
- Use the project `LOG` (from `src.utils`) for consistent logging.
- Use `LOG.exception(...)` when logging inside an except block to capture stack traces.
- Use `LOG.info`, `LOG.debug`, `LOG.warning`, `LOG.error` appropriately.

Rule 7 — Document fallback behavior
-----------------------------------
If you implement best-effort fallbacks (e.g., try `worksheet.format` and fall back to an alternative), document the steps in a short comment and still log both success and failure cases.

Examples (bad -> good)
----------------------
Bad:
```python
try:
    x = resource.get()
except:
    return None
```

Good:
```python
try:
    x = resource.get()
except ResourceNotFoundError:
    LOG.info("Resource missing — creating new one")
    x = resource.create()
except Exception as e:
    LOG.exception("Unexpected failure getting resource: %s", e)
    raise
```

Notes for reviewers / PRs
------------------------
- If you see a nested try/except, consider extracting the inner block into a helper and giving the outer block a smaller scope.
- Keep error messages actionable (include variable values or identifiers when safe), but never log secrets.
- Use module-level constants for repeated literals and refer to them across modules where applicable.

Automation
----------
- Consider adding a lint rule or pre-commit hook that flags bare `except:`, broad `except Exception`, and repeated literal strings beyond a threshold.

Acknowledgements
----------------
This repository adopted these practices to improve reliability and debugging when calling external services (pygsheets, Splitwise API, etc.).
