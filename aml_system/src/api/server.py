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

from src.ingestion.loader import TransactionLoader, enrich_with_customer_data
from src.rules_engine.engine import RulesEngine
from src.risk_scoring.scorer import RiskScorer
from src.alert_generation.alert_manager import AlertManager
from src.investigation.case_builder import CaseBuilder
from src.utils.helpers import load_config, ensure_dir
from src.utils.logger import get_logger

app = FastAPI(title="AML Monitoring API")
log = get_logger(__name__)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

CFG = load_config("config/config.yaml")

# Global cache for cases (loaded once at startup or on-demand)
_CASES_CACHE = None
_CASES_CACHE_TIMESTAMP = None

def _load_cases_cache():
    """Load all case JSON files into memory for fast pagination/filtering."""
    global _CASES_CACHE, _CASES_CACHE_TIMESTAMP
    try:
        cases_dir = CFG.get("investigation", {}).get("cases_dir")
        if not cases_dir or not os.path.isdir(cases_dir):
            _CASES_CACHE = []
            return []
        
        cases = []
        for fname in sorted(os.listdir(cases_dir)):
            if fname.endswith('.json'):
                try:
                    with open(Path(cases_dir) / fname, 'r', encoding='utf-8') as f:
                        case = json.load(f)
                        cases.append(_serialize_for_json(case))
                except Exception as e:
                    print(f"Warning: Failed to load case {fname}: {e}")
        
        _CASES_CACHE = cases
        _CASES_CACHE_TIMESTAMP = __import__('time').time()
        return cases
    except Exception as e:
        print(f"Error loading cases cache: {e}")
        _CASES_CACHE = []
        return []

def _get_cases_cache():
    """Get cases from cache, loading on first access."""
    global _CASES_CACHE
    if _CASES_CACHE is None:
        _load_cases_cache()
    return _CASES_CACHE or []


# Global SAR candidates cache
_SAR_CANDIDATES_CACHE = None

def _load_sar_candidates_cache():
    """Load ESCALATED cases and their SAR files into cache."""
    global _SAR_CANDIDATES_CACHE
    try:
        all_cases = _get_cases_cache()
        candidates = []
        for case in all_cases:
            if case.get('status') == 'ESCALATED' or case.get('recommendation') == 'SAR':
                case_copy = _serialize_for_json(case)
                sar_file = _find_sar_for_case(case_copy.get('case_id') or '')
                if sar_file:
                    case_copy['sar_file'] = sar_file
                candidates.append(case_copy)
        _SAR_CANDIDATES_CACHE = candidates
        return candidates
    except Exception as e:
        print(f"Error loading SAR candidates cache: {e}")
        _SAR_CANDIDATES_CACHE = []
        return []

def _get_sar_candidates_cache():
    """Get SAR candidates from cache, loading on first access."""
    global _SAR_CANDIDATES_CACHE
    if _SAR_CANDIDATES_CACHE is None:
        _load_sar_candidates_cache()
    return _SAR_CANDIDATES_CACHE or []

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


def _auto_generate_sar_for_case(case: Any) -> Optional[str]:
    """
    Auto-generate SAR report for a single case if it has sanctions hits.
    Returns the generated SAR file path, or None if not generated.
    """
    from src.sar_reporting.sar_generator import SARGenerator
    from src.sar_reporting.sar_exporter import SARExporter

    # Extract sanctions_hits and case_id
    sanctions_hits = case.get("sanctions_hits") if isinstance(case, dict) else getattr(case, "sanctions_hits", None)
    case_id = case.get("case_id") if isinstance(case, dict) else getattr(case, "case_id", None)
    
    if not case_id:
        return None
    
    # Only generate SAR if there are sanctions hits
    if not sanctions_hits:
        return None
    
    # Check if SAR already exists for this case
    existing_sar = _find_sar_for_case(case_id)
    if existing_sar:
        log.debug(f"SAR already exists for {case_id}: {existing_sar}")
        return existing_sar
    
    try:
        generator = SARGenerator(config_path="config/config.yaml")
        exporter = SARExporter(config_path="config/config.yaml")
        
        log.info(f"Auto-generating SAR for sanctions case {case_id} (sanctions_hits={len(sanctions_hits)})")
        sar_data = generator.generate(case)
        sar_file = exporter.export(sar_data, case_id=case_id)
        exporter.export_json(sar_data, case_id=case_id)
        log.info(f"SAR generated successfully: {sar_file}")
        return str(sar_file)
    except Exception as exc:
        log.warning(f"Failed to auto-generate SAR for sanctions case {case_id}: {exc}")
        return None


def _auto_generate_sar_reports(cases: list[Any]) -> list[str]:
    """Generate SAR reports automatically for cases with sanctions hits."""
    generated_files: list[str] = []
    
    for case in cases:
        sar_file = _auto_generate_sar_for_case(case)
        if sar_file:
            generated_files.append(sar_file)
    
    return generated_files


def _auto_generate_sar_reports_for_all_cases() -> int:
    """
    Scan all existing cases on disk and auto-generate SARs for any that:
    - Have sanctions_hits populated
    - Don't already have a SAR file
    
    Returns the count of SARs generated.
    """
    all_cases = _get_cases_cache()
    generated_count = 0
    
    for case in all_cases:
        if _auto_generate_sar_for_case(case):
            generated_count += 1
    
    return generated_count


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
def run_pipeline(sample: Optional[int] = None, skip_sar: bool = False, alert_limit: Optional[int] = None, case_limit: Optional[int] = None):
    """Run the core pipeline (ingest → rules → scoring → alerts → cases).
    Returns a short summary and datasets for UI consumption.
    If `alert_limit` or `case_limit` are omitted or None, the full lists are returned.
    """
    try:
        loader = TransactionLoader(config_path="config/config.yaml")
        df = loader.load_all(sample_n=sample)
        customer_details_file = CFG.get("investigation", {}).get("customer_details_file", "data/raw/customer_details.csv")
        if os.path.exists(customer_details_file):
            df = enrich_with_customer_data(transactions=df, customer_csv=customer_details_file)

        engine = RulesEngine(config_path="config/config.yaml")
        scored_df = engine.run(df)

        scorer = RiskScorer(config_path="config/config.yaml")
        scored_df = scorer.assign_tiers(scored_df)

        if "sanctions_hit" in scored_df.columns:
            scored_df["is_flagged"] = scored_df["is_flagged"] | scored_df["sanctions_hit"].astype(bool)
            scored_df["risk_tier"] = scored_df.apply(
                lambda row: "CRITICAL" if row.get("sanctions_hit") else row.get("risk_tier"),
                axis=1,
            )

        alert_mgr = AlertManager(config_path="config/config.yaml")
        alerts = alert_mgr.create_alerts(scored_df)

        case_builder = CaseBuilder(full_df=df, config_path="config/config.yaml")
        cases = case_builder.build_cases(alerts)

        # Persist generated outputs so the UI and pipeline behave like the CLI run
        alert_path = alert_mgr.save(alerts)
        case_builder.save_cases(cases)
        
        # Refresh cases cache after pipeline run
        _load_cases_cache()

        generated_sars = []
        if not skip_sar:
            generated_sars = _auto_generate_sar_reports(cases)
            # Refresh SAR candidates cache after generating new SARs
            _load_sar_candidates_cache()

        # Save a labeled output dataset similar to main.py
        RULE_TO_TYPE = {
            "Smurfing": "Structuring/Smurfing",
            "Layering": "Layering",
            "RapidMovement": "Fan-Out/Money-Mule",
            "LargeTransaction": "Large-Cash-Transaction",
            "HighRiskCountry": "High-Risk-Jurisdiction",
            "CurrencyMismatch": "FX-Layering",
            "CashBusinessAI": "Cash-Business-AI",
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

        # Return alerts and cases; respect explicit limits if provided
        if alert_limit is None or alert_limit <= 0:
            alerts_sample = [_serialize_for_json(asdict(a)) for a in alerts]
        else:
            alerts_sample = [_serialize_for_json(asdict(a)) for a in alerts[:alert_limit]]

        if case_limit is None or case_limit <= 0:
            cases_summary = [_serialize_for_json(asdict(c)) for c in cases]
        else:
            cases_summary = [_serialize_for_json(asdict(c)) for c in cases[:case_limit]]

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


@app.get("/api/cases/list")
def cases_list(offset: int = 0, limit: int = 50, risk_tier: str | None = None, status: str | None = None):
    """Return paginated cases with filtering (fast: uses in-memory cache)."""
    try:
        all_cases = _get_cases_cache()
        total = len(all_cases)

        # Apply filters
        filtered = all_cases
        if risk_tier:
            filtered = [c for c in filtered if c.get('risk_tier') == risk_tier]
        if status:
            filtered = [c for c in filtered if c.get('status') == status]

        # Paginate
        page = filtered[offset: offset + limit]

        # Aggregates
        by_tier = {}
        for c in filtered:
            tier = c.get('risk_tier') or 'UNKNOWN'
            by_tier[tier] = by_tier.get(tier, 0) + 1

        return {"total": len(filtered), "cases": page, "by_tier": by_tier}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/cases/{case_id}")
def case_detail(case_id: str):
    try:
        # Loading the full CaseBuilder here triggers expensive initialization
        # (customer profiler, sanctions watchlist loading, pattern analyzer) even
        # when we only need to return the persisted JSON for a single case.
        # Read the case file directly for fast responses.
        cases_dir = CFG.get("investigation", {}).get("cases_dir")
        if not cases_dir:
            raise FileNotFoundError(f"Case not found: {case_id}")
        path = Path(cases_dir) / f"{case_id}.json"
        if not path.exists():
            raise FileNotFoundError(f"Case not found: {case_id}")
        with open(path, "r", encoding="utf-8") as f:
            case = json.load(f)
        return JSONResponse(content=_serialize_for_json(case))
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Case not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/sar/candidates")
def sar_candidates():
    """Return cases that are candidates for SAR filing (ESCALATED status)."""
    try:
        candidates = _get_sar_candidates_cache()
        return {"sar_candidates": candidates, "candidates": candidates}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/sar/candidates/list")
def sar_candidates_list(offset: int = 0, limit: int = 50, risk_tier: str | None = None):
    """Return paginated SAR candidates with filtering (fast: uses in-memory cache)."""
    try:
        all_candidates = _get_sar_candidates_cache()
        total = len(all_candidates)

        # Apply filters
        filtered = all_candidates
        if risk_tier:
            filtered = [c for c in filtered if c.get('risk_tier') == risk_tier]

        # Paginate
        page = filtered[offset: offset + limit]

        # Aggregates
        by_tier = {}
        for c in filtered:
            tier = c.get('risk_tier') or 'UNKNOWN'
            by_tier[tier] = by_tier.get(tier, 0) + 1

        return {"total": len(filtered), "candidates": page, "by_tier": by_tier}
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

        # Refresh SAR candidates cache so UI sees the new generated report immediately
        _load_sar_candidates_cache()

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


@app.post("/api/cases/{case_id}/whitelist")
def whitelist_case(case_id: str):
    """Mark a case as whitelisted (legitimate customer) by setting Is_laundering=0."""
    try:
        cb = CaseBuilder(full_df=None, config_path="config/config.yaml")
        case_data = cb.load_case(case_id)
        
        # Get transaction IDs from the case
        alerts = case_data.get('alerts', [])
        if not alerts:
            return {
                "success": True,
                "message": "Case whitelisted (no alerts)",
                "case_id": case_id,
                "whitelisted_count": 0,
            }
        
        # Extract transaction indices
        txn_indices = list(set(alert.get('txn_id') for alert in alerts if 'txn_id' in alert))
        
        # Update transactions CSV - mark as non-laundering
        labeled_path = "data/outputs/transactions_labeled.csv"
        if os.path.exists(labeled_path):
            try:
                df_labeled = pd.read_csv(labeled_path)
                for idx in txn_indices:
                    if idx < len(df_labeled):
                        df_labeled.at[idx, 'Is_laundering'] = 0
                df_labeled.to_csv(labeled_path, index=False)
            except Exception as e:
                print(f"Warning: Could not update transactions_labeled.csv: {e}")
        
        # Update case status to FALSE_POSITIVE
        case_data['status'] = 'FALSE_POSITIVE'
        cases_dir = CFG.get("investigation", {}).get("cases_dir")
        if cases_dir:
            case_file = Path(cases_dir) / f"{case_id}.json"
            with open(case_file, 'w', encoding='utf-8') as f:
                json.dump(_serialize_for_json(case_data), f, indent=2, default=str)
        
        # Refresh caches
        _load_cases_cache()
        _load_sar_candidates_cache()
        
        return {
            "success": True,
            "message": f"Case {case_id} whitelisted - marked as legitimate customer",
            "case_id": case_id,
            "whitelisted_count": len(txn_indices),
        }
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Case {case_id} not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Whitelist operation failed: {str(e)}")


@app.post("/api/sar/auto-generate-missing")
def auto_generate_missing_sars():
    """
    Auto-generate missing SAR reports for all cases with sanctions hits.
    Scans all existing cases and generates SARs for those that have sanctions_hits
    but don't have a corresponding SAR file yet.
    """
    try:
        log.info("Starting auto-generation of missing SAR reports for sanctions cases...")
        generated_count = _auto_generate_sar_reports_for_all_cases()
        
        # Refresh SAR candidates cache
        _load_sar_candidates_cache()
        
        log.info(f"Auto-generation complete: {generated_count} SAR(s) generated")
        return {
            "success": True,
            "message": f"Auto-generated {generated_count} SAR report(s) for sanctions cases",
            "generated_count": generated_count,
        }
    except Exception as e:
        log.error(f"Auto-generation of missing SARs failed: {e}")
        raise HTTPException(status_code=500, detail=f"Auto-generation failed: {str(e)}")


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

