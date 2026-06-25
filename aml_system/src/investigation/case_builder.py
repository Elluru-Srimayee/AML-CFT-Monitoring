"""
Case Builder
=============
Groups related alerts into Investigation Cases and enriches them
with customer profiles, sanctions hits, and pattern findings.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import List, Optional

import pandas as pd

from src.alert_generation.alert_manager import Alert
from src.investigation.customer_profiler import CustomerProfile, CustomerProfiler
from src.investigation.pattern_analyzer import PatternFinding, PatternAnalyzer
from src.investigation.sanctions_checker import SanctionsChecker
from src.utils.helpers import (
    generate_case_id,
    load_config,
    now_utc,
    ensure_dir,
    format_currency,
)
from src.utils.logger import get_logger

log = get_logger(__name__)


@dataclass
class InvestigationCase:
    """A fully assembled investigation case for one flagged account."""
    case_id: str
    created_at: str
    status: str                          # OPEN | FALSE_POSITIVE | ESCALATED

    # Primary subject
    subject_account: str
    risk_tier: str
    risk_score: int
    triggered_rules: list[str]

    # Supporting evidence
    alerts: list[dict] = field(default_factory=list)
    customer_profile: dict = field(default_factory=dict)
    sanctions_hits: list[dict] = field(default_factory=list)
    pattern_findings: list[str] = field(default_factory=list)  # description strings

    # Transaction summary
    transaction_count: int = 0
    total_amount: float = 0.0
    date_range_start: str = ""
    date_range_end: str = ""
    countries_involved: list[str] = field(default_factory=list)

    # Investigator notes
    narrative: str = ""
    recommendation: str = ""          # "CLOSE" | "SAR" | "MONITOR"


class CaseBuilder:
    """
    Builds InvestigationCase objects from grouped alerts.
    Enriches each case with profiling, sanctions, and pattern findings.
    """

    def __init__(
        self,
        full_df: pd.DataFrame,
        config_path: str = "config/config.yaml",
    ):
        cfg = load_config(config_path)
        inv_cfg = cfg["investigation"]
        self.cases_dir = Path(inv_cfg["cases_dir"])
        self.auto_escalate_tiers = set(inv_cfg.get("auto_escalate_tiers", ["CRITICAL"]))

        self.profiler = CustomerProfiler(full_df, config_path=config_path)
        self.analyzer = PatternAnalyzer(full_df)
        self.sanctions = SanctionsChecker(config_path)

    # ── Public API ────────────────────────────────────────────────────────

    def build_cases(self, alerts: list[Alert]) -> list[InvestigationCase]:
        """
        Build one InvestigationCase per unique Sender_account across all alerts.

        Args:
            alerts: All alerts from AlertManager.create_alerts()

        Returns:
            List of InvestigationCase objects (one per subject account).
        """
        # Group alerts by sender account
        by_account: dict[str, list[Alert]] = {}
        for alert in alerts:
            by_account.setdefault(alert.sender_account, []).append(alert)

        cases: list[InvestigationCase] = []
        log.info(f"Building {len(by_account)} cases from {len(alerts)} alerts …")

        for account, acct_alerts in by_account.items():
            case = self._build_single_case(account, acct_alerts)
            cases.append(case)

        escalated = sum(1 for c in cases if c.status == "ESCALATED")
        log.info(
            f"Case building complete — {len(cases)} cases | "
            f"{escalated} auto-escalated to SAR"
        )
        return cases

    def save_cases(self, cases: list[InvestigationCase]) -> None:
        """Persist each case as a JSON file in the cases directory."""
        ensure_dir(self.cases_dir)
        for case in cases:
            path = self.cases_dir / f"{case.case_id}.json"
            with open(path, "w", encoding="utf-8") as f:
                json.dump(asdict(case), f, indent=2, default=str)
        log.info(f"Saved {len(cases)} case files → {self.cases_dir}")

    def load_case(self, case_id: str) -> dict:
        path = self.cases_dir / f"{case_id}.json"
        if not path.exists():
            raise FileNotFoundError(f"Case not found: {case_id}")
        with open(path, "r") as f:
            return json.load(f)

    def get_sar_candidates(self, cases: list[InvestigationCase]) -> list[InvestigationCase]:
        """Return cases that should generate a SAR."""
        return [c for c in cases if c.status == "ESCALATED"]

    # ── Private ───────────────────────────────────────────────────────────

    def _build_single_case(
        self,
        account: str,
        alerts: list[Alert],
    ) -> InvestigationCase:
        # Determine highest risk tier across all alerts
        tier_order = ["LOW", "MEDIUM", "HIGH", "CRITICAL"]
        best_tier = max(alerts, key=lambda a: tier_order.index(a.risk_tier)).risk_tier
        max_score = max(a.risk_score for a in alerts)

        # Aggregate triggered rules
        rules = set()
        for a in alerts:
            rules.update(a.triggered_rules.split("|"))
        rules.discard("")

        # Transaction summary
        total_amount = sum(a.amount for a in alerts)
        timestamps = [a.timestamp for a in alerts if a.timestamp]
        date_start = min(timestamps) if timestamps else ""
        date_end = max(timestamps) if timestamps else ""

        # Customer profile
        profile: CustomerProfile = self.profiler.build_profile(account)
        countries = profile.countries_involved

        # Sanctions check — use account, customer details, and related receiver accounts
        entities_to_check = [account]
        if profile.full_name:
            entities_to_check.append(profile.full_name)
        if profile.government_id:
            entities_to_check.append(profile.government_id)
        entities_to_check += [a.receiver_account for a in alerts[:10]]
        # preserve order and uniqueness
        seen = set()
        entities_to_check = [x for x in entities_to_check if x and not (x in seen or seen.add(x))]
        sanctions_hits = self.sanctions.check_accounts(entities_to_check)

        # Pattern findings
        findings = self.analyzer.analyze_account(account)
        finding_descs = [f.description for f in findings]

        # Auto-generate narrative
        narrative = self._generate_narrative(
            account, alerts, profile, sanctions_hits, finding_descs
        )

        # Determine recommendation
        has_sanctions = len(sanctions_hits) > 0
        if best_tier in self.auto_escalate_tiers or has_sanctions:
            status = "ESCALATED"
            recommendation = "SAR"
        elif best_tier == "HIGH":
            status = "OPEN"
            recommendation = "SAR"
        else:
            status = "OPEN"
            recommendation = "MONITOR"

        return InvestigationCase(
            case_id=generate_case_id(),
            created_at=now_utc().isoformat(),
            status=status,
            subject_account=account,
            risk_tier=best_tier,
            risk_score=max_score,
            triggered_rules=sorted(rules),
            alerts=[asdict(a) for a in alerts],
            customer_profile=asdict(profile),
            sanctions_hits=sanctions_hits,
            pattern_findings=finding_descs,
            transaction_count=len(alerts),
            total_amount=total_amount,
            date_range_start=date_start,
            date_range_end=date_end,
            countries_involved=countries,
            narrative=narrative,
            recommendation=recommendation,
        )

    def _generate_narrative(
        self,
        account: str,
        alerts: list[Alert],
        profile: CustomerProfile,
        sanctions_hits: list[dict],
        patterns: list[str],
    ) -> str:
        lines = [
            f"Account {account!r} was flagged by the AML monitoring system based on "
            f"{len(alerts)} alert(s) with a maximum risk score of "
            f"{max(a.risk_score for a in alerts)}.",
            "",
            f"The account has conducted {profile.total_transactions} total transactions "
            f"with a total sent amount of {format_currency(profile.total_sent)} and "
            f"received {format_currency(profile.total_received)}.",
            "",
            f"Geographic exposure: {', '.join(profile.countries_involved) or 'N/A'}.",
        ]

        triggered_rules = set()
        for a in alerts:
            triggered_rules.update(a.triggered_rules.split("|"))
        triggered_rules.discard("")

        if triggered_rules:
            lines += [
                "",
                f"Triggered AML rules: {', '.join(sorted(triggered_rules))}.",
            ]

        if sanctions_hits:
            lines += [
                "",
                f"SANCTIONS MATCH: {len(sanctions_hits)} watchlist hit(s) identified.",
            ]
            for hit in sanctions_hits:
                lines.append(
                    f"  - {hit['query']} matched '{hit['matched_entity']}' "
                    f"(score {hit['score']}, list: {hit['list_type']}, country: {hit['country']})"
                )

        if patterns:
            lines += ["", "Suspicious network patterns detected:"]
            for p in patterns:
                lines.append(f"  - {p}")

        lines += [
            "",
            "Based on the above evidence, this case is recommended for Suspicious Activity "
            "Report (SAR) filing with the relevant regulatory authority.",
        ]

        return "\n".join(lines)
