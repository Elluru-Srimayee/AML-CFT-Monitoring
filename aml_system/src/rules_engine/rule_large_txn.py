"""Rule: Large Transaction Detection."""

import pandas as pd

from src.rules_engine.base_rule import BaseRule, RuleResult


class LargeTransactionRule(BaseRule):
    """
    Flag any single transaction that exceeds the configured threshold for its currency.

    This allows the system to use different reporting thresholds for USD,
    EUR, GBP, and other currencies instead of a single global amount.
    """

    name = "LargeTransaction"
    description = "Single transaction exceeds the reporting threshold"

    def __init__(self, config: dict):
        super().__init__(config)
        self.default_threshold = float(config.get("threshold_usd", 20_000))
        self.thresholds_by_currency = {
            str(k).strip().upper(): float(v)
            for k, v in config.get("thresholds_by_currency", {}).items()
        }

    def _threshold_for_currency(self, currency: str) -> float:
        return self.thresholds_by_currency.get(str(currency).strip().upper(), self.default_threshold)

    def apply(self, df: pd.DataFrame) -> RuleResult:
        if not self.enabled:
            return self._result([], {})

        payment_currency = df["Payment_currency"].astype(str).str.upper().str.strip()
        thresholds = payment_currency.map(self._threshold_for_currency)
        mask = df["Amount"] > thresholds
        triggered = df.index[mask].tolist()

        reasons = {
            idx: (
                f"Transaction amount {df.at[idx, 'Amount']:,.2f} "
                f"{df.at[idx, 'Payment_currency']} exceeds threshold "
                f"of {thresholds.at[idx]:,.2f}"
            )
            for idx in triggered
        }

        return self._result(triggered, reasons)
