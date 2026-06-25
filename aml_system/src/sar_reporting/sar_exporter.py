"""
SAR Exporter
=============
Fills the user-provided PDF SAR template with SARData field values.

Strategy (in order of preference):
  1. Try to fill as a fillable AcroForm PDF using pypdf
  2. If no form fields detected, generate a standalone formatted PDF
     using reportlab as fallback

The template PDF should be placed at:
  reports/templates/SAR_template.pdf

AcroForm field names that will be filled (must match field names in your PDF):
  See SAR_FIELD_MAPPING below — you can rename fields in your PDF to match,
  or update the mapping dict here to match your PDF's field names.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from src.sar_reporting.sar_generator import SARData
from src.utils.helpers import ensure_dir, load_config, now_utc
from src.utils.logger import get_logger

log = get_logger(__name__)

# ── Mapping: SARData field → PDF form field name ─────────────────────────────
# Update these keys to match the actual field names in your PDF template.
SAR_FIELD_MAPPING = {
    "sar_id":                      "SAR_ID",
    "filing_date":                 "Filing_Date",
    "report_type":                 "Report_Type",
    "filing_institution":          "Institution_Name",
    "filing_institution_address":  "Institution_Address",
    "filing_institution_tin":      "Institution_TIN",
    "contact_name":                "Contact_Name",
    "contact_phone":               "Contact_Phone",
    "contact_email":               "Contact_Email",
    "subject_account":             "Subject_Account",
    "subject_bank":                "Subject_Bank",
    "subject_location":            "Subject_Location",
    "case_id":                     "Case_ID",
    "risk_tier":                   "Risk_Tier",
    "risk_score":                  "Risk_Score",
    "triggered_rules":             "Triggered_Rules",
    "activity_type":               "Activity_Type",
    "transaction_date_start":      "Txn_Date_From",
    "transaction_date_end":        "Txn_Date_To",
    "total_transactions":          "Total_Transactions",
    "total_amount":                "Total_Amount",
    "countries_involved":          "Countries_Involved",
    "payment_types":               "Payment_Types",
    "sanctions_hits":              "Sanctions_Hits",
    "narrative":                   "Narrative",
    "investigator_name":           "Investigator_Name",
    "investigator_date":           "Investigator_Date",
    "investigator_title":          "Investigator_Title",
}


class SARExporter:
    """
    Exports filled SAR PDF reports.

    Usage:
        exporter = SARExporter()
        path = exporter.export(sar_data, case_id="CASE-ABC123")
    """

    def __init__(self, config_path: str = "config/config.yaml"):
        cfg = load_config(config_path)
        sar_cfg = cfg["sar"]
        self.template_path = Path(sar_cfg.get("template_pdf", "reports/templates/SAR_template.pdf"))
        self.output_dir = Path(sar_cfg.get("output_dir", "data/outputs/sar"))
        ensure_dir(self.output_dir)

    # ── Public API ────────────────────────────────────────────────────────

    def export(self, sar_data: SARData, case_id: str = "") -> str:
        """
        Export a filled SAR PDF for the given SARData.

        Args:
            sar_data: Populated SARData from SARGenerator.
            case_id:  Optional case ID for filename.

        Returns:
            Absolute path to the output PDF.
        """
        filename = f"SAR_{sar_data.sar_id}_{case_id or 'CASE'}.pdf"
        output_path = self.output_dir / filename

        if self.template_path.exists():
            success = self._fill_acroform(sar_data, output_path)
            if not success:
                log.warning("AcroForm fill failed or no form fields — generating standalone PDF")
                self._generate_standalone_pdf(sar_data, output_path)
        else:
            log.warning(
                f"SAR template not found at {self.template_path}. "
                "Generating standalone SAR PDF using reportlab."
            )
            self._generate_standalone_pdf(sar_data, output_path)

        log.info(f"SAR exported → {output_path}")
        return str(output_path)

    def export_json(self, sar_data: SARData, case_id: str = "") -> str:
        """Also save a JSON copy for archival / audit trail."""
        filename = f"SAR_{sar_data.sar_id}_{case_id or 'CASE'}.json"
        path = self.output_dir / filename
        with open(path, "w", encoding="utf-8") as f:
            json.dump(sar_data.to_dict(), f, indent=2)
        log.info(f"SAR JSON archived → {path}")
        return str(path)

    def export_batch(self, sar_list: list[tuple[SARData, str]]) -> list[str]:
        """
        Export multiple SARs.

        Args:
            sar_list: List of (SARData, case_id) tuples.

        Returns:
            List of output PDF paths.
        """
        paths = []
        for sar_data, case_id in sar_list:
            path = self.export(sar_data, case_id)
            self.export_json(sar_data, case_id)
            paths.append(path)
        log.info(f"Batch export complete — {len(paths)} SAR(s) generated")
        return paths

    # ── Private — AcroForm fill ───────────────────────────────────────────

    def _fill_acroform(self, sar_data: SARData, output_path: Path) -> bool:
        """
        Fill a fillable PDF (AcroForm) with SAR data using pypdf.

        Returns True if successful, False if the PDF has no form fields.
        """
        try:
            from pypdf import PdfReader, PdfWriter
            from pypdf.generic import NameObject, create_string_object

            reader = PdfReader(str(self.template_path))
            writer = PdfWriter()
            writer.append(reader)

            # Check if PDF has AcroForm fields
            if "/AcroForm" not in reader.trailer.get("/Root", {}):
                log.debug("PDF has no AcroForm — falling back to standalone generation")
                return False

            fields = reader.get_fields()
            if not fields:
                return False

            # Build fill dict: PDF field name → value
            sar_dict = sar_data.to_dict()
            fill_values: dict[str, str] = {}

            for sar_key, pdf_field_name in SAR_FIELD_MAPPING.items():
                value = sar_dict.get(sar_key, "")
                if pdf_field_name in fields:
                    fill_values[pdf_field_name] = value
                else:
                    log.debug(f"PDF field not found: '{pdf_field_name}' (skipping)")

            if not fill_values:
                log.debug("No matching form fields found in PDF")
                return False

            # Fill the form
            writer.update_page_form_field_values(writer.pages[0], fill_values)

            # For multi-page forms, update all pages
            if len(writer.pages) > 1:
                for page in writer.pages[1:]:
                    try:
                        writer.update_page_form_field_values(page, fill_values)
                    except Exception:
                        pass

            with open(output_path, "wb") as f:
                writer.write(f)

            log.info(
                f"AcroForm filled: {len(fill_values)} fields written → {output_path.name}"
            )
            return True

        except ImportError:
            log.warning("pypdf not installed — cannot fill AcroForm PDF")
            return False
        except Exception as e:
            log.warning(f"AcroForm fill error: {e}")
            return False

    # ── Private — Standalone PDF generation ──────────────────────────────

    def _generate_standalone_pdf(self, sar_data: SARData, output_path: Path) -> None:
        """
        Generate a fully formatted SAR PDF from scratch using reportlab.
        This is used when no fillable template is available.
        """
        try:
            from reportlab.lib import colors
            from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY
            from reportlab.lib.pagesizes import letter
            from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
            from reportlab.lib.units import inch
            from reportlab.platypus import (
                SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
                HRFlowable,
            )

            doc = SimpleDocTemplate(
                str(output_path),
                pagesize=letter,
                rightMargin=0.75 * inch,
                leftMargin=0.75 * inch,
                topMargin=0.75 * inch,
                bottomMargin=0.75 * inch,
            )

            styles = getSampleStyleSheet()
            story = []

            # ── Header ────────────────────────────────────────────────────
            title_style = ParagraphStyle(
                "Title",
                parent=styles["Heading1"],
                fontSize=16,
                textColor=colors.HexColor("#1A237E"),
                spaceAfter=4,
                alignment=TA_CENTER,
            )
            sub_style = ParagraphStyle(
                "Sub",
                parent=styles["Normal"],
                fontSize=10,
                textColor=colors.HexColor("#555555"),
                alignment=TA_CENTER,
                spaceAfter=12,
            )
            label_style = ParagraphStyle(
                "Label",
                parent=styles["Normal"],
                fontSize=9,
                textColor=colors.HexColor("#333333"),
                fontName="Helvetica-Bold",
            )
            value_style = ParagraphStyle(
                "Value",
                parent=styles["Normal"],
                fontSize=9,
                textColor=colors.HexColor("#000000"),
            )
            narrative_style = ParagraphStyle(
                "Narrative",
                parent=styles["Normal"],
                fontSize=9,
                leading=14,
                alignment=TA_JUSTIFY,
            )
            section_style = ParagraphStyle(
                "Section",
                parent=styles["Heading2"],
                fontSize=11,
                textColor=colors.HexColor("#1A237E"),
                spaceBefore=12,
                spaceAfter=4,
                borderPad=2,
            )

            story.append(Paragraph("SUSPICIOUS ACTIVITY REPORT (SAR)", title_style))
            story.append(Paragraph(
                f"SAR ID: {sar_data.sar_id} &nbsp;&nbsp;|&nbsp;&nbsp; "
                f"Filing Date: {sar_data.filing_date} &nbsp;&nbsp;|&nbsp;&nbsp; "
                f"Case ID: {sar_data.case_id}",
                sub_style,
            ))
            story.append(HRFlowable(width="100%", thickness=2, color=colors.HexColor("#1A237E")))
            story.append(Spacer(1, 10))

            def section(title: str) -> None:
                story.append(Paragraph(title, section_style))
                story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#BBBBBB")))
                story.append(Spacer(1, 4))

            def field_table(rows: list[tuple[str, str]]) -> None:
                tbl_data = [
                    [Paragraph(lbl, label_style), Paragraph(val, value_style)]
                    for lbl, val in rows
                ]
                tbl = Table(tbl_data, colWidths=[2.2 * inch, 5.0 * inch])
                tbl.setStyle(TableStyle([
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("ROWBACKGROUNDS", (0, 0), (-1, -1), [colors.HexColor("#F5F5F5"), colors.white]),
                    ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#DDDDDD")),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]))
                story.append(tbl)
                story.append(Spacer(1, 8))

            # ── Section 1: Filing Institution ──────────────────────────────
            section("1. FILING INSTITUTION")
            field_table([
                ("Institution Name:", sar_data.filing_institution),
                ("Address:", sar_data.filing_institution_address),
                ("TIN:", sar_data.filing_institution_tin),
                ("Contact Name:", sar_data.contact_name),
                ("Contact Phone:", sar_data.contact_phone),
                ("Contact Email:", sar_data.contact_email),
            ])

            # ── Section 2: Subject Information ────────────────────────────
            section("2. SUBJECT OF REPORT")
            field_table([
                ("Account Number:", sar_data.subject_account),
                ("Associated Bank(s):", sar_data.subject_bank),
                ("Geographic Location(s):", sar_data.subject_location),
            ])

            # ── Section 3: Suspicious Activity ────────────────────────────
            section("3. SUSPICIOUS ACTIVITY DETAILS")
            field_table([
                ("Risk Tier:", sar_data.risk_tier),
                ("Risk Score:", sar_data.risk_score),
                ("Activity Type:", sar_data.activity_type),
                ("Triggered Rules:", sar_data.triggered_rules),
                ("Transaction Period:", f"{sar_data.transaction_date_start} to {sar_data.transaction_date_end}"),
                ("No. of Transactions:", sar_data.total_transactions),
                ("Total Amount:", sar_data.total_amount),
                ("Countries Involved:", sar_data.countries_involved),
                ("Payment Types:", sar_data.payment_types),
            ])

            # ── Section 4: Sanctions ──────────────────────────────────────
            section("4. SANCTIONS / WATCHLIST SCREENING")
            field_table([("Screening Result:", sar_data.sanctions_hits)])

            # ── Section 5: Narrative ──────────────────────────────────────
            section("5. NARRATIVE DESCRIPTION OF SUSPICIOUS ACTIVITY")
            story.append(Spacer(1, 4))
            for para in sar_data.narrative.split("\n\n"):
                if para.strip():
                    story.append(Paragraph(para.replace("\n", " "), narrative_style))
                    story.append(Spacer(1, 6))

            # ── Section 6: Investigator Sign-off ─────────────────────────
            section("6. INVESTIGATOR CERTIFICATION")
            field_table([
                ("Prepared By:", sar_data.investigator_name),
                ("Title:", sar_data.investigator_title),
                ("Date:", sar_data.investigator_date),
                ("Signature:", "_" * 40),
            ])

            story.append(Spacer(1, 20))
            footer_style = ParagraphStyle(
                "Footer",
                parent=styles["Normal"],
                fontSize=7,
                textColor=colors.HexColor("#999999"),
                alignment=TA_CENTER,
            )
            story.append(Paragraph(
                "This report is confidential and intended solely for the designated regulatory authority. "
                "Unauthorized disclosure is prohibited under applicable AML/CFT regulations.",
                footer_style,
            ))

            doc.build(story)
            log.info(f"Standalone SAR PDF generated → {output_path.name}")

        except ImportError:
            log.error("reportlab not installed — cannot generate SAR PDF")
        except Exception as e:
            log.error(f"SAR PDF generation error: {e}", exc_info=True)
