"""
Sanctions Checker
==================
Fuzzy-matches account IDs and entity names against the configured sanction_list.
Uses rapidfuzz for fast string similarity matching.
"""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

from src.utils.helpers import load_config
from src.utils.logger import get_logger

log = get_logger(__name__)

try:
    from rapidfuzz import fuzz, process as rf_process
    _HAS_RAPIDFUZZ = True
except ImportError:
    _HAS_RAPIDFUZZ = False
    log.warning("rapidfuzz not installed — sanctions check will use exact matching only")


class SanctionsChecker:
    """
    Cross-references account IDs and associated entities against the sanction_list.

    Usage:
        checker = SanctionsChecker()
        hits = checker.check_accounts(["ACC123", "GLOBAL SHADOW CORP"])
    """

    def __init__(self, config_path: str = "config/config.yaml"):
        cfg = load_config(config_path)
        inv_cfg = cfg["investigation"]
        self.watchlist_file = inv_cfg.get("sanctions_file", "config/sanction_list.csv")
        self.threshold = int(inv_cfg.get("fuzzy_match_threshold", 85))
        self._watchlist: list[str] = []
        self._watchlist_row_index: list[int] = []
        self._watchlist_df: pd.DataFrame = pd.DataFrame()
        self._load_watchlist()

    # ── Public API ────────────────────────────────────────────────────────

    def check_accounts(self, account_ids: list[str]) -> list[dict]:
        """
        Check a list of account IDs / names against the sanction_list.

        Returns:
            List of hit dicts with keys: query, matched_entity, score, list_type, country
        """
        if not account_ids or self._watchlist_df.empty:
            return []

        hits = []
        for query in account_ids:
            match = self._match(str(query))
            if match:
                hits.append(match)

        if hits:
            log.warning(f"Sanctions check: {len(hits)} watchlist hit(s) found!")
        else:
            log.info("Sanctions check: No watchlist hits")

        return hits

    def is_on_watchlist(self, name: str) -> bool:
        return self._match(name) is not None

    # ── Private ───────────────────────────────────────────────────────────

    def _load_watchlist(self) -> None:
        path = Path(self.watchlist_file)
        if not path.exists():
            log.warning(f"Watchlist file not found: {path}. Sanctions check disabled.")
            return

        self._watchlist_df = pd.read_csv(path)

        if "entity_name" in self._watchlist_df.columns:
            names = self._watchlist_df["entity_name"].astype(str).tolist()
            indices = list(self._watchlist_df.index)
        elif "Primary_Name" in self._watchlist_df.columns:
            names = []
            indices = []
            for idx, row in self._watchlist_df.iterrows():
                primary_name = str(row["Primary_Name"]).strip()
                if primary_name:
                    names.append(primary_name.upper())
                    indices.append(idx)
                aka_names = str(row.get("AKA_Names", "")).strip()
                if aka_names and aka_names.upper() != "NAN":
                    for alias in re.split(r"\s*[|,;]\s*", aka_names):
                        alias = alias.strip()
                        if alias:
                            names.append(alias.upper())
                            indices.append(idx)
        else:
            log.warning(
                f"Unsupported sanctions file format: {path}. "
                "Expected 'entity_name' or 'Primary_Name' column."
            )
            return

        self._watchlist = [n for n in names if n]
        self._watchlist_row_index = indices[: len(self._watchlist)]
        log.info(f"Loaded {len(self._watchlist)} watchlist entries from {path}")

    def _match(self, query: str) -> dict | None:
        if not self._watchlist:
            return None

        q_upper = query.upper().strip()

        if _HAS_RAPIDFUZZ:
            result = rf_process.extractOne(
                q_upper, self._watchlist, scorer=fuzz.token_sort_ratio
            )
            if result and result[1] >= self.threshold:
                matched_name, score, idx = result
                row = self._watchlist_df.iloc[idx]
                return {
                    "query": query,
                    "matched_entity": matched_name,
                    "score": score,
                    "list_type": row.get("list_type", "Unknown"),
                    "country": row.get("country", "Unknown"),
                    "entity_type": row.get("entity_type", "Unknown"),
                    "notes": row.get("notes", ""),
                }
        else:
            # Exact match fallback
            if q_upper in self._watchlist:
                idx = self._watchlist.index(q_upper)
                row_index = self._watchlist_row_index[idx]
                row = self._watchlist_df.iloc[row_index]
                return {
                    "query": query,
                    "matched_entity": q_upper,
                    "score": 100,
                    "list_type": row.get("list_type", row.get("List_Source", "Unknown")),
                    "country": row.get("country", row.get("Country_of_Residence", row.get("Nationality", "Unknown"))),
                    "entity_type": row.get("entity_type", row.get("Entity_Type", "Unknown")),
                    "notes": row.get("notes", row.get("Remarks", "")),
                }
        return None
