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

from collections import Counter, defaultdict
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
        self.window_hours = int(config.get("window_hours", 120))
        self.min_chain_length = int(config.get("min_chain_length", 3))
        self.min_fan_degree = int(config.get("min_fan_degree", 3))
        self.amount_threshold = float(config.get("amount_threshold", config.get("min_chain_amount", 10000.0)))
        self.detect_fan_out = bool(config.get("detect_fan_out", True))
        self.detect_fan_in = bool(config.get("detect_fan_in", True))

    def apply(self, df: pd.DataFrame) -> RuleResult:
        if not self.enabled:
            return self._result([], {})

        if "Timestamp" not in df.columns:
            log.warning("Layering rule skipped — 'Timestamp' column missing")
            return self._result([], {})

        senders = set(df["Sender_account"].unique())
        receivers = set(df["Receiver_account"].unique())
        passthrough = senders & receivers          # accounts that do both

        window = timedelta(hours=self.window_hours)
        triggered_indices: set[int] = set()
        reasons: dict[int, str] = {}

        def flag_group(indices: list[int], reason: str) -> None:
            total_amount = 0.0
            for idx in indices:
                raw_amount = df.loc[idx, "Amount"]
                amount_value = float(raw_amount) if not pd.isna(raw_amount) else 0.0
                total_amount += amount_value

            if total_amount < self.amount_threshold:
                return

            for idx in indices:
                if idx not in triggered_indices:
                    triggered_indices.add(idx)
                    reasons[idx] = (
                        f"{reason} (chain amount: {total_amount:,.2f}, threshold: {self.amount_threshold:,.2f})"
                    )

        # Build full adjacency maps for all rules
        adjacency_out: dict[str, list[tuple]] = defaultdict(list)
        adjacency_in: dict[str, list[tuple]] = defaultdict(list)
        for _, row in df.iterrows():
            sender = row["Sender_account"]
            receiver = row["Receiver_account"]
            ts = row["Timestamp"]
            idx = row.name
            amount = row["Amount"]

            adjacency_out[sender].append((receiver, ts, idx, amount))
            adjacency_in[receiver].append((sender, ts, idx, amount))

        # ── Linear layering chains ────────────────────────────────────────
        def dfs(
            account: str,
            chain_accounts: list[str],
            chain_indices: list[int],
            last_time,
        ) -> None:
            if len(chain_accounts) >= self.min_chain_length:
                flag_group(
                    chain_indices,
                    (
                        f"Layering chain: {' → '.join(chain_accounts)} "
                        f"({len(chain_accounts)-1} hops within {self.window_hours}h)"
                    ),
                )

            if account not in adjacency_out:
                return

            for next_acc, ts, idx, amount in adjacency_out[account]:
                if pd.isna(ts) or pd.isna(last_time):
                    continue
                time_diff = ts - last_time
                if (
                    timedelta(0) <= time_diff <= window
                    and next_acc not in chain_accounts
                    and (next_acc in passthrough or account in passthrough)
                ):
                    dfs(
                        next_acc,
                        chain_accounts + [next_acc],
                        chain_indices + [idx],
                        ts,
                    )

        for start_account, edges in adjacency_out.items():
            for next_acc, ts, idx, amount in edges:
                if not pd.isna(ts) and next_acc in passthrough:
                    dfs(next_acc, [start_account, next_acc], [idx], ts)

        # ── Fan-out pattern: same sender to many receivers ──────────────────
        if self.detect_fan_out:
            for sender, edges in adjacency_out.items():
                if sender not in passthrough or len(edges) < self.min_fan_degree:
                    continue

                window_edges = sorted(edges, key=lambda item: item[1])
                left = 0
                receiver_counts: Counter = Counter()

                for right, (receiver, ts, idx, amount) in enumerate(window_edges):
                    if pd.isna(ts):
                        continue
                    receiver_counts[receiver] += 1

                    while window_edges[right][1] - window_edges[left][1] > window:
                        old_receiver = window_edges[left][0]
                        receiver_counts[old_receiver] -= 1
                        if receiver_counts[old_receiver] == 0:
                            del receiver_counts[old_receiver]
                        left += 1

                    if len(receiver_counts) >= self.min_fan_degree:
                        indices = [edge[2] for edge in window_edges[left:right + 1]]
                        flag_group(
                            indices,
                            (
                                f"Fan-out: sender {sender} sent to {len(receiver_counts)} distinct receivers "
                                f"within {self.window_hours}h"
                            ),
                        )

        # ── Fan-in pattern: many senders to same receiver ────────────────
        if self.detect_fan_in:
            for receiver, edges in adjacency_in.items():
                if receiver not in passthrough or len(edges) < self.min_fan_degree:
                    continue

                window_edges = sorted(edges, key=lambda item: item[1])
                left = 0
                sender_counts: Counter = Counter()

                for right, (sender, ts, idx, amount) in enumerate(window_edges):
                    if pd.isna(ts):
                        continue
                    sender_counts[sender] += 1

                    while window_edges[right][1] - window_edges[left][1] > window:
                        old_sender = window_edges[left][0]
                        sender_counts[old_sender] -= 1
                        if sender_counts[old_sender] == 0:
                            del sender_counts[old_sender]
                        left += 1

                    if len(sender_counts) >= self.min_fan_degree:
                        indices = [edge[2] for edge in window_edges[left:right + 1]]
                        flag_group(
                            indices,
                            (
                                f"Fan-in: receiver {receiver} received from {len(sender_counts)} distinct senders "
                                f"within {self.window_hours}h"
                            ),
                        )

        # ── Scatter-gather pattern: scatter to intermediates then gather to one account ──
        scatter_min_branches = 2
        for source, out_edges in adjacency_out.items():
            if len(out_edges) < scatter_min_branches:
                continue

            scatter_by_intermediate: dict[str, list[tuple]] = defaultdict(list)
            for receiver, ts, idx, amount in out_edges:
                if receiver in passthrough:
                    scatter_by_intermediate[receiver].append((ts, idx))

            if len(scatter_by_intermediate) < scatter_min_branches:
                continue

            gather_candidates: dict[str, dict[str, list[tuple]]] = defaultdict(lambda: defaultdict(list))
            for intermediate, scatter_edges in scatter_by_intermediate.items():
                if intermediate not in adjacency_out:
                    continue
                for next_receiver, next_ts, next_idx, next_amount in adjacency_out[intermediate]:
                    if next_receiver == source:
                        continue
                    for scatter_ts, scatter_idx in scatter_edges:
                        if pd.isna(next_ts) or pd.isna(scatter_ts):
                            continue
                        delta = next_ts - scatter_ts
                        if timedelta(0) <= delta <= window:
                            gather_candidates[next_receiver][intermediate].append(
                                (scatter_idx, next_idx)
                            )

            for destination, intermediate_map in gather_candidates.items():
                if len(intermediate_map) < scatter_min_branches:
                    continue
                involved_indices: list[int] = []
                for intermediate, pairs in intermediate_map.items():
                    for scatter_idx, next_idx in pairs:
                        involved_indices.extend([scatter_idx, next_idx])
                unique_indices = sorted(set(involved_indices))
                flag_group(
                    unique_indices,
                    (
                        f"Scatter-gather: {source} scattered funds to {len(intermediate_map)} intermediates "
                        f"and they gathered at {destination} within {self.window_hours}h"
                    ),
                )

        log.debug(f"LayeringRule → {len(triggered_indices)} flagged rows")
        return self._result(list(triggered_indices), reasons)
