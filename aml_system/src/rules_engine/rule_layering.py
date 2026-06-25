"""
Rule: Layering Detection
=========================
Layering = money passes through a chain of accounts rapidly (A→B→B→C→D)
to obscure the origin.

Detection logic:
  Build a directed graph from all transactions.
  For each node, do DFS to find transaction chains of length >= min_chain_length
  where each hop occurs within window_hours of the previous hop.
  Flag every transaction that is part of such a chain.

Note: For scalability on 1M rows, we limit the graph traversal to accounts
      that appear in both Sender and Receiver roles (i.e., pass-through accounts).
"""

from __future__ import annotations

from collections import defaultdict
from datetime import timedelta

import pandas as pd

from src.rules_engine.base_rule import BaseRule, RuleResult
from src.utils.logger import get_logger

log = get_logger(__name__)


class LayeringRule(BaseRule):
    """Detect rapid multi-hop fund movement chains."""

    name = "Layering"
    description = "Funds pass through 3+ accounts in rapid succession (layering pattern)"

    def __init__(self, config: dict):
        super().__init__(config)
        self.window_hours = int(config.get("window_hours", 72))
        self.min_chain_length = int(config.get("min_chain_length", 3))

    def apply(self, df: pd.DataFrame) -> RuleResult:
        if not self.enabled:
            return self._result([], {})

        if "Timestamp" not in df.columns:
            log.warning("Layering rule skipped — 'Timestamp' column missing")
            return self._result([], {})

        # Identify pass-through accounts (receive AND send money)
        senders = set(df["Sender_account"].unique())
        receivers = set(df["Receiver_account"].unique())
        passthrough = senders & receivers          # accounts that do both

        if not passthrough:
            return self._result([], {})

        # Build adjacency list: sender → list of (receiver, timestamp, df_idx, amount)
        # Only keep edges involving passthrough accounts for efficiency
        relevant = df[
            df["Sender_account"].isin(passthrough) | df["Receiver_account"].isin(passthrough)
        ].copy()

        adjacency: dict[str, list[tuple]] = defaultdict(list)
        for _, row in relevant.iterrows():
            adjacency[row["Sender_account"]].append(
                (row["Receiver_account"], row["Timestamp"], row.name, row["Amount"])
            )

        window = timedelta(hours=self.window_hours)
        triggered_indices: set[int] = set()
        reasons: dict[int, str] = {}

        # DFS to find chains
        def dfs(
            account: str,
            chain_accounts: list[str],
            chain_indices: list[int],
            last_time,
        ) -> None:
            if len(chain_accounts) >= self.min_chain_length:
                # Found a chain — flag all edges in it
                for ci in chain_indices:
                    if ci not in triggered_indices:
                        triggered_indices.add(ci)
                        reasons[ci] = (
                            f"Layering chain: {' → '.join(chain_accounts)} "
                            f"({len(chain_accounts)-1} hops within {self.window_hours}h)"
                        )

            if account not in adjacency:
                return

            for next_acc, ts, idx, amount in adjacency[account]:
                if pd.isna(ts) or pd.isna(last_time):
                    continue
                time_diff = ts - last_time
                if timedelta(0) <= time_diff <= window:
                    # Avoid cycles
                    if next_acc not in chain_accounts:
                        dfs(
                            next_acc,
                            chain_accounts + [next_acc],
                            chain_indices + [idx],
                            ts,
                        )

        # Start DFS from every passthrough account
        for start_account in passthrough:
            if start_account not in adjacency:
                continue
            for next_acc, ts, idx, amount in adjacency[start_account]:
                if not pd.isna(ts):
                    dfs(next_acc, [start_account, next_acc], [idx], ts)

        log.debug(f"LayeringRule → {len(triggered_indices)} flagged rows")
        return self._result(list(triggered_indices), reasons)
