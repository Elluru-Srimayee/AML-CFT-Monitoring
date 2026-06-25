"""
Unit tests for the Rules Engine.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
import pytest
from datetime import datetime, timedelta

from src.rules_engine.rule_large_txn import LargeTransactionRule
from src.rules_engine.rule_high_risk_country import HighRiskCountryRule
from src.rules_engine.rule_layering import LayeringRule
from src.rules_engine.rule_smurfing import SmurfingRule


# ── Fixtures ──────────────────────────────────────────────────────────────────

def make_txn_df(rows: list[dict]) -> pd.DataFrame:
    """Helper to create minimal transaction DataFrames for tests."""
    defaults = {
        "Txn_id": 0,
        "Timestamp": datetime(2023, 1, 1),
        "Sender_account": "ACC001",
        "Receiver_account": "ACC002",
        "Amount": 1000.0,
        "Payment_currency": "USD",
        "Received_currency": "USD",
        "Sender_bank_location": "United States",
        "Receiver_bank_location": "United States",
        "Payment_type": "ACH",
        "Is_laundering": 0,
        "Laundering_type": "",
    }
    data = [{**defaults, **row, "Txn_id": i} for i, row in enumerate(rows)]
    return pd.DataFrame(data)


# ── LargeTransactionRule Tests ────────────────────────────────────────────────

class TestLargeTransactionRule:
    config = {"enabled": True, "score": 25, "threshold_usd": 10000}
    rule = LargeTransactionRule(config)

    def test_above_threshold_flagged(self):
        df = make_txn_df([{"Amount": 15000.0}])
        result = self.rule.apply(df)
        assert 0 in result.triggered_indices

    def test_at_threshold_not_flagged(self):
        df = make_txn_df([{"Amount": 10000.0}])
        result = self.rule.apply(df)
        assert 0 not in result.triggered_indices

    def test_below_threshold_not_flagged(self):
        df = make_txn_df([{"Amount": 9999.99}])
        result = self.rule.apply(df)
        assert result.triggered_indices == []

    def test_score_correct(self):
        result = self.rule.apply(make_txn_df([{"Amount": 20000.0}]))
        assert result.score == 25

    def test_reason_contains_amount(self):
        df = make_txn_df([{"Amount": 50000.0}])
        result = self.rule.apply(df)
        assert "50,000.00" in result.reasons.get(0, "")

    def test_multiple_rows(self):
        df = make_txn_df([
            {"Amount": 5000},
            {"Amount": 15000},
            {"Amount": 25000},
        ])
        result = self.rule.apply(df)
        assert 0 not in result.triggered_indices
        assert 1 in result.triggered_indices
        assert 2 in result.triggered_indices

    def test_disabled_rule_returns_empty(self):
        cfg = {**self.config, "enabled": False}
        rule = LargeTransactionRule(cfg)
        df = make_txn_df([{"Amount": 99999}])
        result = rule.apply(df)
        assert result.triggered_indices == []

    def test_currency_specific_thresholds(self):
        cfg = {
            "enabled": True,
            "score": 25,
            "threshold_usd": 10000,
            "thresholds_by_currency": {
                "USD": 10000,
                "Euro": 9000,
                "UK pounds": 8000,
            },
        }
        rule = LargeTransactionRule(cfg)

        df = make_txn_df([{
            "Payment_currency": "Euro",
            "Amount": 9500.0,
        }])
        result = rule.apply(df)
        assert 0 in result.triggered_indices

        df2 = make_txn_df([{
            "Payment_currency": "UK pounds",
            "Amount": 8500.0,
        }])
        result2 = rule.apply(df2)
        assert 0 in result2.triggered_indices

        df3 = make_txn_df([{
            "Payment_currency": "USD",
            "Amount": 9500.0,
        }])
        result3 = rule.apply(df3)
        assert result3.triggered_indices == []


# ── HighRiskCountryRule Tests ─────────────────────────────────────────────────

class TestHighRiskCountryRule:
    config = {
        "enabled": True,
        "score": 30,
        "high_risk_countries": ["Iran", "North Korea", "Myanmar"],
    }
    rule = HighRiskCountryRule(config)

    def test_sender_in_high_risk(self):
        df = make_txn_df([{"Sender_bank_location": "Iran"}])
        result = self.rule.apply(df)
        assert 0 in result.triggered_indices

    def test_receiver_in_high_risk(self):
        df = make_txn_df([{"Receiver_bank_location": "North Korea"}])
        result = self.rule.apply(df)
        assert 0 in result.triggered_indices

    def test_safe_country_not_flagged(self):
        df = make_txn_df([{
            "Sender_bank_location": "United States",
            "Receiver_bank_location": "Germany",
        }])
        result = self.rule.apply(df)
        assert result.triggered_indices == []

    def test_case_insensitive(self):
        df = make_txn_df([{"Sender_bank_location": "IRAN"}])
        result = self.rule.apply(df)
        assert 0 in result.triggered_indices

    def test_both_sides_high_risk(self):
        df = make_txn_df([{
            "Sender_bank_location": "Iran",
            "Receiver_bank_location": "Myanmar",
        }])
        result = self.rule.apply(df)
        assert 0 in result.triggered_indices
        reason = result.reasons.get(0, "")
        assert "sender" in reason.lower()
        assert "receiver" in reason.lower()


# ── CurrencyMismatchRule Tests ────────────────────────────────────────────────



# ── SmurfingRule Tests ────────────────────────────────────────────────────────

class TestSmurfingRule:
    config = {
        "enabled": True,
        "score": 40,
        "window_hours": 24,
        "min_transactions": 3,
        "individual_threshold": 9999,
        "cumulative_threshold": 10000,
    }
    rule = SmurfingRule(config)

    def _make_smurfing_df(self, n: int = 4, amount: float = 3000.0) -> pd.DataFrame:
        base = datetime(2023, 6, 1, 10, 0, 0)
        rows = [
            {
                "Sender_account": "SMURF001",
                "Receiver_account": f"RECV{i:03d}",
                "Amount": amount,
                "Timestamp": base + timedelta(hours=i),
            }
            for i in range(n)
        ]
        return make_txn_df(rows)

    def test_smurfing_detected(self):
        df = self._make_smurfing_df(n=4, amount=2600.0)
        result = self.rule.apply(df)
        assert len(result.triggered_indices) > 0

    def test_single_transaction_no_flag(self):
        df = make_txn_df([{"Amount": 5000, "Sender_account": "SOLO"}])
        result = self.rule.apply(df)
        assert 0 not in result.triggered_indices

    def test_large_individual_not_flagged_by_smurfing(self):
        # Amount > individual threshold should NOT be smurfing (it's a large txn)
        df = self._make_smurfing_df(n=4, amount=12000.0)
        result = self.rule.apply(df)
        assert result.triggered_indices == []  # no sub-threshold txns

    def test_outside_window_not_flagged(self):
        base = datetime(2023, 6, 1, 0, 0, 0)
        rows = [
            {
                "Sender_account": "TIMED001",
                "Amount": 3000.0,
                "Timestamp": base + timedelta(days=i * 2),  # every 2 days
            }
            for i in range(4)
        ]
        df = make_txn_df(rows)
        result = self.rule.apply(df)
        assert result.triggered_indices == []


class TestLayeringRule:
    config = {
        "enabled": True,
        "score": 35,
        "window_hours": 72,
        "min_chain_length": 3,
        "min_fan_degree": 3,
    }
    rule = LayeringRule(config)

    def test_linear_chain_flags_origin_edge(self):
        base = datetime(2023, 1, 1, 0, 0, 0)
        rows = [
            {
                "Sender_account": "A000",
                "Receiver_account": "B000",
                "Timestamp": base,
            },
            {
                "Sender_account": "B000",
                "Receiver_account": "C000",
                "Timestamp": base + timedelta(hours=1),
            },
            {
                "Sender_account": "C000",
                "Receiver_account": "D000",
                "Timestamp": base + timedelta(hours=2),
            },
        ]
        df = make_txn_df(rows)
        result = self.rule.apply(df)
        assert set(result.triggered_indices) == {0, 1, 2}
