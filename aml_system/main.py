#!/usr/bin/env python3
"""
AML Monitoring System — Main Pipeline Entry Point
==================================================
Runs the complete AML pipeline:
  Transactions → Risk Assessment → Alert Generation → Investigation → SAR Reporting

Usage:
    python main.py --input data/raw/transactions.csv
    python main.py --input data/raw/transactions.csv --sample 10000
    python main.py --input data/raw/transactions.csv --max-sar 5

Arguments:
    --input       Path to the IBM AML transactions CSV file
    --sample      Process only first N rows (for testing)
    --max-sar     Maximum number of SAR reports to generate (default: 20)
    --config      Path to config.yaml (default: config/config.yaml)
    --skip-sar    Skip SAR generation (alerts & cases only)
"""

import argparse
import sys
import os
import time
from pathlib import Path

# Ensure project root is on PYTHONPATH regardless of how script is invoked
sys.path.insert(0, str(Path(__file__).parent))

from src.alert_generation.alert_manager import AlertManager
from src.ingestion.loader import TransactionLoader
from src.investigation.case_builder import CaseBuilder
from src.risk_scoring.scorer import RiskScorer
from src.rules_engine.engine import RulesEngine
from src.sar_reporting.sar_exporter import SARExporter
from src.sar_reporting.sar_generator import SARGenerator
from src.utils.helpers import load_config, print_section, print_kv, ensure_dir
from src.utils.logger import get_logger


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="AML Monitoring System — end-to-end pipeline",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--input",
        default="data/raw/transactions.csv",
        help="Path to IBM AML transactions CSV",
    )
    parser.add_argument(
        "--sample",
        type=int,
        default=None,
        help="Load only first N rows (quick test mode)",
    )
    parser.add_argument(
        "--max-sar",
        type=int,
        default=20,
        help="Maximum number of SAR PDFs to generate",
    )
    parser.add_argument(
        "--config",
        default="config/config.yaml",
        help="Path to config.yaml",
    )
    parser.add_argument(
        "--skip-sar",
        action="store_true",
        help="Skip SAR generation step",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    # ── Bootstrap ────────────────────────────────────────────────────────
    cfg = load_config(args.config)
    log_cfg = cfg.get("logging", {})
    log = get_logger(
        "aml.pipeline",
        log_file=log_cfg.get("log_file"),
        level=log_cfg.get("level", "INFO"),
    )

    pipeline_start = time.time()

    print_section("AML MONITORING SYSTEM — PIPELINE START")
    print_kv("Input file:", args.input)
    print_kv("Sample rows:", args.sample or "ALL")
    print_kv("Max SARs:", args.max_sar)
    print_kv("Config:", args.config)

    # ═══════════════════════════════════════════════════════════════════
    # STEP 1 — DATA INGESTION
    # ═══════════════════════════════════════════════════════════════════
    print_section("STEP 1 — DATA INGESTION")
    t0 = time.time()

    loader = TransactionLoader(config_path=args.config)
    # Override input path from CLI
    loader.input_file = args.input

    df = loader.load_all(sample_n=args.sample)
    print_kv("Rows loaded:", f"{len(df):,}")
    print_kv("Columns:", ", ".join(df.columns.tolist()))
    print_kv("Elapsed:", f"{time.time() - t0:.1f}s")

    # ═══════════════════════════════════════════════════════════════════
    # STEP 2 — RULES ENGINE
    # ═══════════════════════════════════════════════════════════════════
    print_section("STEP 2 — RULES ENGINE")
    t0 = time.time()

    engine = RulesEngine(config_path=args.config)
    scored_df = engine.run(df)

    rule_summary = engine.summary(scored_df)
    print("\n  Rule Trigger Summary:")
    for rule, count in rule_summary.items():
        print_kv(f"  {rule}:", f"{count:,} triggered")
    print_kv("\n  Elapsed:", f"{time.time() - t0:.1f}s")

    # ═══════════════════════════════════════════════════════════════════
    # STEP 3 — RISK SCORING
    # ═══════════════════════════════════════════════════════════════════
    print_section("STEP 3 — RISK SCORING")
    t0 = time.time()

    scorer = RiskScorer(config_path=args.config)
    scored_df = scorer.assign_tiers(scored_df)

    tier_dist = scored_df["risk_tier"].value_counts().to_dict()
    print("\n  Risk Tier Distribution:")
    for tier in ["CRITICAL", "HIGH", "MEDIUM", "LOW"]:
        count = tier_dist.get(tier, 0)
        pct = 100 * count / len(scored_df) if len(scored_df) > 0 else 0
        print_kv(f"  {tier}:", f"{count:>10,}  ({pct:.2f}%)")

    # Evaluate against ground truth
    metrics = scorer.evaluate(scored_df)
    if metrics:
        print("\n  Model Evaluation vs. Ground Truth (Is_laundering):")
        print_kv("  Precision:", f"{metrics.get('precision', 0):.2%}")
        print_kv("  Recall:", f"{metrics.get('recall', 0):.2%}")
        print_kv("  F1 Score:", f"{metrics.get('f1_score', 0):.4f}")
        print_kv("  True Positives:", f"{metrics.get('tp', 0):,}")
        print_kv("  False Positives:", f"{metrics.get('fp', 0):,}")
        print_kv("  False Negatives:", f"{metrics.get('fn', 0):,}")
    print_kv("\n  Elapsed:", f"{time.time() - t0:.1f}s")
        # ═══════════════════════════════════════════════════════════════════
    # STEP 3b — PREDICT Is_laundering & Laundering_type
    # ═══════════════════════════════════════════════════════════════════
    print_section("STEP 3b — LABELLING TRANSACTIONS")

    # Rule → Laundering type label mapping
    RULE_TO_TYPE = {
        "Smurfing":          "Structuring/Smurfing",
        "Layering":          "Layering",
        "RapidMovement":     "Fan-Out/Money-Mule",
        "LargeTransaction":  "Large-Cash-Transaction",
        "HighRiskCountry":   "High-Risk-Jurisdiction",
        "CurrencyMismatch":  "FX-Layering",
    }

    def derive_laundering_type(triggered_rules_str: str) -> str:
        """Convert pipe-separated rule names to a human-readable laundering type."""
        if not triggered_rules_str:
            return ""
        rules = [r.strip() for r in triggered_rules_str.split("|") if r.strip()]
        types = [RULE_TO_TYPE.get(r, r) for r in rules]
        return "; ".join(dict.fromkeys(types))  # dedup, preserve order

    # Only predict where ground truth is absent (Is_laundering == -1)
    no_gt_mask = scored_df["Is_laundering"] == -1

    # Is_laundering = 1 if flagged (MEDIUM/HIGH/CRITICAL), else 0
    scored_df.loc[no_gt_mask, "Is_laundering"] = (
        scored_df.loc[no_gt_mask, "is_flagged"].astype(int)
    )

    # Laundering_type = derived from triggered rules
    scored_df.loc[no_gt_mask, "Laundering_type"] = (
        scored_df.loc[no_gt_mask, "triggered_rules"].apply(derive_laundering_type)
    )

    # Save the fully labeled output dataset
    labeled_path = "data/outputs/transactions_labeled.csv"
    output_cols = [
        "Txn_id", "Timestamp", "Sender_account", "Receiver_account",
        "Amount", "Payment_currency", "Received_currency",
        "Sender_bank_location", "Receiver_bank_location", "Payment_type",
        "Is_laundering", "Laundering_type",          # ← predicted labels
        "total_risk_score", "risk_tier", "triggered_rules", "rule_reasons",
    ]
    scored_df[[c for c in output_cols if c in scored_df.columns]].to_csv(
        labeled_path, index=False
    )

    laundering_count = (scored_df["Is_laundering"] == 1).sum()
    print_kv("  Transactions predicted as laundering:", f"{laundering_count:,}")
    print_kv("  Transactions predicted as clean:",      f"{len(scored_df) - laundering_count:,}")
    print_kv("  Labeled output saved to:", labeled_path)

    # ═══════════════════════════════════════════════════════════════════
    # STEP 4 — ALERT GENERATION
    # ═══════════════════════════════════════════════════════════════════
    print_section("STEP 4 — ALERT GENERATION")
    t0 = time.time()

    alert_mgr = AlertManager(config_path=args.config)
    alerts = alert_mgr.create_alerts(scored_df)
    alert_path = alert_mgr.save(alerts)

    alert_summary = alert_mgr.summary(alerts)
    print("\n  Alert Summary by Risk Tier:")
    for tier, count in sorted(alert_summary.items(), key=lambda x: ["LOW","MEDIUM","HIGH","CRITICAL"].index(x[0]) if x[0] in ["LOW","MEDIUM","HIGH","CRITICAL"] else 0, reverse=True):
        print_kv(f"  {tier}:", f"{count:,}")
    print_kv("\n  Total Alerts:", f"{len(alerts):,}")
    print_kv("  Alerts CSV:", alert_path)
    print_kv("  Elapsed:", f"{time.time() - t0:.1f}s")

    # ═══════════════════════════════════════════════════════════════════
    # STEP 5 — INVESTIGATION
    # ═══════════════════════════════════════════════════════════════════
    print_section("STEP 5 — CASE INVESTIGATION")
    t0 = time.time()

    case_builder = CaseBuilder(full_df=df, config_path=args.config)
    cases = case_builder.build_cases(alerts)
    case_builder.save_cases(cases)

    sar_candidates = case_builder.get_sar_candidates(cases)
    print_kv("  Total Cases Built:", f"{len(cases):,}")
    print_kv("  Auto-Escalated (→ SAR):", f"{len(sar_candidates):,}")
    print_kv("  Cases Directory:", cfg["investigation"]["cases_dir"])
    print_kv("  Elapsed:", f"{time.time() - t0:.1f}s")

    # ═══════════════════════════════════════════════════════════════════
    # STEP 6 — SAR REPORTING
    # ═══════════════════════════════════════════════════════════════════
    if not args.skip_sar:
        print_section("STEP 6 — SAR REPORT GENERATION")
        t0 = time.time()

        sar_gen = SARGenerator(config_path=args.config)
        sar_exp = SARExporter(config_path=args.config)

        # Limit SAR generation to max_sar cases
        to_report = sar_candidates[:args.max_sar]
        sar_batch: list[tuple] = []

        for case in to_report:
            sar_data = sar_gen.generate(case)
            sar_batch.append((sar_data, case.case_id))

        output_paths = sar_exp.export_batch(sar_batch)

        print_kv("  SARs Generated:", f"{len(output_paths):,}")
        print_kv("  SAR Output Dir:", cfg["sar"]["output_dir"])
        if output_paths:
            print_kv("  First SAR:", output_paths[0])
        print_kv("  Elapsed:", f"{time.time() - t0:.1f}s")
    else:
        print("\n  [SAR generation skipped — --skip-sar flag set]")

    # ═══════════════════════════════════════════════════════════════════
    # PIPELINE COMPLETE
    # ═══════════════════════════════════════════════════════════════════
    total_time = time.time() - pipeline_start
    print_section("PIPELINE COMPLETE")
    print_kv("  Total transactions processed:", f"{len(df):,}")
    print_kv("  Total alerts generated:", f"{len(alerts):,}")
    print_kv("  Total cases built:", f"{len(cases):,}")
    if not args.skip_sar:
        print_kv("  Total SARs filed:", f"{len(to_report):,}")
    print_kv("  Total elapsed time:", f"{total_time:.1f}s")
    print("\n  Output files:")
    print_kv("    Alerts CSV:", cfg["alerts"]["output_file"])
    print_kv("    Alerts Excel:", cfg["alerts"]["excel_report"])
    print_kv("    Cases JSON:", cfg["investigation"]["cases_dir"])
    print_kv("    SAR PDFs:", cfg["sar"]["output_dir"])
    print_kv("    Run Log:", cfg["logging"].get("log_file", "N/A"))
    print()


if __name__ == "__main__":
    main()
