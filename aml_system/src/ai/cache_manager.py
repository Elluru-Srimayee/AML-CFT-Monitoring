"""
cache_manager.py
================

SQLite cache for Azure AI responses.

Purpose
-------
Avoid repeated Azure OpenAI calls for identical business profiles.

Cache Key
---------
SHA256(
    normalized_occupation +
    country +
    income_band
)

Example
-------
Restaurant Owner
Restaurant Manager
Cafe Owner

↓

restaurant

↓

Same cache entry.
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
        key             -> SHA256 hash
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

        Returns
        -------
        dict | None
        """

        cursor = self.conn.cursor()

        cursor.execute(
            """
            SELECT response_json
            FROM business_context_cache
            WHERE cache_key=?
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

    # ---------------------------------------------------------
    # Utility Methods
    # ---------------------------------------------------------

    @staticmethod
    def build_cache_key(
        occupation: str,
        country: str,
        income: float,
    ) -> str:
        """
        Create deterministic SHA256 cache key.

        Parameters
        ----------
        occupation
        country
        income

        Returns
        -------
        str
        """

        occupation = CacheManager.normalize_occupation(occupation)

        income_band = CacheManager.income_band(income)

        raw = f"{occupation}|{country.lower()}|{income_band}"

        return hashlib.sha256(raw.encode()).hexdigest()

    @staticmethod
    def normalize_occupation(occupation: str) -> str:
        """
        Normalize occupation to reduce Azure calls.

        Example

        Restaurant Owner
        Restaurant Manager
        Cafe Owner

        →

        restaurant
        """

        occ = occupation.lower().strip()

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
        }

        return mapping.get(occ, occ)

    @staticmethod
    def income_band(income: float) -> str:
        """
        Convert annual income into income bands.
        """

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