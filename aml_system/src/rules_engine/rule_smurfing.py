"""
Rule: Smurfing / Structuring Detection
========================================
Smurfing = splitting a large sum into multiple smaller transactions (each
below the reporting threshold) to avoid detection.

Detection logic:
  For each Sender_account, within a rolling time window:
    • Count transactions < individual_threshold
    • If count >= min_transactions AND cumulative amount >= cumulative_threshold
      → flag ALL those transactions
"""

from __future__ import annotations

import pandas as pd

from src.rules_engine.base_rule import BaseRule, RuleResult
from src.utils.logger import get_logger

log = get_logger(__name__)


class SmurfingRule(BaseRule):
    """Detect structuring (smurfing) behaviour across sender accounts."""

    name = "Smurfing"
    description = "Multiple sub-threshold transactions that together exceed the CTR threshold"

    def __init__(self, config: dict):
        super().__init__(config)
        self.window_hours = int(config.get("window_hours", 24))
        self.min_transactions = int(config.get("min_transactions", 3))
        self.individual_threshold = float(config.get("individual_threshold", 9_999))
        self.cumulative_threshold = float(config.get("cumulative_threshold", 10_000))

    def apply(self, df: pd.DataFrame) -> RuleResult:
        if not self.enabled:
            return self._result([], {})

        if "Timestamp" not in df.columns:
            log.warning("Smurfing rule skipped — 'Timestamp' column missing")
            return self._result([], {})

        # Only consider sub-threshold transactions (the "smurfs")
        sub = df[df["Amount"] < self.individual_threshold].copy()
        if sub.empty:
            return self._result([], {})

        sub = sub.sort_values("Timestamp")
        window = pd.Timedelta(hours=self.window_hours)
        triggered_indices: list[int] = []
        reasons: dict[int, str] = {}

        for sender, grp in sub.groupby("Sender_account"):
            grp = grp.sort_values("Timestamp").reset_index()  # keep original index in col 'index'
            times = grp["Timestamp"].values
            amounts = grp["Amount"].values
            orig_indices = grp["index"].values  # original df indices

            # Sliding window O(n) approach
            left = 0
            for right in range(len(grp)):
                # Shrink window from left if too wide
                while (times[right] - times[left]) > window.value:
                    left += 1

                window_slice = slice(left, right + 1)
                count = right - left + 1
                total = amounts[window_slice].sum()

                if count >= self.min_transactions and total >= self.cumulative_threshold:
                    # Flag all transactions in this window
                    for i in range(left, right + 1):
                        idx = int(orig_indices[i])
                        if idx not in triggered_indices:
                            triggered_indices.append(idx)
                            reasons[idx] = (
                                f"Smurfing: account {sender!r} made {count} transactions "
                                f"totalling {total:,.2f} within {self.window_hours}h "
                                f"(each below {self.individual_threshold:,.2f} threshold)"
                            )

        log.debug(f"SmurfingRule → {len(triggered_indices)} flagged rows")
        return self._result(triggered_indices, reasons)
