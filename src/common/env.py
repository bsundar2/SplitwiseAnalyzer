"""Environment variable loading utilities.

Centralizes .env file loading to avoid duplication across modules.
"""

import os
from functools import cache
from pathlib import Path
from dotenv import load_dotenv


@cache
def load_project_env() -> None:
    """Load .env file once for entire project.

    Uses @cache decorator for automatic memoization - the function body
    only executes once, subsequent calls return immediately.
    Thread-safe and idempotent.
    """
    # Get project root (3 levels up from this file)
    project_root = Path(__file__).parent.parent.parent
    env_path = project_root / "config" / ".env"
    load_dotenv(env_path)


def get_env(key: str, default: str = None) -> str:
    """Get environment variable, loading .env if needed.

    Args:
        key: Environment variable name
        default: Default value if not found

    Returns:
        Environment variable value or default
    """
    load_project_env()
    return os.getenv(key, default)
