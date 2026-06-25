"""
Unit tests for customer details enrichment and sanctions screening integration.
"""

import sys
import os
from pathlib import Path
import tempfile
import yaml
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
from src.utils.helpers import reload_config
from src.investigation.customer_profiler import CustomerProfiler
from src.investigation.case_builder import CaseBuilder
from src.alert_generation.alert_manager import Alert


def make_txn_df(rows):
    return pd.DataFrame(rows)


def make_alert(account_id: str, receiver_account: str) -> Alert:
    return Alert(
        alert_id="ALT-TEST",
        txn_id=1,
        timestamp=datetime.now().isoformat(),
        sender_account=account_id,
        receiver_account=receiver_account,
        amount=15000.0,
        payment_currency="USD",
        sender_location="United States",
        receiver_location="United States",
        payment_type="Wire",
        risk_tier="MEDIUM",
        risk_score=25,
        triggered_rules="LargeTransaction",
        rule_reasons="Test reason",
        is_laundering_gt=0,
        laundering_type_gt="",
    )


def test_customer_profile_loads_customer_details_and_enriches_profile():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as detail_file:
        detail_file.write(
            "Customer Id,Account Number,Full Name,Date of Birth,Occupation,Complete Address,Total Income Per Annum,Passport/Gov ID Proof,Is_Flagged,Flag_Type,Flag_Reason,Risk_Category,Risk_Score\n"
            "CUST000001,1234567890,John Doe,01-01-1980,Entrepreneur,1 Main St,500000,Passport: P123456,False,NONE,,CLEAN,5\n"
        )
        detail_path = detail_file.name

    config = {
        "investigation": {
            "cases_dir": "data/outputs/cases",
            "sanctions_file": "config/sanction_list.csv",
            "customer_details_file": detail_path,
            "fuzzy_match_threshold": 85,
            "auto_escalate_tiers": ["CRITICAL"],
            "manual_review_tiers": ["HIGH"],
        }
    }

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as cfg_file:
        yaml.dump(config, cfg_file)
        config_path = cfg_file.name

    try:
        reload_config(config_path)
        df = make_txn_df([
            {
                "Txn_id": 1,
                "Timestamp": datetime(2024, 1, 1),
                "Sender_account": "1234567890",
                "Receiver_account": "9999999999",
                "Amount": 15000.0,
                "Payment_currency": "USD",
                "Received_currency": "USD",
                "Sender_bank_location": "United States",
                "Receiver_bank_location": "United States",
                "Payment_type": "Wire",
                "Is_laundering": 0,
                "Laundering_type": "",
            }
        ])
        profiler = CustomerProfiler(df, config_path=config_path)
        profile = profiler.build_profile("1234567890")

        assert profile.full_name == "John Doe"
        assert profile.government_id == "Passport: P123456"
        assert profile.risk_category == "CLEAN"
        assert profile.risk_score == 5
    finally:
        os.unlink(detail_path)
        os.unlink(config_path)


def test_case_builder_uses_customer_name_in_sanctions_screening():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as detail_file:
        detail_file.write(
            "Customer Id,Account Number,Full Name,Date of Birth,Occupation,Complete Address,Total Income Per Annum,Passport/Gov ID Proof,Is_Flagged,Flag_Type,Flag_Reason,Risk_Category,Risk_Score\n"
            "CUST000001,1234567890,John Doe,01-01-1980,Entrepreneur,1 Main St,500000,Passport: P123456,False,NONE,,CLEAN,5\n"
        )
        detail_path = detail_file.name

    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as watchlist_file:
        watchlist_file.write(
            "entity_name,entity_type,country,list_type,added_date,notes\n"
            "JOHN DOE,Individual,USA,OFAC SDN,2024-01-01,Known sanctioned individual\n"
        )
        watchlist_path = watchlist_file.name

    config = {
        "investigation": {
            "cases_dir": "data/outputs/cases",
            "sanctions_file": watchlist_path,
            "customer_details_file": detail_path,
            "fuzzy_match_threshold": 80,
            "auto_escalate_tiers": ["CRITICAL"],
            "manual_review_tiers": ["HIGH"],
        }
    }

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as cfg_file:
        yaml.dump(config, cfg_file)
        config_path = cfg_file.name

    try:
        reload_config(config_path)
        df = make_txn_df([
            {
                "Txn_id": 1,
                "Timestamp": datetime(2024, 1, 1),
                "Sender_account": "1234567890",
                "Receiver_account": "9999999999",
                "Amount": 15000.0,
                "Payment_currency": "USD",
                "Received_currency": "USD",
                "Sender_bank_location": "United States",
                "Receiver_bank_location": "United States",
                "Payment_type": "Wire",
                "Is_laundering": 0,
                "Laundering_type": "",
            }
        ])
        alert = make_alert("1234567890", "9999999999")
        builder = CaseBuilder(df, config_path=config_path)
        cases = builder.build_cases([alert])

        assert len(cases) == 1
        assert cases[0].sanctions_hits, "Expected sanctions hits from customer name screening"
        assert any("JOHN DOE" in hit["matched_entity"].upper() for hit in cases[0].sanctions_hits)
    finally:
        os.unlink(detail_path)
        os.unlink(watchlist_path)
        os.unlink(config_path)
