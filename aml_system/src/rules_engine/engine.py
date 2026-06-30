"""
Rules Engine Orchestrator
==========================
Loads all rules from config and applies them to the transaction DataFrame.
Returns a per-transaction DataFrame with individual rule scores and reasons.
"""

from __future__ import annotations

import pandas as pd
from tqdm import tqdm

from src.rules_engine.base_rule import RuleResult
from src.rules_engine.rule_high_risk_country import HighRiskCountryRule
from src.rules_engine.rule_large_txn import LargeTransactionRule
from src.rules_engine.rule_layering import LayeringRule
from src.rules_engine.rule_rapid_movement import RapidMovementRule
from src.rules_engine.rule_smurfing import SmurfingRule
from src.utils.helpers import load_config
from src.utils.logger import get_logger
from src.rules_engine.rule_cash_business_ai import CashBusinessAIRule

log = get_logger(__name__)


class RulesEngine:
    """
    Orchestrates all AML detection rules and assembles the rule scores
    into a per-transaction annotation DataFrame.

    Usage:
        engine = RulesEngine()
        scored_df = engine.run(df)       # df from TransactionLoader
    """

    def __init__(self, config_path: str = "config/config.yaml"):
        cfg = load_config(config_path)
        rules_cfg = cfg["rules"]

        # ── Instantiate all rules ─────────────────────────────────────
        self.rules = [
            LargeTransactionRule(rules_cfg["large_transaction"]),
            HighRiskCountryRule(rules_cfg["high_risk_country"]),
            # CurrencyMismatchRule(rules_cfg["currency_mismatch"]),
            SmurfingRule(rules_cfg["smurfing"]),
            LayeringRule(rules_cfg["layering"]),
            RapidMovementRule(rules_cfg["rapid_movement"]),
            CashBusinessAIRule(rules_cfg["cash_business_ai"]),
        ]

        enabled = [r.name for r in self.rules if r.enabled]
        log.info(f"Rules engine initialised with {len(enabled)} enabled rules: {enabled}")

    # ── Public API ────────────────────────────────────────────────────────

    def run(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Apply all rules to the DataFrame and return an annotated copy.

        Added columns per rule:
          rule_<RuleName>          — bool: whether this rule triggered
          rule_<RuleName>_reason   — str: human-readable reason

        Additional summary columns:
          total_risk_score         — int: sum of all triggered rule scores
          triggered_rules          — str: pipe-separated list of triggered rule names
          rule_reasons             — str: concatenated reasons

        Args:
            df: Cleaned transaction DataFrame.

        Returns:
            Annotated DataFrame (same rows, additional columns).
        """
        result_df = df.copy()

        # Initialise score and meta columns
        result_df["total_risk_score"] = 0
        result_df["triggered_rules"] = ""
        result_df["rule_reasons"] = ""

        for rule in tqdm(self.rules, desc="Applying rules", unit="rule"):
            if not rule.enabled:
                log.debug(f"Skipping disabled rule: {rule.name}")
                continue

            log.info(f"Applying rule: {rule.name} …")
            rule_result: RuleResult = rule.apply(result_df)

            col_flag = f"rule_{rule.name}"
            col_reason = f"rule_{rule.name}_reason"

            result_df[col_flag] = False
            result_df[col_reason] = ""

            if rule_result.triggered_indices:
                valid_indices = [i for i in rule_result.triggered_indices if i in result_df.index]
                result_df.loc[valid_indices, col_flag] = True
                result_df.loc[valid_indices, "total_risk_score"] += rule_result.score

                for idx in valid_indices:
                    reason = rule_result.reasons.get(idx, rule.description)
                    result_df.at[idx, col_reason] = reason

                    # Append to triggered_rules
                    existing = result_df.at[idx, "triggered_rules"]
                    result_df.at[idx, "triggered_rules"] = (
                        f"{existing}|{rule.name}" if existing else rule.name
                    )

                    # Append to rule_reasons
                    existing_r = result_df.at[idx, "rule_reasons"]
                    result_df.at[idx, "rule_reasons"] = (
                        f"{existing_r}; {reason}" if existing_r else reason
                    )

                log.info(
                    f"  ✓ {rule.name}: {len(valid_indices):,} transactions flagged "
                    f"(+{rule_result.score} pts each)"
                )
            else:
                log.info(f"  ✓ {rule.name}: 0 transactions flagged")

        total_flagged = (result_df["total_risk_score"] > 0).sum()
        log.info(
            f"Rules engine complete — {total_flagged:,} / {len(result_df):,} "
            f"transactions scored > 0"
        )
        return result_df

    def summary(self, scored_df: pd.DataFrame) -> dict:
        """Return per-rule trigger counts as a summary dict."""
        summary = {}
        for rule in self.rules:
            col = f"rule_{rule.name}"
            if col in scored_df.columns:
                summary[rule.name] = int(scored_df[col].sum())
        return summary
