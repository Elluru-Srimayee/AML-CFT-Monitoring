"""
Rules Engine Orchestrator
==========================
Loads all rules from config and applies them to the transaction DataFrame.
Returns a per-transaction DataFrame with individual rule scores and reasons.

This updated version runs enabled rules in parallel using threads.
"""

from __future__ import annotations

import pandas as pd
from tqdm import tqdm
from concurrent.futures import ThreadPoolExecutor, as_completed
from types import SimpleNamespace
from typing import Dict, Tuple, Any

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

        # parallelism config for rule-level execution
        engine_cfg = cfg.get("engine", {})
        self.max_rule_workers = int(engine_cfg.get("max_rule_workers", 4))

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

        Parallel execution:
          - Enabled rules are executed concurrently using ThreadPoolExecutor.
          - Each rule receives a copy of the input DataFrame (preserves immutability).
          - Exceptions in individual rules are logged and do not stop the engine.

        Added columns per rule:
          rule_<RuleName>          — bool: whether this rule triggered
          rule_<RuleName>_reason   — str: human-readable reason

        Additional summary columns:
          total_risk_score         — int: sum of all triggered rule scores
          triggered_rules          — str: pipe-separated list of triggered rule names
          rule_reasons             — str: concatenated reasons
        """
        result_df = df.copy()

        # Initialise score and meta columns
        result_df["total_risk_score"] = 0
        result_df["triggered_rules"] = ""
        result_df["rule_reasons"] = ""

        # Build list of enabled rules
        enabled_rules = [r for r in self.rules if r.enabled]

        if not enabled_rules:
            log.info("No enabled rules to run.")
            return result_df

        # Submit rules in parallel
        max_workers = min(self.max_rule_workers, len(enabled_rules))
        futures_map: Dict[Any, Any] = {}

        log.info(f"Applying rules in parallel (max_workers={max_workers})")

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            for rule in enabled_rules:
                # Submit rule.apply with a copy of the DataFrame to avoid shared mutations
                futures_map[executor.submit(self._safe_apply, rule, result_df.copy())] = rule

            # Progress bar over the number of rules
            pbar = tqdm(total=len(futures_map), desc="Applying rules", unit="rule")

            # Collect and merge results as they complete
            for future in as_completed(futures_map):
                rule = futures_map[future]
                pbar.update(1)

                try:
                    rule_result: RuleResult = future.result()
                except Exception as exc:
                    # This should not happen because _safe_apply catches exceptions,
                    # but keep a defensive fallback.
                    log.exception(f"Unhandled exception executing rule {rule.name}: {exc}")
                    rule_result = SimpleNamespace(triggered_indices=[], reasons={}, score=0)

                # Merge rule_result into result_df
                self._merge_rule_result(result_df, rule, rule_result)

            pbar.close()

        total_flagged = int((result_df["total_risk_score"] > 0).sum())
        log.info(
            f"Rules engine complete — {total_flagged:,} / {len(result_df):,} "
            f"transactions scored > 0"
        )
        return result_df

    # ── Helpers ──────────────────────────────────────────────────────────

    def _safe_apply(self, rule, df_copy: pd.DataFrame) -> RuleResult:
        """
        Execute rule.apply with exception handling.

        Returns a RuleResult-like object. Exceptions are logged and
        a neutral RuleResult (no triggers, zero score) is returned.
        """
        try:
            log.info(f"Applying rule: {rule.name} …")
            result = rule.apply(df_copy)
            return result
        except Exception as exc:
            log.exception(f"Rule {rule.name} failed: {exc}")
            # Return a neutral result object with expected attributes
            return SimpleNamespace(triggered_indices=[], reasons={}, score=0)

    def _merge_rule_result(self, result_df: pd.DataFrame, rule, rule_result: RuleResult) -> None:
        """
        Merge a single rule's result into the shared result_df.

        This preserves the previous behavior (flags, reasons, totals).
        """
        col_flag = f"rule_{rule.name}"
        col_reason = f"rule_{rule.name}_reason"

        # Ensure columns exist (initialize)
        if col_flag not in result_df.columns:
            result_df[col_flag] = False
        if col_reason not in result_df.columns:
            result_df[col_reason] = ""

        # Normalize triggered indices
        triggered = getattr(rule_result, "triggered_indices", []) or []
        reasons_map = getattr(rule_result, "reasons", {}) or {}
        score = int(getattr(rule_result, "score", 0) or 0)

        if triggered:
            valid_indices = [i for i in triggered if i in result_df.index]
            if valid_indices:
                result_df.loc[valid_indices, col_flag] = True
                result_df.loc[valid_indices, "total_risk_score"] += score

                for idx in valid_indices:
                    reason = reasons_map.get(idx, rule.description)
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
                    f"(+{score} pts each)"
                )
            else:
                log.info(f"  ✓ {rule.name}: 0 valid transactions flagged")
        else:
            log.info(f"  ✓ {rule.name}: 0 transactions flagged")

    def summary(self, scored_df: pd.DataFrame) -> dict:
        """Return per-rule trigger counts as a summary dict."""
        summary = {}
        for rule in self.rules:
            col = f"rule_{rule.name}"
            if col in scored_df.columns:
                summary[rule.name] = int(scored_df[col].sum())
        return summary