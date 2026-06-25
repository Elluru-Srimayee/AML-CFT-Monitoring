# AML Monitoring System

> A complete Python PoC for Anti-Money Laundering detection, built for the **IBM Kaggle AML dataset**.

---

## Pipeline Overview

```
IBM Transactions CSV
       │
       ▼
┌─────────────────┐
│  1. Ingestion   │  Chunked CSV loading, schema validation, datetime parsing
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  2. Rules Engine│  6 detection rules: large txn, high-risk country,
│                 │  smurfing, layering, rapid movement, FX mismatch
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  3. Risk Scoring│  Weighted score → LOW / MEDIUM / HIGH / CRITICAL
│                 │  Precision / Recall / F1 vs. Is_laundering ground truth
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  4. Alerts      │  Deduped alerts → alerts.csv + colour-coded Excel
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  5. Investigation│ Case building, customer profiling, sanctions check,
│                 │  NetworkX pattern analysis (fan-out, fan-in, cycles)
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  6. SAR Report  │  Fills your PDF template via AcroForm (pypdf)
│                 │  Fallback: generates formatted SAR PDF via reportlab
└─────────────────┘
```

---

## Quick Start

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Add your dataset

Download the IBM AML dataset from Kaggle:  
https://www.kaggle.com/datasets/ealtman2019/ibm-transactions-for-anti-money-laundering-aml

Place the CSV file at:
```
data/raw/transactions.csv
```

The file must have these columns:
```
Time, Date, Sender_account, Receiver_account, Amount, Payment_currency,
Received_currency, Sender_bank_location, Receiver_bank_location,
Payment_type, Is_laundering, Laundering_type
```

### 3. (Optional) Add your PDF SAR template

Place your PDF SAR template at:
```
reports/templates/SAR_template.pdf
```

**If the PDF is a fillable form (AcroForm):** rename your PDF fields to match  
the names in `SAR_FIELD_MAPPING` in `src/sar_reporting/sar_exporter.py` — or  
update the mapping to match your existing field names.

**If the PDF is not fillable:** the system auto-generates a formatted SAR PDF  
using reportlab. No action needed.

### 4. Run the full pipeline

```bash
# Full dataset
python main.py

# Quick test with first 10,000 rows
python main.py --sample 10000

# Custom input path
python main.py --input path/to/your/transactions.csv

# Limit SAR generation to 10 reports
python main.py --max-sar 10

# Skip SAR generation (alerts + cases only)
python main.py --skip-sar
```

---

## Output Files

| File | Description |
|------|-------------|
| `data/outputs/alerts/alerts.csv` | All alerts with risk tier & reasons |
| `data/outputs/alerts/alert_report.xlsx` | Colour-coded Excel alert workbook |
| `data/outputs/cases/CASE-*.json` | Full investigation case files (JSON) |
| `data/outputs/sar/SAR-*.pdf` | Filled SAR PDF reports |
| `data/outputs/sar/SAR-*.json` | SAR archival JSON copy |
| `data/outputs/aml_system.log` | Full run log |

---

## Project Structure

```
aml_system/
├── config/
│   ├── config.yaml              # All thresholds, rules, countries — edit here
│   └── sanction_list.csv            # Sanctions / PEP watchlist
├── data/
│   ├── raw/                     # → Place transactions.csv here
│   ├── processed/
│   └── outputs/
│       ├── alerts/
│       ├── cases/
│       └── sar/
├── src/
│   ├── ingestion/loader.py      # Chunked CSV loader
│   ├── rules_engine/
│   │   ├── engine.py            # Orchestrator
│   │   ├── rule_large_txn.py
│   │   ├── rule_high_risk_country.py
│   │   ├── rule_smurfing.py
│   │   ├── rule_layering.py
│   │   ├── rule_rapid_movement.py
│   │   └── rule_currency_mismatch.py
│   ├── risk_scoring/scorer.py   # Tier assignment + evaluation
│   ├── alert_generation/alert_manager.py
│   ├── investigation/
│   │   ├── case_builder.py
│   │   ├── customer_profiler.py
│   │   ├── sanctions_checker.py
│   │   └── pattern_analyzer.py
│   ├── sar_reporting/
│   │   ├── sar_generator.py
│   │   └── sar_exporter.py      # PDF fill / generation
│   └── utils/
│       ├── logger.py
│       └── helpers.py
├── reports/templates/           # → Place SAR_template.pdf here
├── tests/
│   ├── test_rules_engine.py
│   ├── test_risk_scoring.py
│   └── test_sar_generator.py
├── main.py                      # Entry point
└── requirements.txt
```

---

## Detection Rules

| Rule | What it detects | Score |
|------|----------------|-------|
| `LargeTransaction` | Single txn > $10,000 (configurable) | +25 |
| `HighRiskCountry` | Sender/receiver in FATF grey/black list | +30 |
| `Smurfing` | Multiple sub-threshold txns totalling > threshold | +40 |
| `Layering` | Money chain A→B→C→D within 72h | +35 |
| `RapidMovement` | Account re-sends ≥80% of received funds within 24h | +20 |
| `CurrencyMismatch` | Payment currency ≠ received currency | +15 |

**Risk tiers:**
- `LOW` (0–30): Pass through
- `MEDIUM` (31–59): Alert generated
- `HIGH` (60–79): Alert + case built
- `CRITICAL` (80+): Auto-escalate to SAR

---

## SAR PDF Template — Field Names

If your PDF is a fillable AcroForm, name the fields using these IDs  
(or update `SAR_FIELD_MAPPING` in `src/sar_reporting/sar_exporter.py`):

| Field Name | Content |
|------------|---------|
| `SAR_ID` | Unique SAR identifier |
| `Filing_Date` | Date SAR was generated |
| `Institution_Name` | Filing institution name |
| `Institution_Address` | Filing institution address |
| `Subject_Account` | Flagged account number |
| `Case_ID` | Investigation case ID |
| `Risk_Tier` | CRITICAL / HIGH / MEDIUM |
| `Activity_Type` | Smurfing, Layering, etc. |
| `Txn_Date_From` | Earliest suspicious transaction date |
| `Txn_Date_To` | Latest suspicious transaction date |
| `Total_Transactions` | Count of suspicious transactions |
| `Total_Amount` | Sum of suspicious amounts |
| `Countries_Involved` | Countries in the transaction chain |
| `Sanctions_Hits` | Watchlist screening result |
| `Narrative` | Full investigation narrative |
| `Investigator_Name` | Name of investigator |
| `Investigator_Date` | Sign-off date |

---

## Configuration

Edit `config/config.yaml` to tune:
- **Thresholds** — CTR amount, smurfing window/count, layering chain length
- **High-risk countries** — FATF list is pre-populated
- **Risk tier boundaries** — change what score maps to which tier
- **Filing institution details** — appears in every SAR
- **sanction_list file path** — point to your own sanctions list

---

## Running Tests

```bash
pytest tests/ -v
```

---

## License

Internal PoC — not for production use without compliance review.
