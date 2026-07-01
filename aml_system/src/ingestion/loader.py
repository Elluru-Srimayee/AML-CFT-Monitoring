"""
Data Ingestion Module
=====================
Loads and validates the IBM AML transaction CSV dataset.
Handles 1M+ rows via chunked pandas reading.

Expected columns (IBM Kaggle AML dataset):
    Time, Date, Sender_account, Receiver_account, Amount,
    Payment_currency, Received_currency, Sender_bank_location,
    Receiver_bank_location, Payment_type, Is_laundering, Laundering_type
"""

from __future__ import annotations

import os
import random
from pathlib import Path
from typing import Iterator

import numpy as np
import pandas as pd
from tqdm import tqdm

from src.utils.helpers import load_config
from src.utils.logger import get_logger

log = get_logger(__name__)

# Canonical column names expected from the IBM dataset
REQUIRED_COLUMNS = [
    "Time",
    "Date",
    "Sender_account",
    "Receiver_account",
    "Amount",
    "Payment_currency",
    "Received_currency",
    "Sender_bank_location",
    "Receiver_bank_location",
    "Payment_type",
]


class TransactionLoader:
    """
    Loads and pre-processes the IBM AML transaction dataset.

    Usage:
        loader = TransactionLoader()
        df = loader.load_all()                      # full DataFrame in memory
        for chunk in loader.load_chunks():          # memory-efficient iteration
            process(chunk)
    """

    def __init__(self, config_path: str = "config/config.yaml"):
        cfg = load_config(config_path)
        self.cfg = cfg["ingestion"]
        self.project_root = Path(__file__).resolve().parents[2]
        self.input_file = self.cfg["input_file"]
        self.sample_files = [
            self.project_root / "data" / "raw" / name
            for name in ("sample1.csv", "sample2.csv", "sample3.csv")
        ]
        self.chunk_size = self.cfg.get("chunk_size", 50_000)
        self.date_fmt = self.cfg.get("date_format", "%Y/%m/%d")
        self.time_fmt = self.cfg.get("time_format", "%H:%M:%S")

    # ── Public API ────────────────────────────────────────────────────────

    def load_all(self, sample_n: int | None = None) -> pd.DataFrame:
        """
        Load the full CSV into a single DataFrame.

        Args:
            sample_n: If set, load only the first N rows (for quick testing).

        Returns:
            Cleaned DataFrame with parsed datetime and normalised columns.
        """
        path = self._resolve_input_path()
        if not path.is_absolute():
            path = self.project_root / path
        self.input_file = str(path)
        self._assert_file(path)

        log.info(f"Loading transactions from: {path.resolve()}")
        nrows = None if path in self.sample_files else (sample_n if sample_n else None)

        chunks = []
        reader = pd.read_csv(
            path,
            nrows=nrows,
            chunksize=self.chunk_size,
            low_memory=False,
        )
        total_chunks = (nrows // self.chunk_size + 1) if nrows else None
        for chunk in tqdm(reader, desc="Reading CSV", unit="chunk", total=total_chunks):
            chunks.append(self._clean_chunk(chunk))

        df = pd.concat(chunks, ignore_index=True)
        log.info(f"Loaded {len(df):,} transactions. Columns: {list(df.columns)}")
        self._log_stats(df)
        return df

    def load_chunks(self) -> Iterator[pd.DataFrame]:
        """
        Yield cleaned chunks — memory-efficient for very large datasets.
        """
        path = Path(self.input_file)
        self._assert_file(path)
        reader = pd.read_csv(path, chunksize=self.chunk_size, low_memory=False)
        for chunk in reader:
            yield self._clean_chunk(chunk)

    # ── Private Helpers ───────────────────────────────────────────────────

    def _resolve_input_path(self) -> Path:
        """Choose a sample CSV automatically when present, else fall back to the configured file."""
        available_samples = [p for p in self.sample_files if p.exists()]
        if available_samples:
            chosen = random.choice(available_samples)
            log.info(f"Using sample transaction file: {chosen.resolve()}")
            return chosen
        return Path(self.input_file)

    def _assert_file(self, path: Path) -> None:
        if not path.exists():
            raise FileNotFoundError(
                f"\n\nTransaction CSV not found at: {path.resolve()}\n"
                "Place the IBM Kaggle AML dataset at that path, then re-run.\n"
                "Dataset: https://www.kaggle.com/code/jek1wantaufik/anti-money-laundering-assessment/input?select=SAML-D.csv"
            )

    def _clean_chunk(self, df: pd.DataFrame) -> pd.DataFrame:
        """Validate schema, parse dates, normalise dtypes."""
        df = df.copy()

        # ── Column validation ─────────────────────────────────────────
        missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
        if missing:
            raise ValueError(f"Missing expected columns: {missing}")

        # ── Parse datetime ────────────────────────────────────────────
        # IBM format: Date="10/14/2026", Time="12:38:39"
        date_str = df["Date"].astype(str).str.strip()
        time_str = df["Time"].astype(str).str.strip()
        timestamp_input = date_str + " " + time_str

        df["Timestamp"] = pd.to_datetime(
            timestamp_input,
            format=f"{self.date_fmt} {self.time_fmt}",
            errors="coerce",
        )

        if df["Timestamp"].isna().any():
            df["Timestamp"] = pd.to_datetime(
                timestamp_input,
                infer_datetime_format=True,
                errors="coerce",
            )

        nat_count = df["Timestamp"].isna().sum()
        if nat_count > 0:
            sample = df.loc[df["Timestamp"].isna(), ["Date", "Time"]].head(5)
            log.warning(
                f"{nat_count} rows had unparseable timestamps — set to NaT. "
                f"Sample bad rows: {sample.to_dict(orient='records')}"
            )

        # ── Numeric coercion ──────────────────────────────────────────
        df["Amount"] = pd.to_numeric(df["Amount"], errors="coerce").fillna(0.0)
        # Only parse ground truth columns if they exist in the dataset
        if "Is_laundering" in df.columns:
            df["Is_laundering"] = pd.to_numeric(df["Is_laundering"], errors="coerce").fillna(0).astype(int)
        else:
            df["Is_laundering"] = -1   # -1 = unknown (to be predicted by rules engine)

        if "Laundering_type" not in df.columns:
            df["Laundering_type"] = ""  # will be filled by rules engine output
        # ── String normalisation ──────────────────────────────────────
        str_cols = [
            "Sender_account", "Receiver_account", "Payment_currency",
            "Received_currency", "Sender_bank_location", "Receiver_bank_location",
            "Payment_type", "Laundering_type",
        ]
        for col in str_cols:
            df[col] = df[col].astype(str).str.strip()

        # ── Add transaction index if not present ──────────────────────
        if "Txn_id" not in df.columns:
            df.insert(0, "Txn_id", range(len(df)))

        # ── Drop exact duplicates ─────────────────────────────────────
        before = len(df)
        df.drop_duplicates(
            subset=["Timestamp", "Sender_account", "Receiver_account", "Amount"],
            keep="first",
            inplace=True,
        )
        dropped = before - len(df)
        if dropped:
            log.debug(f"Dropped {dropped} duplicate rows in chunk")

        return df.reset_index(drop=True)

    def _log_stats(self, df: pd.DataFrame) -> None:
        laundering_count = df["Is_laundering"].sum()
        log.info(
            f"Dataset summary — Total: {len(df):,} | "
            f"Laundering (ground truth): {laundering_count:,} ({100*laundering_count/len(df):.2f}%) | "
            f"Date range: {df['Timestamp'].min()} → {df['Timestamp'].max()}"
        )
