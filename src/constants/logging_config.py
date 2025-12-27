"""Logging configuration for the application."""
import logging
import os
from logging.handlers import RotatingFileHandler

# Configure the root logger
LOG = logging.getLogger("cc_splitwise")

# Create console handler with a higher log level
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)

# Create formatter and add it to the handlers
formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
console_handler.setFormatter(formatter)

# Add the handlers to the logger
LOG.addHandler(console_handler)
LOG.setLevel(os.getenv("LOG_LEVEL", "INFO"))

def setup_file_logging(log_file_path, max_bytes=5*1024*1024, backup_count=5):
    """Configure file logging with rotation.
    
    Args:
        log_file_path: Path to the log file
        max_bytes: Maximum size of log file before rotation (default: 5MB)
        backup_count: Number of backup log files to keep (default: 5)
    """
    file_handler = RotatingFileHandler(
        log_file_path,
        maxBytes=max_bytes,
        backupCount=backup_count
    )
    file_handler.setFormatter(formatter)
    LOG.addHandler(file_handler)
