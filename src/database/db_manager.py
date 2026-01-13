"""Database manager for transaction storage and retrieval."""

import sqlite3
import os
from datetime import datetime
from typing import List, Optional, Dict, Any
from contextlib import contextmanager

from .schema import init_database
from .models import Transaction, ImportLog


class DatabaseManager:
    """Manages SQLite database operations for transactions."""

    def __init__(self, db_path: str = None):
        """Initialize database manager.

        Args:
            db_path: Path to SQLite database file. Defaults to data/transactions.db
        """
        if db_path is None:
            # Default to data/transactions.db in project root
            project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
            db_path = os.path.join(project_root, "data", "transactions.db")

        self.db_path = db_path
        self._ensure_db_exists()

    def _ensure_db_exists(self):
        """Ensure database file and directory exist, initialize schema if new."""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)

        is_new = not os.path.exists(self.db_path)
        conn = self.get_connection()

        if is_new:
            print(f"Initializing new database at {self.db_path}")
            init_database(conn)

        conn.close()

    def get_connection(self) -> sqlite3.Connection:
        """Get a database connection with row factory."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row  # Return rows as dictionaries
        return conn

    @contextmanager
    def transaction(self):
        """Context manager for database transactions."""
        conn = self.get_connection()
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()

    # ==================== Transaction CRUD ====================

    def insert_transaction(self, txn: Transaction) -> int:
        """Insert a new transaction, return its ID.

        Args:
            txn: Transaction object to insert

        Returns:
            Database ID of inserted transaction
        """
        with self.transaction() as conn:
            cursor = conn.cursor()
            data = txn.to_dict()

            # Remove id if present (auto-increment)
            data.pop("id", None)

            columns = ", ".join(data.keys())
            placeholders = ", ".join(["?"] * len(data))
            query = f"INSERT INTO transactions ({columns}) VALUES ({placeholders})"

            cursor.execute(query, list(data.values()))
            return cursor.lastrowid

    def insert_transactions_batch(self, transactions: List[Transaction]) -> List[int]:
        """Insert multiple transactions efficiently.

        Args:
            transactions: List of Transaction objects

        Returns:
            List of inserted IDs
        """
        if not transactions:
            return []

        ids = []
        with self.transaction() as conn:
            cursor = conn.cursor()

            for txn in transactions:
                data = txn.to_dict()
                data.pop("id", None)

                columns = ", ".join(data.keys())
                placeholders = ", ".join(["?"] * len(data))
                query = f"INSERT INTO transactions ({columns}) VALUES ({placeholders})"

                cursor.execute(query, list(data.values()))
                ids.append(cursor.lastrowid)

        return ids

    def get_transaction_by_id(self, txn_id: int) -> Optional[Transaction]:
        """Retrieve transaction by ID."""
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM transactions WHERE id = ?", (txn_id,))
        row = cursor.fetchone()
        conn.close()

        if row:
            return Transaction.from_row(dict(row))
        return None

    def get_transaction_by_splitwise_id(
        self, splitwise_id: int
    ) -> Optional[Transaction]:
        """Retrieve transaction by Splitwise expense ID."""
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute(
            "SELECT * FROM transactions WHERE splitwise_id = ?", (splitwise_id,)
        )
        row = cursor.fetchone()
        conn.close()

        if row:
            return Transaction.from_row(dict(row))
        return None

    def update_transaction(self, txn_id: int, updates: Dict[str, Any]) -> bool:
        """Update transaction fields.

        Args:
            txn_id: Transaction ID
            updates: Dictionary of field:value pairs to update

        Returns:
            True if updated, False if not found
        """
        if not updates:
            return False

        # Always update updated_at timestamp
        updates["updated_at"] = datetime.utcnow().isoformat()

        with self.transaction() as conn:
            cursor = conn.cursor()

            set_clause = ", ".join([f"{k} = ?" for k in updates.keys()])
            query = f"UPDATE transactions SET {set_clause} WHERE id = ?"

            cursor.execute(query, list(updates.values()) + [txn_id])
            return cursor.rowcount > 0

    def mark_written_to_sheet(self, txn_ids: List[int], year: int):
        """Mark transactions as written to Google Sheets.

        Args:
            txn_ids: List of transaction IDs
            year: Year of the sheet tab
        """
        if not txn_ids:
            return

        with self.transaction() as conn:
            cursor = conn.cursor()
            placeholders = ",".join(["?"] * len(txn_ids))
            query = f"""
                UPDATE transactions 
                SET written_to_sheet = 1,
                    sheet_year = ?,
                    updated_at = ?
                WHERE id IN ({placeholders})
            """
            cursor.execute(query, [year, datetime.utcnow().isoformat()] + txn_ids)

    # ==================== Queries ====================

    def get_transactions_by_date_range(
        self, start_date: str, end_date: str, include_deleted: bool = False
    ) -> List[Transaction]:
        """Get transactions within date range.

        Args:
            start_date: ISO date (YYYY-MM-DD)
            end_date: ISO date (YYYY-MM-DD)
            include_deleted: Whether to include Splitwise-deleted transactions

        Returns:
            List of Transaction objects
        """
        conn = self.get_connection()
        cursor = conn.cursor()

        query = "SELECT * FROM transactions WHERE date >= ? AND date <= ?"
        params = [start_date, end_date]

        if not include_deleted:
            query += " AND (splitwise_deleted_at IS NULL OR splitwise_deleted_at = '')"

        query += " ORDER BY date, merchant"

        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()

        return [Transaction.from_row(dict(row)) for row in rows]

    def get_unwritten_transactions(
        self, year: Optional[int] = None
    ) -> List[Transaction]:
        """Get transactions not yet written to Google Sheets.

        Args:
            year: Optional year filter

        Returns:
            List of Transaction objects
        """
        conn = self.get_connection()
        cursor = conn.cursor()

        query = """
            SELECT * FROM transactions 
            WHERE written_to_sheet = 0
            AND (splitwise_deleted_at IS NULL OR splitwise_deleted_at = '')
        """
        params = []

        if year:
            query += " AND strftime('%Y', date) = ?"
            params.append(str(year))

        query += " ORDER BY date, merchant"

        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()

        return [Transaction.from_row(dict(row)) for row in rows]

    def find_potential_duplicates(
        self,
        date: str,
        merchant: str,
        amount: float,
        tolerance_days: int = 3,
        amount_tolerance: float = 0.01,
    ) -> List[Transaction]:
        """Find potential duplicate transactions.

        Args:
            date: Transaction date
            merchant: Merchant name
            amount: Transaction amount
            tolerance_days: Days before/after to check
            amount_tolerance: Amount difference tolerance

        Returns:
            List of potential duplicate Transaction objects
        """
        conn = self.get_connection()
        cursor = conn.cursor()

        query = """
            SELECT * FROM transactions
            WHERE merchant = ?
            AND ABS(julianday(date) - julianday(?)) <= ?
            AND ABS(amount - ?) <= ?
            AND (splitwise_deleted_at IS NULL OR splitwise_deleted_at = '')
        """

        cursor.execute(
            query, [merchant, date, tolerance_days, amount, amount_tolerance]
        )
        rows = cursor.fetchall()
        conn.close()

        return [Transaction.from_row(dict(row)) for row in rows]

    def get_transactions_by_source(self, source: str) -> List[Transaction]:
        """Get all transactions from a specific source.

        Args:
            source: Source identifier (amex, visa, splitwise, etc.)

        Returns:
            List of Transaction objects
        """
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute(
            "SELECT * FROM transactions WHERE source = ? ORDER BY date", (source,)
        )
        rows = cursor.fetchall()
        conn.close()

        return [Transaction.from_row(dict(row)) for row in rows]

    # ==================== Import Logging ====================

    def log_import(self, log: ImportLog) -> int:
        """Log an import operation.

        Args:
            log: ImportLog object

        Returns:
            Log entry ID
        """
        with self.transaction() as conn:
            cursor = conn.cursor()
            data = log.to_dict()
            data.pop("id", None)

            columns = ", ".join(data.keys())
            placeholders = ", ".join(["?"] * len(data))
            query = f"INSERT INTO import_log ({columns}) VALUES ({placeholders})"

            cursor.execute(query, list(data.values()))
            return cursor.lastrowid

    def get_import_history(self, source_type: Optional[str] = None) -> List[dict]:
        """Get import history.

        Args:
            source_type: Optional filter by source type

        Returns:
            List of import log entries as dictionaries
        """
        conn = self.get_connection()
        cursor = conn.cursor()

        if source_type:
            cursor.execute(
                "SELECT * FROM import_log WHERE source_type = ? ORDER BY timestamp DESC",
                (source_type,),
            )
        else:
            cursor.execute("SELECT * FROM import_log ORDER BY timestamp DESC")

        rows = cursor.fetchall()
        conn.close()

        return [dict(row) for row in rows]

    # ==================== Statistics ====================

    def get_stats(self) -> Dict[str, Any]:
        """Get database statistics.

        Returns:
            Dictionary with various stats
        """
        conn = self.get_connection()
        cursor = conn.cursor()

        stats = {}

        # Total transactions
        cursor.execute("SELECT COUNT(*) FROM transactions")
        stats["total_transactions"] = cursor.fetchone()[0]

        # Transactions by source
        cursor.execute(
            """
            SELECT source, COUNT(*) as count 
            FROM transactions 
            GROUP BY source
        """
        )
        stats["by_source"] = {row["source"]: row["count"] for row in cursor.fetchall()}

        # Written vs unwritten
        cursor.execute(
            "SELECT written_to_sheet, COUNT(*) FROM transactions GROUP BY written_to_sheet"
        )
        written_counts = {row[0]: row[1] for row in cursor.fetchall()}
        stats["written_to_sheet"] = written_counts.get(1, 0)
        stats["not_written_to_sheet"] = written_counts.get(0, 0)

        # Splitwise integration
        cursor.execute(
            "SELECT COUNT(*) FROM transactions WHERE splitwise_id IS NOT NULL"
        )
        stats["in_splitwise"] = cursor.fetchone()[0]

        cursor.execute(
            "SELECT COUNT(*) FROM transactions WHERE splitwise_deleted_at IS NOT NULL"
        )
        stats["deleted_in_splitwise"] = cursor.fetchone()[0]

        # Date range
        cursor.execute("SELECT MIN(date), MAX(date) FROM transactions")
        min_date, max_date = cursor.fetchone()
        stats["date_range"] = {"min": min_date, "max": max_date}

        conn.close()
        return stats
