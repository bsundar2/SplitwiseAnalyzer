"""Bank statement format detection and configuration."""

import json
from pathlib import Path
from typing import Optional, Dict, Any

from src.common.utils import LOG


class BankConfig:
    """Load and manage bank statement configurations."""

    def __init__(self, config_path: Optional[Path] = None):
        """Initialize bank configuration from JSON file.

        Args:
            config_path: Path to bank_config.json. If None, uses default location.
        """
        if config_path is None:
            config_path = Path(__file__).parent.parent.parent / "config" / "bank_config.json"

        self.config_path = config_path
        self.config = self._load_config()

    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from JSON file."""
        try:
            with open(self.config_path, "r") as f:
                return json.load(f)
        except Exception as e:
            LOG.error("Failed to load bank config from %s: %s", self.config_path, e)
            raise

    def get_bank_config(self, bank_name: str) -> Dict[str, Any]:
        """Get configuration for a specific bank.

        Args:
            bank_name: Bank key (e.g., 'amex', 'bofa')

        Returns:
            Bank configuration dictionary
        """
        if bank_name not in self.config["banks"]:
            raise ValueError(f"Unknown bank: {bank_name}")
        return self.config["banks"][bank_name]

    def detect_bank(self, df) -> str:
        """Detect which bank statement this CSV is based on column names.

        Args:
            df: Pandas DataFrame from CSV

        Returns:
            Bank key (e.g., 'amex', 'bofa')

        Raises:
            ValueError: If bank cannot be detected
        """
        columns = set(df.columns)
        detection_rules = self.config.get("detection_rules", {})

        for bank_name, rules in detection_rules.items():
            required = set(rules.get("required_columns", []))
            if required.issubset(columns):
                LOG.info("Detected bank: %s", bank_name)
                return bank_name

        raise ValueError(
            f"Could not detect bank from columns: {list(columns)}. "
            f"Required columns for amex: {detection_rules['amex']['required_columns']}, "
            f"for bofa: {detection_rules['bofa']['required_columns']}"
        )

    def get_category_mapping(self, bank_name: str) -> Dict[str, str]:
        """Get category mapping for a bank.

        Args:
            bank_name: Bank key (e.g., 'amex', 'bofa')

        Returns:
            Merchant-to-category mapping dictionary
        """
        bank_cfg = self.get_bank_config(bank_name)
        mapping_file = bank_cfg.get("category_mapping_file")

        if not mapping_file:
            return {}

        mapping_path = Path(__file__).parent.parent.parent / "config" / mapping_file
        try:
            with open(mapping_path, "r") as f:
                return json.load(f)
        except Exception as e:
            LOG.warning("Failed to load category mapping for %s: %s", bank_name, e)
            return {}
