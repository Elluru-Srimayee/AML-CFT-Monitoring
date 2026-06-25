"""
SAR Generator
=============
Builds a structured SAR (Suspicious Activity Report) data model
from an InvestigationCase. Produces a flat dict of field values
ready for PDF template injection.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from src.investigation.case_builder import InvestigationCase
from src.utils.helpers import (
    format_currency,
    format_date,
    generate_sar_id,
    load_config,
    now_utc,
)
from src.utils.logger import get_logger

log = get_logger(__name__)


@dataclass
class SARData:
    """Flat representation of all fields in the SAR form."""

    # SAR metadata
    sar_id: str
    filing_date: str
    report_type: str = "Suspicious Activity Report"

    # Filing institution
    filing_institution: str = ""
    filing_institution_address: str = ""
    filing_institution_tin: str = ""
    contact_name: str = ""
    contact_phone: str = ""
    contact_email: str = ""

    # Subject of the report
    subject_account: str = ""
    subject_bank: str = ""
    subject_location: str = ""

    # Activity summary
    case_id: str = ""
    risk_tier: str = ""
    risk_score: str = ""
    triggered_rules: str = ""
    activity_type: str = ""

    # Transaction details
    transaction_date_start: str = ""
    transaction_date_end: str = ""
    total_transactions: str = ""
    total_amount: str = ""
    countries_involved: str = ""
    payment_types: str = ""

    # Sanctions
    sanctions_hits: str = ""

    # Narrative
    narrative: str = ""

    # Investigator sign-off
    investigator_name: str = "AML System (Automated)"
    investigator_date: str = ""
    investigator_title: str = "Compliance Analyst"

    def to_dict(self) -> dict[str, str]:
        """Return all fields as a string dict for PDF form injection."""
        from dataclasses import asdict
        return {k: str(v) for k, v in asdict(self).items()}


class SARGenerator:
    """
    Converts an InvestigationCase into a SARData object.

    Usage:
        gen = SARGenerator()
        sar = gen.generate(case)
    """

    def __init__(self, config_path: str = "config/config.yaml"):
        cfg = load_config(config_path)
        sar_cfg = cfg["sar"]
        self.institution = sar_cfg.get("filing_institution", "Financial Institution")
        self.institution_address = sar_cfg.get("filing_institution_address", "")
        self.institution_tin = sar_cfg.get("filing_institution_tin", "")
        self.contact_name = sar_cfg.get("contact_name", "")
        self.contact_phone = sar_cfg.get("contact_phone", "")
        self.contact_email = sar_cfg.get("contact_email", "")

    def generate(self, case: InvestigationCase) -> SARData:
        """Build a SARData from a fully assembled InvestigationCase."""
        now = now_utc()

        # Derive activity type from triggered rules
        rules = case.triggered_rules
        activity_types = []
        rule_to_activity = {
            "Smurfing":         "Structuring / Smurfing",
            "Layering":         "Layering",
            "LargeTransaction": "Large Cash Transaction",
            "HighRiskCountry":  "High-Risk Jurisdiction Transaction",
            "RapidMovement":    "Rapid Fund Movement (Money Mule)",
            "CurrencyMismatch": "Foreign Exchange Layering",
        }
        for rule in rules:
            if rule in rule_to_activity:
                activity_types.append(rule_to_activity[rule])

        activity_desc = "; ".join(activity_types) if activity_types else "Suspicious Activity"

        # Sanctions summary
        if case.sanctions_hits:
            sanctions_text = "; ".join(
                f"{h['query']} → {h['matched_entity']} ({h['list_type']})"
                for h in case.sanctions_hits
            )
        else:
            sanctions_text = "No watchlist matches identified"

        # Customer profile derived fields
        profile = case.customer_profile
        subject_bank = profile.get("countries_involved", [])
        payment_types = ", ".join(profile.get("payment_types_used", []))

        sar = SARData(
            sar_id=generate_sar_id(),
            filing_date=format_date(now),
            filing_institution=self.institution,
            filing_institution_address=self.institution_address,
            filing_institution_tin=self.institution_tin,
            contact_name=self.contact_name,
            contact_phone=self.contact_phone,
            contact_email=self.contact_email,
            subject_account=case.subject_account,
            subject_bank=", ".join(subject_bank[:3]) if subject_bank else "N/A",
            subject_location=", ".join(case.countries_involved[:5]) if case.countries_involved else "N/A",
            case_id=case.case_id,
            risk_tier=case.risk_tier,
            risk_score=str(case.risk_score),
            triggered_rules=", ".join(case.triggered_rules),
            activity_type=activity_desc,
            transaction_date_start=case.date_range_start[:10] if case.date_range_start else "N/A",
            transaction_date_end=case.date_range_end[:10] if case.date_range_end else "N/A",
            total_transactions=str(case.transaction_count),
            total_amount=format_currency(case.total_amount),
            countries_involved=", ".join(case.countries_involved) if case.countries_involved else "N/A",
            payment_types=payment_types or "N/A",
            sanctions_hits=sanctions_text,
            narrative=case.narrative,
            investigator_date=format_date(now),
        )

        log.info(
            f"SAR generated — ID: {sar.sar_id} | Case: {case.case_id} | "
            f"Account: {case.subject_account} | Tier: {case.risk_tier}"
        )
        return sar
