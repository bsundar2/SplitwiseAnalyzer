Coding Style Guide — Project conventions

Purpose
-------
This small guide captures a few project-specific rules so future edits are consistent and readable. It focuses on exception handling, imports, logging, and avoiding magic strings.

Rule 0 — Organize imports at the top of the file
------------------------------------------------
- All imports should be at the top of the file, grouped in the following order:
  1. Standard library imports
  2. Third-party library imports
  3. Local application/library specific imports
- Separate each group with a blank line
- Within each group, sort imports alphabetically

Example:
```python
# Standard library
import os
from datetime import datetime, timedelta

# Third-party
import pandas as pd
from dotenv import load_dotenv
from splitwise import Splitwise

# Local application
from src.utils import LOG, merchant_slug
```

Rule 1 — Remove unused imports and variables
-------------------------------------------
- Always remove unused imports and variables to keep the code clean and maintainable.
- Use your IDE's "Optimize Imports" feature before committing.
- If you're temporarily commenting out code that uses certain imports, remove those imports and add them back when needed.

Bad:
```python
import os  # unused import
from datetime import datetime  # unused import

unused_var = "This is never used"  # unused variable

def my_function():
    return "Hello"
```

Good:
```python
def my_function():
    return "Hello"
```

- If a variable is intentionally unused (e.g., in tuple unpacking), prefix it with an underscore:

```python
# Good: Using _ to indicate intentionally unused variable
first, _ = (1, 2)

# Good: Using _ for unused loop variables
for _ in range(3):
    do_something()
```

Rule 2 — Do not catch ImportError or use broad excepts
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

Rule 4 — No emojis in log messages
-----------------------------------
- Do not use emojis in log messages or status outputs
- Keep log messages clear, concise, and professional
- Use standard punctuation and formatting instead of emojis

Bad:
```python
LOG.info("✅ Successfully processed data")  # Bad: Uses emoji
print("❌ Error: Could not save file")     # Bad: Uses emoji in console output
```

Good:
```python
LOG.info("Successfully processed data")    # Good: No emoji
print("Error: Could not save file")       # Good: No emoji
```

Rule 5 — Avoid magic strings and numbers; use constants
------------------------------------------------------
Do not sprinkle identical literal strings or numeric literals across the codebase. Pull repeated or meaningful literals into module-level constants with descriptive names.

This includes SQL query fragments, UI strings, configuration values, and any repeated literals.

Bad:
```python
worksheet = sheet.worksheet_by_title("Splitwise Expenses")
parser.add_argument("--worksheet-name", default="Splitwise Expenses")

# Bad: SQL fragments as magic strings
query = "SELECT * FROM transactions ORDER BY date"
query2 = "SELECT * FROM users ORDER BY date"
```

Good:
```python
DEFAULT_WORKSHEET_NAME = "Splitwise Expenses"
# ... later ...
worksheet = sheet.worksheet_by_title(DEFAULT_WORKSHEET_NAME)
parser.add_argument("--worksheet-name", default=DEFAULT_WORKSHEET_NAME)

# Good: SQL fragments as constants
SQL_ORDER_BY_DATE = "ORDER BY date"
SQL_ORDER_BY_DATE_MERCHANT = "ORDER BY date, merchant"
query = f"SELECT * FROM transactions {SQL_ORDER_BY_DATE}"
query2 = f"SELECT * FROM users {SQL_ORDER_BY_DATE}"
```

Rule 5a — Never use the `global` keyword
-----------------------------------------
Avoid using the `global` keyword in functions. Global mutable state makes code harder to test, debug, and reason about.

Instead, use these patterns:
- **Cached functions** (preferred): Use `@functools.cache` or `@functools.lru_cache` decorators
- **Class-based state**: Encapsulate state in a class with class-level attributes
- **Dependency injection**: Pass dependencies as parameters

Bad:
```python
_db_instance = None

def get_database():
    global _db_instance  # Bad: Uses global keyword
    if _db_instance is None:
        _db_instance = DatabaseManager()
    return _db_instance
```

Good:
```python
# Option 1: Cached function (preferred - simple, thread-safe, Pythonic)
from functools import cache

@cache
def get_database() -> DatabaseManager:
    """Get singleton DatabaseManager (cached automatically)."""
    return DatabaseManager()

@cache
def load_project_env() -> None:
    """Load .env file once (cached automatically)."""
    project_root = Path(__file__).parent.parent.parent
    env_path = project_root / "config" / "..env"
    load_dotenv(env_path)

# Option 2: Class-based singleton
class DatabaseManager:
    _instance = None
    
    @classmethod
    def get_instance(cls) -> 'DatabaseManager':
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

# Option 3: Dependency injection (most flexible)
def process_transactions(db: DatabaseManager = None):
    """Process transactions using provided or default database."""
    db = db or get_database()  # Allow injection for testing
    # ... use db ...
```

Note: The `@cache` decorator is preferred for singleton patterns as it's simpler, thread-safe, and follows Python conventions. Never use `global` keyword anywhere in the codebase.

Rule 5b — Small helpers and flattened control flow
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

Rule 8 — Group related constants and utilities in classes
----------------------------------------------------------
When you have multiple related constants or utilities that work together (e.g., mappings and their reverse lookups, ID-to-name conversions), consider grouping them in a simple class rather than using module-level functions and dictionaries.

Use descriptive module names that clearly indicate their purpose (e.g., `transaction_filters.py` instead of `filters.py`).

Benefits:
- Encapsulates related data and behavior
- Makes initialization explicit and testable
- Provides clear namespace for related functionality
- Easier to extend with additional methods

Bad:
```python
def get_subcategory_ids():
    import json  # Import inside function
    # ... load from file ...
    return mapping

SUBCATEGORY_IDS = get_subcategory_ids()
SUBCATEGORY_NAMES = {v: k for k, v in SUBCATEGORY_IDS.items()}
```

Good:
```python
# Standard library imports at top
import json
from pathlib import Path
from typing import Dict

class SubcategoryMapper:
    """Manages Splitwise subcategory ID mappings."""
    
    def __init__(self):
        self._ids: Dict[str, int] = {}
        self._names: Dict[int, str] = {}
        self._load_mappings()
    
    def _load_mappings(self):
        """Load subcategory mappings from configuration file."""
        # ... load from file ...
    
    @property
    def ids(self) -> Dict[str, int]:
        """Get mapping of names to IDs."""
        return self._ids.copy()
    
    def get_id(self, name: str) -> int:
        """Get ID by name."""
        return self._ids[name]

# Global instance for convenience
_subcategory_mapper = SubcategoryMapper()
SUBCATEGORY_IDS = _subcategory_mapper.ids  # For backward compatibility
```

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
