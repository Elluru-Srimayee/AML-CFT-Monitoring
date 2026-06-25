"""
Customer Profiler
==================
Builds a behavioural profile for each account involved in flagged alerts.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from src.utils.helpers import load_config
from src.utils.logger import get_logger

log = get_logger(__name__)


@dataclass
class CustomerProfile:
    account_id: str
    full_name: str
    date_of_birth: str
    occupation: str
    complete_address: str
    government_id: str
    risk_category: str
    risk_score: int
    total_transactions: int
    total_sent: float
    total_received: float
    avg_transaction_amount: float
    max_transaction_amount: float
    unique_counterparties: int
    countries_involved: list[str]
    payment_types_used: list[str]
    first_seen: str
    last_seen: str
    laundering_gt_count: int          # ground-truth laundering txn count


class CustomerProfiler:
    """
    Computes per-account statistics from the full transaction dataset.
    Enriches each profile with customer details from the customer details file.
    Used during case investigation to establish behavioural baseline.
    """

    def __init__(self, full_df: pd.DataFrame, config_path: str = "config/config.yaml"):
        """
        Args:
            full_df: The complete (cleaned) transaction DataFrame.
            config_path: Path to configuration file.
        """
        self.df = full_df
        self.customer_details_df = pd.DataFrame()
        self._load_customer_details(config_path)

    def _load_customer_details(self, config_path: str) -> None:
        cfg = load_config(config_path)
        inv_cfg = cfg.get("investigation", {})
        path = Path(inv_cfg.get("customer_details_file", "data/raw/customer_details_with_risk.csv"))
        if not path.exists():
            log.warning(
                f"Customer details file not found: {path}. "
                "Customer enrichment will be skipped."
            )
            return

        try:
            self.customer_details_df = pd.read_csv(path, dtype=str).fillna("")
            self.customer_details_df["Account Number"] = self.customer_details_df[
                "Account Number"
            ].astype(str).str.strip()
            log.info(
                f"Loaded {len(self.customer_details_df):,} customer detail rows from {path}"
            )
        except Exception as exc:
            log.warning(f"Failed to load customer details file: {exc}")
            self.customer_details_df = pd.DataFrame()

    def _lookup_customer_details(self, account_id: str) -> dict[str, str]:
        if self.customer_details_df.empty:
            return {}

        acct = str(account_id).strip()
        rows = self.customer_details_df[
            self.customer_details_df["Account Number"] == acct
        ]
        if rows.empty:
            return {}

        row = rows.iloc[0]
        return {
            "full_name": str(row.get("Full Name", "")).strip(),
            "date_of_birth": str(row.get("Date of Birth", "")).strip(),
            "occupation": str(row.get("Occupation", "")).strip(),
            "complete_address": str(row.get("Complete Address", "")).strip(),
            "government_id": str(row.get("Passport/Gov ID Proof", "")).strip(),
            "risk_category": str(row.get("Risk_Category", "")).strip(),
            "risk_score": int(float(row.get("Risk_Score", "0"))) if str(row.get("Risk_Score", "")).strip() else 0,
        }

    def build_profile(self, account_id: str) -> CustomerProfile:
        """Build a full profile for a single account."""
        sent = self.df[self.df["Sender_account"] == account_id]
        recv = self.df[self.df["Receiver_account"] == account_id]
        all_txns = pd.concat([sent, recv]).drop_duplicates()

        countries = set()
        for _, r in all_txns.iterrows():
            if r["Sender_bank_location"]:
                countries.add(str(r["Sender_bank_location"]))
            if r["Receiver_bank_location"]:
                countries.add(str(r["Receiver_bank_location"]))

        counterparties = set(sent["Receiver_account"].tolist()) | set(recv["Sender_account"].tolist())

        ts_col = all_txns["Timestamp"] if "Timestamp" in all_txns.columns else None

        details = self._lookup_customer_details(account_id)

        return CustomerProfile(
            account_id=account_id,
            full_name=details.get("full_name", ""),
            date_of_birth=details.get("date_of_birth", ""),
            occupation=details.get("occupation", ""),
            complete_address=details.get("complete_address", ""),
            government_id=details.get("government_id", ""),
            risk_category=details.get("risk_category", ""),
            risk_score=details.get("risk_score", 0),
            total_transactions=len(all_txns),
            total_sent=float(sent["Amount"].sum()),
            total_received=float(recv["Amount"].sum()),
            avg_transaction_amount=float(all_txns["Amount"].mean()) if len(all_txns) else 0.0,
            max_transaction_amount=float(all_txns["Amount"].max()) if len(all_txns) else 0.0,
            unique_counterparties=len(counterparties),
            countries_involved=sorted(countries),
            payment_types_used=sorted(all_txns["Payment_type"].unique().tolist()),
            first_seen=str(ts_col.min()) if ts_col is not None and not ts_col.empty else "N/A",
            last_seen=str(ts_col.max()) if ts_col is not None and not ts_col.empty else "N/A",
            laundering_gt_count=int(all_txns["Is_laundering"].sum()) if "Is_laundering" in all_txns.columns else 0,
        )

    def build_profiles_for_accounts(self, account_ids: list[str]) -> dict[str, CustomerProfile]:
        """Build profiles for a list of account IDs."""
        profiles = {}
        for acct in account_ids:
            profiles[acct] = self.build_profile(acct)
        return profiles
