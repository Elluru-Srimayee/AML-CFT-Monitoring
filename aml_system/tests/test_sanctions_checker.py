"""
Unit tests for the Sanctions Checker.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.investigation.sanctions_checker import SanctionsChecker
from src.utils.helpers import reload_config


def test_sanctions_checker_loads_primary_name_list():
    reload_config("config/config.yaml")
    checker = SanctionsChecker(config_path="config/config.yaml")
    assert checker._watchlist_df is not None
    assert len(checker._watchlist) > 0
    assert "PRIMARY_NAME" in [c.upper() for c in checker._watchlist_df.columns]


def test_sanctions_checker_matches_primary_name():
    reload_config("config/config.yaml")
    checker = SanctionsChecker(config_path="config/config.yaml")
    hits = checker.check_accounts(["Abdul Hamid Al-Yemeni"])
    assert hits, "Expected a sanction match for Primary_Name"
    assert "ABDUL HAMID AL-YEMENI" in hits[0]["matched_entity"].upper()
