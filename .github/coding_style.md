Coding Style Guide — Project conventions

Purpose
-------
This small guide captures a few project-specific rules so future edits are consistent and readable. It focuses on exception handling and logging because we ran into several nested bare `except:` blocks that made debugging and reliability harder.

Rule 1 — Avoid bare `except:`
----------------------------
Do not use bare `except:` anywhere. Bare excepts hide KeyboardInterrupt/SystemExit and make debugging hard.

Bad:
```python
try:
    do_something()
except:
    pass
```

Good:
```python
try:
    do_something()
except SpecificError as e:
    LOG.warning("Failed doing something: %s", e)
    raise
```

If you must catch all exceptions, prefer `except Exception as e:` and always log the exception with context. E.g.:
```python
try:
    do_something()
except Exception as e:
    LOG.exception("Unexpected error doing something: %s", e)
    raise
```
Updated guidance: Prefer not catching all exceptions (including `except Exception`) unless you have a specific reason. If you cannot choose a concrete exception class, let the exception propagate so the failure is visible and can be debugged. Use broad catch only when implementing a deliberate fallback with logging and a clear recovery path.

Rule 2 — Prefer specific exceptions where possible
-------------------------------------------------
Catching specific exceptions (ValueError, KeyError, TypeError, IOError, etc.) is preferred. Only use broader catches when you truly intend to handle any runtime error and when you log it.

Rule 3 — Small helpers and flattened control flow
------------------------------------------------
Avoid deeply nested try/except blocks. Break functionality into small helper functions that each have a single responsibility (e.g. `_safe_authorize`, `_open_spreadsheet`, `_apply_column_formats`). Helpers make try/except scoping explicit and easier to read and test.

Rule 4 — Logging
----------------
- Use the project `LOG` (from `src.utils`) for consistent logging.
- Use `LOG.exception(...)` when logging inside an except block to capture stack traces.
- Use `LOG.info`, `LOG.debug`, `LOG.warning`, `LOG.error` appropriately.

Rule 5 — Fail fast
-------------------
If an operation must succeed (e.g., authenticating to an API) and you cannot proceed without it, log the error and re-raise to stop execution. Silent failures should be avoided.

Rule 6 — Document fallback behavior
-----------------------------------
If you implement best-effort fallbacks (e.g., try `worksheet.format` and fall back to `batchUpdate`), document the steps in a short comment and still log both success and failure cases.

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

Automation
----------
- Consider adding a lint rule or pre-commit hook that flags bare `except:` occurrences.

Acknowledgements
----------------
This repository adopted these practices to improve reliability and debugging when calling external services (pygsheets, Splitwise API, etc.).
