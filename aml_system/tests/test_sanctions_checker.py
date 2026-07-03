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


def test_sanctions_checker_matches_alias_beyond_primary_row_count():
    reload_config("config/config.yaml")
    checker = SanctionsChecker(config_path="config/config.yaml")
    # Validate alias matching for entries whose alias position is beyond the dataframe row count.
    later_alias = None
    for idx, name in enumerate(checker._watchlist):
        if idx >= len(checker._watchlist_df):
            later_alias = name
            break
    assert later_alias is not None, "Expected at least one alias entry beyond DataFrame row count"
    hits = checker.check_accounts([later_alias])
    assert hits, f"Expected a sanction match for alias {later_alias}"
    assert hits[0]["matched_entity"], "Expected matched_entity in the result"
