"""
cache_manager.py
================

Thread-safe SQLite cache for Azure AI responses.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from pathlib import Path
from typing import Optional


class CacheManager:
    """
    SQLite cache for AI responses.

    Thread-safe for parallel AI execution.
    """

    def __init__(self, db_path: str = "data/processed/ai_cache.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self._lock = threading.Lock()

        self.conn = sqlite3.connect(
            self.db_path,
            check_same_thread=False,
        )

        self._create_table()

    # ---------------------------------------------------------
    # Database Initialization
    # ---------------------------------------------------------

    def _create_table(self):
        with self._lock:
            cursor = self.conn.cursor()

            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS business_context_cache (
                    cache_key TEXT PRIMARY KEY,
                    occupation TEXT,
                    country TEXT,
                    income_band TEXT,
                    response_json TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

            self.conn.commit()

    # ---------------------------------------------------------
    # Public Methods
    # ---------------------------------------------------------

    def get(self, cache_key: str) -> Optional[dict]:
        """
        Retrieve cached response.
        """
        with self._lock:
            cursor = self.conn.cursor()

            cursor.execute(
                """
                SELECT response_json
                FROM business_context_cache
                WHERE cache_key = ?
                """,
                (cache_key,),
            )

            row = cursor.fetchone()

        if row is None:
            return None

        return json.loads(row[0])

    def save(
        self,
        cache_key: str,
        occupation: str,
        country: str,
        income_band: str,
        response: dict,
    ):
        """
        Save AI response into cache.
        """
        with self._lock:
            cursor = self.conn.cursor()

            cursor.execute(
                """
                INSERT OR REPLACE INTO business_context_cache (
                    cache_key,
                    occupation,
                    country,
                    income_band,
                    response_json
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    cache_key,
                    occupation,
                    country,
                    income_band,
                    json.dumps(response),
                ),
            )

            self.conn.commit()

    def clear(self):
        """
        Clear the cache table.
        """
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute("DELETE FROM business_context_cache")
            self.conn.commit()

    # ---------------------------------------------------------
    # Utility Methods
    # ---------------------------------------------------------

    @staticmethod
    def build_cache_key(
        occupation: str,
        country: str,
        income: float,
        sender_account: str = "",
        risk_category: str = "",
        currency: str = "",
        payment_type: str = "",
    ) -> str:
        """
        Create deterministic SHA256 cache key.
        """
        occupation = CacheManager.normalize_occupation(occupation)
        income_band = CacheManager.income_band(income)

        raw = (
            f"{str(sender_account).strip().lower()}|"
            f"{occupation}|"
            f"{str(country).strip().lower()}|"
            f"{income_band}|"
            f"{str(risk_category).strip().lower()}|"
            f"{str(currency).strip().lower()}|"
            f"{str(payment_type).strip().lower()}"
        )

        return hashlib.sha256(raw.encode()).hexdigest()

    @staticmethod
    def normalize_occupation(occupation: str) -> str:
        if occupation is None:
            return ""

        occ = str(occupation).lower().strip()

        mapping = {
            "restaurant owner": "restaurant",
            "restaurant manager": "restaurant",
            "cafe owner": "restaurant",
            "hotel owner": "restaurant",
            "food stall owner": "restaurant",
            "doctor": "doctor",
            "physician": "doctor",
            "surgeon": "doctor",
            "software engineer": "software_engineer",
            "software developer": "software_engineer",
            "programmer": "software_engineer",
            "shop owner": "retail",
            "retailer": "retail",
            "merchant": "retail",
        }

        return mapping.get(occ, occ)

    @staticmethod
    def income_band(income: float) -> str:
        try:
            income = float(income or 0)
        except (TypeError, ValueError):
            income = 0.0

        if income < 500000:
            return "0-5L"

        if income < 1000000:
            return "5L-10L"

        if income < 2000000:
            return "10L-20L"

        if income < 5000000:
            return "20L-50L"

        return "50L+"

    # ---------------------------------------------------------
    # Cleanup
    # ---------------------------------------------------------

    def close(self):
        with self._lock:
            self.conn.close()