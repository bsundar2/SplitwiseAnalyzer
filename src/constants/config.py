"""Configuration-related constants and paths.

This module contains all the file paths and configuration-related constants
used throughout the application.
"""
import os
from pathlib import Path

# Project directory structure
PROJECT_ROOT = Path(__file__).parent.parent
BASE_DIR = PROJECT_ROOT

# Configuration files
CFG_PATHS = [
    PROJECT_ROOT / "config.yaml",
    PROJECT_ROOT / "config" / "config.yaml"
]

# Data directories
DATA_DIR = PROJECT_ROOT / "data"
PROCESSED_DIR = DATA_DIR / "processed"

# Cache and state files
CACHE_PATH = DATA_DIR / "splitwise_cache.json"
STATE_PATH = DATA_DIR / "splitwise_exported.json"

# Ensure directories exist
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(PROCESSED_DIR, exist_ok=True)
