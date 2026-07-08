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
        self.score_tiers = self._parse_score_tiers(config.get("score_tiers", {}))

    def _parse_score_tiers(self, config_tiers: dict | list | None) -> list[tuple[float, int]]:
        if isinstance(config_tiers, dict):
            return sorted(((float(k), int(v)) for k, v in config_tiers.items()), key=lambda item: item[0])
        if isinstance(config_tiers, list):
            tiers = []
            for item in config_tiers:
                if isinstance(item, dict):
                    try:
                        tiers.append((float(item.get("multiplier", 0)), int(item.get("score", 0))))
                    except (TypeError, ValueError):
                        continue
            return sorted(tiers, key=lambda item: item[0])
        return []

    def _threshold_for_currency(self, currency: str) -> float:
        return self.thresholds_by_currency.get(str(currency).strip().upper(), self.default_threshold)

    def apply(self, df: pd.DataFrame) -> RuleResult:
        if not self.enabled:
            return self._result([], {})

        payment_currency = df["Payment_currency"].astype(str).str.upper().str.strip()
        thresholds = payment_currency.map(self._threshold_for_currency)
        mask = df["Amount"] > thresholds
        triggered = df.index[mask].tolist()

        reasons = {}
        score_map: dict[int, int] = {}

        for idx in triggered:
            amount = float(df.at[idx, "Amount"])
            threshold = float(thresholds.at[idx])
            multiplier = amount / threshold if threshold > 0 else 0.0
            if self.score_tiers:
                score_value = self.score
                for tier_multiplier, tier_score in self.score_tiers:
                    if multiplier >= tier_multiplier:
                        score_value = tier_score
                    else:
                        break
                score_map[idx] = int(score_value)
                reasons[idx] = (
                    f"Transaction amount {amount:,.2f} {df.at[idx, 'Payment_currency']} "
                    f"exceeds threshold of {threshold:,.2f} (x{multiplier:.2f}) -> +{score_value} pts"
                )
            else:
                score_map[idx] = int(self.score)
                reasons[idx] = (
                    f"Transaction amount {amount:,.2f} {df.at[idx, 'Payment_currency']} exceeds threshold "
                    f"of {threshold:,.2f}"
                )

        return self._result(triggered, reasons, score_map if self.score_tiers else self.score)
