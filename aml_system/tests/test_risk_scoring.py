"""
Unit tests for the Risk Scorer.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
import pytest

from src.risk_scoring.scorer import RiskScorer


def make_scored_df(scores: list[int], gt_laundering: list[int] | None = None) -> pd.DataFrame:
    """Create a minimal scored DataFrame for testing."""
    n = len(scores)
    data = {
        "total_risk_score": scores,
        "Is_laundering": gt_laundering if gt_laundering else [0] * n,
    }
    return pd.DataFrame(data)


# Mock config for scorer
MOCK_CONFIG = {
    "ingestion": {"chunk_size": 50000, "date_format": "%Y/%m/%d", "time_format": "%H:%M:%S",
                  "input_file": "data/raw/transactions.csv", "processed_file": "data/processed/x.parquet"},
    "rules": {
        "large_transaction": {"enabled": True, "threshold_usd": 10000, "score": 25},
        "high_risk_country": {"enabled": True, "score": 30, "high_risk_countries": []},
        "smurfing": {"enabled": True, "score": 40, "window_hours": 24, "min_transactions": 3,
                     "individual_threshold": 9999, "cumulative_threshold": 10000},
        "layering": {"enabled": True, "score": 35, "window_hours": 72, "min_chain_length": 3},
        "rapid_movement": {"enabled": True, "score": 20, "window_hours": 24, "passthrough_pct": 0.80},
        "currency_mismatch": {"enabled": True, "score": 15},
    },
    "risk_scoring": {
        "tiers": {"LOW": [0, 30], "MEDIUM": [31, 59], "HIGH": [60, 79], "CRITICAL": [80, 999]},
        "alert_threshold": "MEDIUM",
    },
    "alerts": {"output_file": "data/outputs/alerts/alerts.csv", "excel_report": "data/outputs/alerts/alert_report.xlsx",
                "dedup_window_hours": 48},
    "investigation": {"cases_dir": "data/outputs/cases", "sanctions_file": "config/sanction_list.csv",
                      "fuzzy_match_threshold": 85, "auto_escalate_tiers": ["CRITICAL"],
                      "manual_review_tiers": ["HIGH"]},
    "sar": {"template_pdf": "reports/templates/SAR_template.pdf", "output_dir": "data/outputs/sar",
            "filing_institution": "Test Bank", "filing_institution_address": "1 Test St",
            "filing_institution_tin": "XX", "contact_name": "Test User",
            "contact_phone": "+1", "contact_email": "test@test.com"},
    "logging": {"level": "INFO", "log_file": "data/outputs/aml_system.log"},
}


class TestRiskScorer:
    def _make_scorer(self):
        """Create scorer with mock config written to a temp file."""
        import tempfile, yaml, os
        import src.utils.helpers as helpers_mod
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(MOCK_CONFIG, f)
            config_path = f.name
        helpers_mod.reload_config(config_path)
        scorer = RiskScorer(config_path=config_path)
        os.unlink(config_path)
        helpers_mod.reload_config("config/config.yaml")
        return scorer

    def test_low_tier_assigned(self):
        scorer = self._make_scorer()
        df = make_scored_df([0, 15, 30])
        result = scorer.assign_tiers(df)
        assert all(result["risk_tier"] == "LOW")

    def test_medium_tier_assigned(self):
        scorer = self._make_scorer()
        df = make_scored_df([31, 45, 59])
        result = scorer.assign_tiers(df)
        assert all(result["risk_tier"] == "MEDIUM")

    def test_high_tier_assigned(self):
        scorer = self._make_scorer()
        df = make_scored_df([60, 70, 79])
        result = scorer.assign_tiers(df)
        assert all(result["risk_tier"] == "HIGH")

    def test_critical_tier_assigned(self):
        scorer = self._make_scorer()
        df = make_scored_df([80, 100, 200])
        result = scorer.assign_tiers(df)
        assert all(result["risk_tier"] == "CRITICAL")

    def test_is_flagged_low_not_flagged(self):
        scorer = self._make_scorer()
        df = make_scored_df([10, 20])
        result = scorer.assign_tiers(df)
        assert not result["is_flagged"].any()

    def test_is_flagged_medium_flagged(self):
        scorer = self._make_scorer()
        df = make_scored_df([40, 55])
        result = scorer.assign_tiers(df)
        assert result["is_flagged"].all()

    def test_is_flagged_critical_flagged(self):
        scorer = self._make_scorer()
        df = make_scored_df([95])
        result = scorer.assign_tiers(df)
        assert result["is_flagged"].iloc[0]

    def test_evaluate_perfect_precision_recall(self):
        scorer = self._make_scorer()
        df = make_scored_df([80, 80, 10, 10], gt_laundering=[1, 1, 0, 0])
        scored = scorer.assign_tiers(df)
        metrics = scorer.evaluate(scored)
        assert metrics["precision"] == 1.0
        assert metrics["recall"] == 1.0
        assert metrics["f1_score"] == 1.0

    def test_evaluate_all_false_positives(self):
        scorer = self._make_scorer()
        df = make_scored_df([80, 80], gt_laundering=[0, 0])
        scored = scorer.assign_tiers(df)
        metrics = scorer.evaluate(scored)
        assert metrics["precision"] == 0.0
        assert metrics["recall"] == 0.0

    def test_missing_score_column_raises(self):
        scorer = self._make_scorer()
        df = pd.DataFrame({"Amount": [100, 200]})
        with pytest.raises(ValueError, match="total_risk_score"):
            scorer.assign_tiers(df)
