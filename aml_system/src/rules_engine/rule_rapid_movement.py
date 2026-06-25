"""
Rule: Rapid Fund Movement Detection
=====================================
Detects accounts that receive funds and quickly re-send a large portion
within a short time window — a hallmark of money mule accounts.

Detection logic:
  For each account A:
    • Find all transactions where A is Receiver (incoming)
    • For each incoming txn at time T, find outgoing txns from A within window_hours
    • If sum(outgoing) / sum(incoming) >= passthrough_pct → flag all those txns
"""

from __future__ import annotations

from datetime import timedelta

import pandas as pd

from src.rules_engine.base_rule import BaseRule, RuleResult
from src.utils.logger import get_logger

log = get_logger(__name__)


class RapidMovementRule(BaseRule):
    """Detect pass-through money mule behaviour."""

    name = "RapidMovement"
    description = "Account receives funds and re-sends 80%+ within 24 hours (money mule pattern)"

    def __init__(self, config: dict):
        super().__init__(config)
        self.window_hours = int(config.get("window_hours", 24))
        self.passthrough_pct = float(config.get("passthrough_pct", 0.80))

    def apply(self, df: pd.DataFrame) -> RuleResult:
        if not self.enabled:
            return self._result([], {})

        if "Timestamp" not in df.columns:
            log.warning("RapidMovement rule skipped — 'Timestamp' column missing")
            return self._result([], {})

        window = timedelta(hours=self.window_hours)
        triggered_indices: set[int] = set()
        reasons: dict[int, str] = {}

        # Build lookup: account → sorted list of (timestamp, amount, idx, direction)
        incoming_by_account: dict[str, list] = {}
        outgoing_by_account: dict[str, list] = {}

        for idx, row in df.iterrows():
            ts = row["Timestamp"]
            if pd.isna(ts):
                continue
            amt = row["Amount"]
            recv = row["Receiver_account"]
            send = row["Sender_account"]

            if recv not in incoming_by_account:
                incoming_by_account[recv] = []
            incoming_by_account[recv].append((ts, amt, idx))

            if send not in outgoing_by_account:
                outgoing_by_account[send] = []
            outgoing_by_account[send].append((ts, amt, idx))

        # Only check accounts that both receive AND send
        candidate_accounts = set(incoming_by_account) & set(outgoing_by_account)

        for account in candidate_accounts:
            inbound = sorted(incoming_by_account[account], key=lambda x: x[0])
            outbound = sorted(outgoing_by_account[account], key=lambda x: x[0])

            for in_ts, in_amt, in_idx in inbound:
                # Find outgoing txns within window AFTER this inbound txn
                out_in_window = [
                    (out_ts, out_amt, out_idx)
                    for out_ts, out_amt, out_idx in outbound
                    if timedelta(0) <= (out_ts - in_ts) <= window
                ]

                if not out_in_window:
                    continue

                total_out = sum(amt for _, amt, _ in out_in_window)
                ratio = total_out / in_amt if in_amt > 0 else 0

                if ratio >= self.passthrough_pct:
                    # Flag the incoming and all outgoing transactions
                    triggered_indices.add(in_idx)
                    reasons[in_idx] = (
                        f"RapidMovement: account {account!r} received "
                        f"{in_amt:,.2f} then re-sent {total_out:,.2f} "
                        f"({ratio*100:.1f}%) within {self.window_hours}h"
                    )
                    for _, _, out_idx in out_in_window:
                        triggered_indices.add(out_idx)
                        reasons[out_idx] = (
                            f"RapidMovement: part of rapid fund re-dispatch from account {account!r}"
                        )

        log.debug(f"RapidMovementRule → {len(triggered_indices)} flagged rows")
        return self._result(list(triggered_indices), reasons)
