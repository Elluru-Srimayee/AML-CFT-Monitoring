"""Rule: High-Risk Country Detection."""

import pandas as pd

from src.rules_engine.base_rule import BaseRule, RuleResult


class HighRiskCountryRule(BaseRule):
    """
    Flag transactions where either the sender or receiver bank is located
    in a FATF grey/blacklisted or otherwise high-risk jurisdiction.
    """

    name = "HighRiskCountry"
    description = "Transaction involves a high-risk jurisdiction"

    def __init__(self, config: dict):
        super().__init__(config)
        raw_countries = config.get("high_risk_countries", [])
        # Case-insensitive matching set
        self.high_risk = {c.lower().strip() for c in raw_countries}

    def apply(self, df: pd.DataFrame) -> RuleResult:
        if not self.enabled or not self.high_risk:
            return self._result([], {})

        sender_loc = df["Sender_bank_location"].str.lower().str.strip()
        receiver_loc = df["Receiver_bank_location"].str.lower().str.strip()

        mask = sender_loc.isin(self.high_risk) | receiver_loc.isin(self.high_risk)
        triggered = df.index[mask].tolist()

        reasons: dict[int, str] = {}
        for idx in triggered:
            parts = []
            sl = df.at[idx, "Sender_bank_location"]
            rl = df.at[idx, "Receiver_bank_location"]
            if sl.lower().strip() in self.high_risk:
                parts.append(f"sender in high-risk location '{sl}'")
            if rl.lower().strip() in self.high_risk:
                parts.append(f"receiver in high-risk location '{rl}'")
            reasons[idx] = "High-risk country: " + "; ".join(parts)

        return self._result(triggered, reasons)
