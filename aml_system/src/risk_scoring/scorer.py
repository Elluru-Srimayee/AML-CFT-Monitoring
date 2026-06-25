"""
Risk Scorer
===========
Converts raw rule scores into a labelled risk tier (LOW/MEDIUM/HIGH/CRITICAL).
Also evaluates model quality against the ground-truth Is_laundering column.
"""

from __future__ import annotations

import pandas as pd

from src.utils.helpers import load_config
from src.utils.logger import get_logger

log = get_logger(__name__)

TIER_ORDER = ["LOW", "MEDIUM", "HIGH", "CRITICAL"]


class RiskScorer:
    """
    Assigns a risk tier to each transaction based on total_risk_score.

    Usage:
        scorer = RiskScorer()
        scored_df = scorer.assign_tiers(engine_df)
        metrics  = scorer.evaluate(scored_df)
    """

    def __init__(self, config_path: str = "config/config.yaml"):
        cfg = load_config(config_path)
        rs_cfg = cfg["risk_scoring"]
        # Build tier → (min, max) mapping
        self.tiers: dict[str, tuple[int, int]] = {
            tier: (bounds[0], bounds[1])
            for tier, bounds in rs_cfg["tiers"].items()
        }
        self.alert_threshold = rs_cfg.get("alert_threshold", "MEDIUM")

    # ── Public API ────────────────────────────────────────────────────────

    def assign_tiers(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Add 'risk_tier' and 'is_flagged' columns to the scored DataFrame.

        Args:
            df: Output of RulesEngine.run() containing 'total_risk_score'.

        Returns:
            DataFrame with risk_tier and is_flagged columns appended.
        """
        if "total_risk_score" not in df.columns:
            raise ValueError("DataFrame must contain 'total_risk_score' (run RulesEngine first)")

        result = df.copy()
        result["risk_tier"] = result["total_risk_score"].apply(self._score_to_tier)
        result["is_flagged"] = result["risk_tier"].apply(
            lambda t: TIER_ORDER.index(t) >= TIER_ORDER.index(self.alert_threshold)
        )

        self._log_tier_distribution(result)
        return result

    def evaluate(self, df: pd.DataFrame) -> dict:
        """
        Compute precision / recall / F1 against ground truth Is_laundering.

        Returns dict with keys: precision, recall, f1, tp, fp, fn, tn.
        """
        if "Is_laundering" not in df.columns or "is_flagged" not in df.columns:
            log.warning("Cannot evaluate — missing Is_laundering or is_flagged columns")
            return {}

        gt = df["Is_laundering"].astype(bool)
        pred = df["is_flagged"].astype(bool)

        tp = int((pred & gt).sum())
        fp = int((pred & ~gt).sum())
        fn = int((~pred & gt).sum())
        tn = int((~pred & ~gt).sum())

        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0

        metrics = {
            "total": len(df),
            "tp": tp, "fp": fp, "fn": fn, "tn": tn,
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1_score": round(f1, 4),
        }
        log.info(
            f"Evaluation — Precision: {precision:.2%}  Recall: {recall:.2%}  F1: {f1:.4f} "
            f"| TP={tp:,} FP={fp:,} FN={fn:,} TN={tn:,}"
        )
        return metrics

    # ── Private ───────────────────────────────────────────────────────────

    def _score_to_tier(self, score: float) -> str:
        for tier, (lo, hi) in self.tiers.items():
            if lo <= score <= hi:
                return tier
        return "CRITICAL"  # fallback for scores beyond defined range

    def _log_tier_distribution(self, df: pd.DataFrame) -> None:
        counts = df["risk_tier"].value_counts()
        log.info("Risk tier distribution:")
        for tier in TIER_ORDER:
            n = counts.get(tier, 0)
            pct = 100 * n / len(df) if len(df) > 0 else 0
            log.info(f"  {tier:<10}: {n:>10,}  ({pct:.2f}%)")
