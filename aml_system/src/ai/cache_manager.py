"""
cache_manager.py
================

SQLite cache for Azure AI responses.

Purpose
-------
Avoid repeated Azure OpenAI calls for the same customer/business profile.

Updated Cache Key
-----------------
SHA256(
    sender_account +
    normalized_occupation +
    country +
    income_band +
    risk_category +
    currency
)

Why this change?
----------------
The previous cache key used only:

    occupation + country + income_band

That can incorrectly reuse one AI response for different customers or
different transaction profiles.

This version makes the cache safer for transaction-level AI rules.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Optional


class CacheManager:
    """
    SQLite cache for AI responses.

    The cache stores:
        cache_key       -> SHA256 hash
        response_json   -> Azure JSON response
    """

    def __init__(self, db_path: str = "data/processed/ai_cache.db"):
        self.db_path = Path(db_path)

        # Create parent directory if needed
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self.conn = sqlite3.connect(self.db_path)

        self._create_table()

    # ---------------------------------------------------------
    # Database Initialization
    # ---------------------------------------------------------

    def _create_table(self):
        cursor = self.conn.cursor()

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS business_context_cache (
                cache_key TEXT PRIMARY KEY,
                sender_account TEXT,
                occupation TEXT,
                country TEXT,
                income_band TEXT,
                risk_category TEXT,
                currency TEXT,
                response_json TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        # Add new columns safely if table already existed from old version
        self._add_column_if_missing("sender_account", "TEXT")
        self._add_column_if_missing("risk_category", "TEXT")
        self._add_column_if_missing("currency", "TEXT")

        self.conn.commit()

    def _add_column_if_missing(self, column_name: str, column_type: str):
        """
        Add a column to existing SQLite table only if it does not already exist.
        """
        cursor = self.conn.cursor()

        cursor.execute("PRAGMA table_info(business_context_cache)")
        existing_columns = [row[1] for row in cursor.fetchall()]

        if column_name not in existing_columns:
            cursor.execute(
                f"""
                ALTER TABLE business_context_cache
                ADD COLUMN {column_name} {column_type}
                """
            )

    # ---------------------------------------------------------
    # Public Methods
    # ---------------------------------------------------------

    def get(self, cache_key: str) -> Optional[dict]:
        """
        Retrieve cached response.

        Returns
        -------
        dict | None
        """
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
        sender_account: str = "",
        risk_category: str = "",
        currency: str = "",
    ):
        """
        Save Azure AI response into cache.
        """
        cursor = self.conn.cursor()

        cursor.execute(
            """
            INSERT OR REPLACE INTO business_context_cache (
                cache_key,
                sender_account,
                occupation,
                country,
                income_band,
                risk_category,
                currency,
                response_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                cache_key,
                sender_account,
                occupation,
                country,
                income_band,
                risk_category,
                currency,
                json.dumps(response),
            ),
        )

        self.conn.commit()

    def clear(self):
        """
        Clear all cached AI responses.

        Use this after changing the prompt or response schema.
        """
        cursor = self.conn.cursor()

        cursor.execute(
            """
            DELETE FROM business_context_cache
            """
        )

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

        Updated key includes payment_type.

        This ensures different payment types, such as Cash Deposit and Cross-border,
        do not incorrectly share the same AI context.
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
        """
        Normalize occupation to reduce unnecessary Azure calls.

        Important:
        This keeps meaningfully similar roles together, but does not merge
        unrelated occupations.
        """
        if occupation is None:
            return ""

        occ = str(occupation).lower().strip()

        mapping = {
            # Restaurants
            "restaurant owner": "restaurant",
            "restaurant manager": "restaurant",
            "cafe owner": "restaurant",
            "hotel owner": "restaurant",
            "food stall owner": "restaurant",

            # Doctors
            "doctor": "doctor",
            "physician": "doctor",
            "surgeon": "doctor",

            # IT
            "software engineer": "software_engineer",
            "software developer": "software_engineer",
            "programmer": "software_engineer",

            # Retail
            "shop owner": "retail",
            "retailer": "retail",
            "merchant": "retail",

            # Professional services
            "chartered accountant": "chartered_accountant",
            "accountant": "accountant",
            "auditor": "accountant",
            "lawyer": "lawyer",
            "consultant": "consultant",
        }

        return mapping.get(occ, occ)

    @staticmethod
    def income_band(income: float) -> str:
        """
        Convert annual income into income bands.
        """
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
        self.conn.close()