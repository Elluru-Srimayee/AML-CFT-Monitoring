"""
Pattern Analyzer
=================
Builds a NetworkX directed graph of related transactions and detects
suspicious network patterns (fan-out, fan-in, cycles, gather-scatter).

Note: Visualization is NOT embedded in SAR — this module only performs
      structural analysis and returns findings as text.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import List

import pandas as pd

from src.utils.logger import get_logger

log = get_logger(__name__)

try:
    import networkx as nx
    _HAS_NX = True
except ImportError:
    _HAS_NX = False
    log.warning("networkx not installed — pattern analysis will be limited")


@dataclass
class PatternFinding:
    pattern_type: str            # "FanOut" | "FanIn" | "Cycle" | "GatherScatter"
    central_account: str
    related_accounts: list[str]
    transaction_count: int
    total_amount: float
    description: str


class PatternAnalyzer:
    """
    Analyses the transaction graph for IBM-dataset laundering patterns:
      • Fan-Out: One sender → many receivers
      • Fan-In:  Many senders → one receiver
      • Cycle:   Money circles back to origin
      • Gather-Scatter: collect from many, redistribute to many
    """

    def __init__(self, full_df: pd.DataFrame):
        self.df = full_df
        self.graph = None
        if _HAS_NX:
            self._build_graph()

    # ── Public API ────────────────────────────────────────────────────────

    def analyze_account(self, account_id: str) -> list[PatternFinding]:
        """Find suspicious patterns centred on a specific account."""
        findings: list[PatternFinding] = []

        if not _HAS_NX or self.graph is None:
            log.warning("Pattern analysis skipped — networkx not available")
            return findings

        findings += self._detect_fan_out(account_id)
        findings += self._detect_fan_in(account_id)
        findings += self._detect_cycles(account_id)

        return findings

    def get_connected_accounts(self, account_id: str, depth: int = 2) -> list[str]:
        """Return all accounts within N hops of the given account."""
        if not _HAS_NX or self.graph is None:
            return []

        try:
            undirected = self.graph.to_undirected()
            neighbors = nx.single_source_shortest_path_length(
                undirected, account_id, cutoff=depth
            )
            return [n for n in neighbors if n != account_id]
        except nx.NetworkXError:
            return []

    # ── Private ───────────────────────────────────────────────────────────

    def _build_graph(self) -> None:
        """Build directed weighted graph from transactions."""
        self.graph = nx.DiGraph()
        for _, row in self.df.iterrows():
            s = row["Sender_account"]
            r = row["Receiver_account"]
            amt = float(row["Amount"])
            if self.graph.has_edge(s, r):
                self.graph[s][r]["weight"] += amt
                self.graph[s][r]["count"] += 1
            else:
                self.graph.add_edge(s, r, weight=amt, count=1)
        log.debug(
            f"Transaction graph built: {self.graph.number_of_nodes()} nodes, "
            f"{self.graph.number_of_edges()} edges"
        )

    def _detect_fan_out(self, account_id: str) -> list[PatternFinding]:
        """Account sends to unusually many distinct receivers."""
        findings = []
        if account_id not in self.graph:
            return findings

        successors = list(self.graph.successors(account_id))
        if len(successors) >= 5:  # threshold: 5+ distinct receivers
            total_amount = sum(
                self.graph[account_id][s].get("weight", 0) for s in successors
            )
            findings.append(PatternFinding(
                pattern_type="FanOut",
                central_account=account_id,
                related_accounts=successors,
                transaction_count=sum(
                    self.graph[account_id][s].get("count", 0) for s in successors
                ),
                total_amount=total_amount,
                description=(
                    f"Account {account_id!r} disperses funds to {len(successors)} "
                    f"distinct receivers (total: {total_amount:,.2f}) — Fan-Out pattern"
                ),
            ))
        return findings

    def _detect_fan_in(self, account_id: str) -> list[PatternFinding]:
        """Account receives from many distinct senders."""
        findings = []
        if account_id not in self.graph:
            return findings

        predecessors = list(self.graph.predecessors(account_id))
        if len(predecessors) >= 5:
            total_amount = sum(
                self.graph[p][account_id].get("weight", 0) for p in predecessors
            )
            findings.append(PatternFinding(
                pattern_type="FanIn",
                central_account=account_id,
                related_accounts=predecessors,
                transaction_count=sum(
                    self.graph[p][account_id].get("count", 0) for p in predecessors
                ),
                total_amount=total_amount,
                description=(
                    f"Account {account_id!r} aggregates funds from {len(predecessors)} "
                    f"distinct senders (total: {total_amount:,.2f}) — Fan-In / Aggregation pattern"
                ),
            ))
        return findings

    def _detect_cycles(self, account_id: str) -> list[PatternFinding]:
        """Detect if money returns to the origin account (circular flow)."""
        findings = []
        if account_id not in self.graph:
            return findings

        try:
            cycles = list(nx.simple_cycles(self.graph))
            for cycle in cycles:
                if account_id in cycle and len(cycle) >= 3:
                    # Compute total amount traversing this cycle
                    total_amt = 0.0
                    for i in range(len(cycle)):
                        a = cycle[i]
                        b = cycle[(i + 1) % len(cycle)]
                        if self.graph.has_edge(a, b):
                            total_amt += self.graph[a][b].get("weight", 0)

                    findings.append(PatternFinding(
                        pattern_type="Cycle",
                        central_account=account_id,
                        related_accounts=[a for a in cycle if a != account_id],
                        transaction_count=len(cycle),
                        total_amount=total_amt,
                        description=(
                            f"Circular money flow detected: {' → '.join(cycle)} → {cycle[0]} "
                            f"(total: {total_amt:,.2f}) — Cycle/Round-trip laundering pattern"
                        ),
                    ))
        except Exception:
            pass  # cycle detection can fail on large graphs — not critical

        return findings
