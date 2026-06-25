"""
Unit tests for the SAR Generator.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from dataclasses import asdict

from src.sar_reporting.sar_generator import SARGenerator, SARData
from src.investigation.case_builder import InvestigationCase


MOCK_CONFIG = {
    "ingestion": {"chunk_size": 50000, "date_format": "%Y/%m/%d", "time_format": "%H:%M:%S",
                  "input_file": "data/raw/transactions.csv", "processed_file": "data/processed/transactions_clean.parquet"},
    "rules": {
        "large_transaction": {"enabled": True, "threshold_usd": 10000, "score": 25},
        "high_risk_country": {"enabled": True, "score": 30, "high_risk_countries": []},
        "smurfing": {"enabled": True, "score": 40, "window_hours": 24, "min_transactions": 3,
                     "individual_threshold": 9999, "cumulative_threshold": 10000},
        "layering": {"enabled": True, "score": 35, "window_hours": 72, "min_chain_length": 3},
        "rapid_movement": {"enabled": True, "score": 20, "window_hours": 24, "passthrough_pct": 0.80},
        "currency_mismatch": {"enabled": True, "score": 15},
    },
    "risk_scoring": {"tiers": {"LOW": [0, 30], "MEDIUM": [31, 59], "HIGH": [60, 79], "CRITICAL": [80, 999]},
                     "alert_threshold": "MEDIUM"},
    "alerts": {"output_file": "data/outputs/alerts/alerts.csv", "excel_report": "data/outputs/alerts/alert_report.xlsx",
                "dedup_window_hours": 48},
    "investigation": {"cases_dir": "data/outputs/cases", "sanctions_file": "config/sanction_list.csv",
                      "fuzzy_match_threshold": 85, "auto_escalate_tiers": ["CRITICAL"],
                      "manual_review_tiers": ["HIGH"]},
    "sar": {
        "template_pdf": "reports/templates/SAR_template.pdf",
        "output_dir": "data/outputs/sar",
        "filing_institution": "Test Bank Inc.",
        "filing_institution_address": "1 Test Street",
        "filing_institution_tin": "12-3456789",
        "contact_name": "Jane Doe",
        "contact_phone": "+1-555-1234",
        "contact_email": "aml@testbank.com",
    },
    "logging": {"level": "INFO", "log_file": "data/outputs/aml_system.log"},
}


def make_mock_case(
    subject_account: str = "ACC-TEST-001",
    risk_tier: str = "CRITICAL",
    risk_score: int = 95,
    triggered_rules: list | None = None,
) -> InvestigationCase:
    return InvestigationCase(
        case_id="CASE-TESTABC123",
        created_at="2024-01-01T00:00:00Z",
        status="ESCALATED",
        subject_account=subject_account,
        risk_tier=risk_tier,
        risk_score=risk_score,
        triggered_rules=triggered_rules or ["Smurfing", "LargeTransaction"],
        alerts=[],
        customer_profile={
            "account_id": subject_account,
            "total_transactions": 42,
            "total_sent": 150000.0,
            "total_received": 145000.0,
            "avg_transaction_amount": 3571.43,
            "max_transaction_amount": 9999.0,
            "unique_counterparties": 15,
            "countries_involved": ["United States", "Panama"],
            "payment_types_used": ["Wire", "ACH"],
            "first_seen": "2023-01-01",
            "last_seen": "2023-12-31",
            "laundering_gt_count": 10,
        },
        sanctions_hits=[],
        pattern_findings=["Fan-Out pattern detected: 8 receivers"],
        transaction_count=42,
        total_amount=150000.0,
        date_range_start="2023-01-01T00:00:00",
        date_range_end="2023-12-31T23:59:59",
        countries_involved=["United States", "Panama"],
        narrative="Test narrative.",
        recommendation="SAR",
    )


class TestSARGenerator:
    def _make_generator(self):
        import tempfile, yaml, os
        import src.utils.helpers as helpers_mod
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(MOCK_CONFIG, f)
            config_path = f.name
        helpers_mod.reload_config(config_path)   # clear cache, load temp config
        gen = SARGenerator(config_path=config_path)
        os.unlink(config_path)
        helpers_mod.reload_config("config/config.yaml")  # restore real config
        return gen

    def test_generate_returns_sar_data(self):
        gen = self._make_generator()
        case = make_mock_case()
        sar = gen.generate(case)
        assert isinstance(sar, SARData)

    def test_sar_id_generated(self):
        gen = self._make_generator()
        sar = gen.generate(make_mock_case())
        assert sar.sar_id.startswith("SAR-")
        assert len(sar.sar_id) > 5

    def test_filing_institution_populated(self):
        gen = self._make_generator()
        sar = gen.generate(make_mock_case())
        assert sar.filing_institution == "Test Bank Inc."
        assert sar.contact_email == "aml@testbank.com"

    def test_subject_account_matches_case(self):
        gen = self._make_generator()
        sar = gen.generate(make_mock_case(subject_account="ACCT-XYZ-789"))
        assert sar.subject_account == "ACCT-XYZ-789"

    def test_risk_tier_propagated(self):
        gen = self._make_generator()
        sar = gen.generate(make_mock_case(risk_tier="CRITICAL"))
        assert sar.risk_tier == "CRITICAL"

    def test_activity_type_from_rules(self):
        gen = self._make_generator()
        sar = gen.generate(make_mock_case(triggered_rules=["Smurfing", "Layering"]))
        assert "Structuring" in sar.activity_type or "Smurfing" in sar.activity_type
        assert "Layering" in sar.activity_type

    def test_total_amount_formatted(self):
        gen = self._make_generator()
        sar = gen.generate(make_mock_case())
        assert "150,000.00" in sar.total_amount

    def test_to_dict_all_strings(self):
        gen = self._make_generator()
        sar = gen.generate(make_mock_case())
        d = sar.to_dict()
        for key, val in d.items():
            assert isinstance(val, str), f"Field {key!r} is not a string: {type(val)}"

    def test_no_sanctions_message(self):
        gen = self._make_generator()
        sar = gen.generate(make_mock_case())
        assert "No watchlist" in sar.sanctions_hits

    def test_sanctions_hit_in_sar(self):
        gen = self._make_generator()
        case = make_mock_case()
        case.sanctions_hits = [{
            "query": "ACC-TEST-001",
            "matched_entity": "GLOBAL SHADOW CORP",
            "score": 92,
            "list_type": "OFAC SDN",
            "country": "Iran",
            "entity_type": "Organization",
            "notes": "",
        }]
        sar = gen.generate(case)
        assert "OFAC SDN" in sar.sanctions_hits or "GLOBAL SHADOW" in sar.sanctions_hits
