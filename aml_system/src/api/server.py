import json
import math
import os
from dataclasses import asdict
from pathlib import Path
from typing import Any, Optional

import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from src.ingestion.loader import TransactionLoader
from src.rules_engine.engine import RulesEngine
from src.risk_scoring.scorer import RiskScorer
from src.alert_generation.alert_manager import AlertManager
from src.investigation.case_builder import CaseBuilder
from src.utils.helpers import load_config, ensure_dir

app = FastAPI(title="AML Monitoring API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

CFG = load_config("config/config.yaml")


def _serialize_for_json(value: Any) -> Any:
    """Convert pandas/Dataclass values into JSON-safe structures."""
    if isinstance(value, dict):
        return {k: _serialize_for_json(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_serialize_for_json(v) for v in value]
    if hasattr(value, "to_dict") and callable(value.to_dict):
        return _serialize_for_json(value.to_dict())
    if hasattr(value, "__dataclass_fields__"):
        return _serialize_for_json(asdict(value))
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return None
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    return value


def _auto_generate_sar_reports(cases: list[Any]) -> list[str]:
    """Generate SAR reports automatically for cases with sanctions hits."""
    from src.sar_reporting.sar_generator import SARGenerator
    from src.sar_reporting.sar_exporter import SARExporter

    generator = SARGenerator(config_path="config/config.yaml")
    exporter = SARExporter(config_path="config/config.yaml")
    generated_files: list[str] = []

    for case in cases:
        sanctions_hits = case.get("sanctions_hits") if isinstance(case, dict) else getattr(case, "sanctions_hits", None)
        if not sanctions_hits:
            continue
        try:
            case_id = case.get("case_id") if isinstance(case, dict) else case.case_id
            sar_data = generator.generate(case)
            sar_file = exporter.export(sar_data, case_id=case_id)
            exporter.export_json(sar_data, case_id=case_id)
            generated_files.append(str(sar_file))
        except Exception as exc:
            # Don't break the pipeline if SAR generation fails for one case.
            case_id = case.get("case_id") if isinstance(case, dict) else getattr(case, "case_id", "UNKNOWN")
            print(f"Warning: failed to auto-generate SAR for {case_id}: {exc}")
    return generated_files


def _find_sar_for_case(case_id: str) -> Optional[str]:
    """Resolve the generated SAR file path for a case, if it exists."""
    cfg = load_config("config/config.yaml")
    sar_dir = Path(cfg.get("sar", {}).get("output_dir", "data/outputs/sar"))
    if not sar_dir.exists():
        return None
    candidates = list(sar_dir.glob(f"*_{case_id}.pdf"))
    if candidates:
        return str(candidates[0])
    return None


# Serve frontend static build if present
FRONTEND_BUILD = Path(__file__).parent.parent / "frontend" / "build"
if FRONTEND_BUILD.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_BUILD), html=True), name="frontend")


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/transactions")
def get_transactions(sample: Optional[int] = None):
    """Return transactions (optionally a sample of N rows).
    Uses the existing TransactionLoader to ensure consistent parsing.
    """
    try:
        loader = TransactionLoader(config_path="config/config.yaml")
        df = loader.load_all(sample_n=sample)
        return JSONResponse(content=_serialize_for_json(df.to_dict(orient="records")))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/run")
def run_pipeline(sample: Optional[int] = None, skip_sar: bool = False, alert_limit: int = 100, case_limit: int = 100):
    """Run the core pipeline (ingest → rules → scoring → alerts → cases).
    Returns a short summary and small datasets for UI consumption.
    """
    try:
        loader = TransactionLoader(config_path="config/config.yaml")
        df = loader.load_all(sample_n=sample)

        engine = RulesEngine(config_path="config/config.yaml")
        scored_df = engine.run(df)

        scorer = RiskScorer(config_path="config/config.yaml")
        scored_df = scorer.assign_tiers(scored_df)

        alert_mgr = AlertManager(config_path="config/config.yaml")
        alerts = alert_mgr.create_alerts(scored_df)

        case_builder = CaseBuilder(full_df=df, config_path="config/config.yaml")
        cases = case_builder.build_cases(alerts)

        # Persist generated outputs so the UI and pipeline behave like the CLI run
        alert_path = alert_mgr.save(alerts)
        case_builder.save_cases(cases)

        generated_sars = []
        if not skip_sar:
            generated_sars = _auto_generate_sar_reports(cases)

        # Save a labeled output dataset similar to main.py
        RULE_TO_TYPE = {
            "Smurfing": "Structuring/Smurfing",
            "Layering": "Layering",
            "RapidMovement": "Fan-Out/Money-Mule",
            "LargeTransaction": "Large-Cash-Transaction",
            "HighRiskCountry": "High-Risk-Jurisdiction",
            "CurrencyMismatch": "FX-Layering",
        }

        def derive_laundering_type(triggered_rules_str: str) -> str:
            if not triggered_rules_str:
                return ""
            rules = [r.strip() for r in triggered_rules_str.split("|") if r.strip()]
            types = [RULE_TO_TYPE.get(r, r) for r in rules]
            return "; ".join(dict.fromkeys(types))

        no_gt_mask = scored_df["Is_laundering"] == -1
        scored_df.loc[no_gt_mask, "Is_laundering"] = scored_df.loc[no_gt_mask, "is_flagged"].astype(int)
        scored_df.loc[no_gt_mask, "Laundering_type"] = scored_df.loc[no_gt_mask, "triggered_rules"].apply(derive_laundering_type)

        labeled_path = "data/outputs/transactions_labeled.csv"
        ensure_dir(Path(labeled_path).parent)
        output_cols = [
            "Txn_id", "Timestamp", "Sender_account", "Receiver_account",
            "Amount", "Payment_currency", "Received_currency",
            "Sender_bank_location", "Receiver_bank_location", "Payment_type",
            "Is_laundering", "Laundering_type",
            "total_risk_score", "risk_tier", "triggered_rules", "rule_reasons",
        ]
        scored_df[[c for c in output_cols if c in scored_df.columns]].to_csv(labeled_path, index=False)

        summary = {
            "rows": len(df),
            "alerts": len(alerts),
            "cases": len(cases),
            "rule_summary": engine.summary(scored_df),
            "artifacts": {
                "alerts_csv": alert_path,
                "cases_dir": str(Path("data/outputs/cases")),
                "labeled_transactions": labeled_path,
                "generated_sars": generated_sars,
            },
        }

        # Return a compact sample of alerts and cases for the UI
        alerts_sample = [_serialize_for_json(asdict(a)) for a in alerts[:max(1, alert_limit)]]
        cases_summary = [_serialize_for_json(asdict(c)) for c in cases[:max(1, case_limit)]]

        return {
            "summary": summary,
            "alerts": alerts_sample,
            "cases": cases_summary,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/alerts")
def list_alerts():
    path = CFG.get("alerts", {}).get("output_file")
    if path and os.path.exists(path):
        return FileResponse(path)
    raise HTTPException(status_code=404, detail="Alerts file not found")


@app.get("/api/alerts/list")
def alerts_list(offset: int = 0, limit: int = 50, risk_tier: str | None = None, sender: str | None = None):
    """Return paginated alerts and simple aggregates."""
    try:
        mgr = AlertManager(config_path="config/config.yaml")
        df = mgr.load_alerts()
        if df.empty:
            return {"total": 0, "alerts": []}

        # optional filters: risk_tier, sender, date range
        date_from = None
        date_to = None
        # filter by passed query params (risk_tier and sender already handled)
        if risk_tier:
            df = df[df["risk_tier"] == risk_tier]
        if sender:
            df = df[df["sender_account"] == sender]

        total = len(df)

        # sorting support via query params
        # client may pass `sort_by` and `sort_dir` (asc|desc)
        # these are accepted from request.args in FastAPI function signature if provided
        # (FastAPI will pass unknown query params through function args only if declared) 
        # So do basic default ordering by created_at desc
        try:
            df = df.sort_values(by=["created_at"], ascending=False)
        except Exception:
            pass

        page = _serialize_for_json(df.iloc[offset: offset + limit].to_dict(orient="records"))

        # Simple aggregates
        by_tier = _serialize_for_json(df["risk_tier"].value_counts().to_dict())
        top_senders = _serialize_for_json(df["sender_account"].value_counts().head(10).to_dict())

        return {"total": total, "alerts": page, "by_tier": by_tier, "top_senders": top_senders}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/alerts/{alert_id}")
def alert_detail(alert_id: str):
    mgr = AlertManager(config_path="config/config.yaml")
    df = mgr.load_alerts()
    if df.empty:
        raise HTTPException(status_code=404, detail="No alerts available")
    if "alert_id" not in df.columns:
        raise HTTPException(status_code=500, detail="Alerts file is malformed")
    matches = df[df["alert_id"].astype(str) == alert_id]
    if matches.empty:
        raise HTTPException(status_code=404, detail="Alert not found")
    return _serialize_for_json(matches.iloc[0].to_dict())


@app.get("/api/cases")
def list_cases():
    cases_dir = CFG.get("investigation", {}).get("cases_dir")
    if not cases_dir or not os.path.isdir(cases_dir):
        raise HTTPException(status_code=404, detail="Cases directory not found")
    files = sorted(os.listdir(cases_dir))
    return {"cases": files}


@app.get("/api/cases/{case_id}")
def case_detail(case_id: str):
    try:
        cb = CaseBuilder(full_df=None, config_path="config/config.yaml")
        case = cb.load_case(case_id)
        return JSONResponse(content=_serialize_for_json(case))
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Case not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/sar/candidates")
def sar_candidates():
    """Return cases that are candidates for SAR filing (ESCALATED status)."""
    try:
        cases_dir = CFG.get("investigation", {}).get("cases_dir")
        if not cases_dir or not os.path.isdir(cases_dir):
            return {"sar_candidates": [], "candidates": []}

        candidates = []
        for filename in sorted(os.listdir(cases_dir)):
            if filename.endswith('.json'):
                try:
                    cb = CaseBuilder(full_df=None, config_path="config/config.yaml")
                    case = cb.load_case(filename.replace('.json', ''))
                    # Only include escalated cases
                    if case.get('status') == 'ESCALATED' or case.get('recommendation') == 'SAR':
                        case_json = _serialize_for_json(case)
                        sar_file = _find_sar_for_case(case_json.get('case_id') or filename.replace('.json', ''))
                        if sar_file:
                            case_json['sar_file'] = sar_file
                        candidates.append(case_json)
                except Exception:
                    pass

        return {"sar_candidates": candidates, "candidates": candidates}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/sar/generate")
def generate_sar(request_data: dict):
    """Generate a SAR report for a given case."""
    try:
        case_id = request_data.get('case_id')
        if not case_id:
            raise HTTPException(status_code=400, detail="case_id required")

        # Load the case
        cb = CaseBuilder(full_df=None, config_path="config/config.yaml")
        case_data = cb.load_case(case_id)
        from src.investigation.case_builder import InvestigationCase
        case = InvestigationCase(**case_data)

        # Import SAR generator
        from src.sar_reporting.sar_generator import SARGenerator
        from src.sar_reporting.sar_exporter import SARExporter

        # Generate SAR
        gen = SARGenerator(config_path="config/config.yaml")
        sar = gen.generate(case)

        # Persist SAR
        exporter = SARExporter(config_path="config/config.yaml")
        sar_file = exporter.export(sar, case_id=case_id)
        exporter.export_json(sar, case_id=case_id)

        return {
            "success": True,
            "sar_file": str(sar_file),
            "filename": os.path.basename(str(sar_file)),
            "case_id": case_id,
        }
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Case not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"SAR generation failed: {str(e)}")


@app.get("/api/sar/{case_id}")
def get_sar_report(case_id: str):
    """Fetch a generated SAR report by case_id."""
    try:
        sar_dir = CFG.get("sar_reporting", {}).get("output_dir", "data/outputs/sar")
        sar_path = None

        # Find the SAR JSON file for this case
        for filename in os.listdir(sar_dir):
            if filename.endswith('.json') and case_id in filename:
                sar_path = Path(sar_dir) / filename
                break

        if not sar_path or not sar_path.exists():
            raise HTTPException(status_code=404, detail=f"SAR report not found for case {case_id}")

        with open(sar_path, "r", encoding="utf-8") as f:
            sar_data = json.load(f)

        return {"success": True, "sar": sar_data}
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"SAR report not found for case {case_id}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

