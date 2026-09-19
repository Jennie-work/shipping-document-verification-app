"""Portable JSON, CSV, and PDF exports for verification results."""

from __future__ import annotations

import csv
from datetime import datetime, timezone
from io import BytesIO, StringIO
import json
from typing import Any
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from .service import ProcessingArtifacts, comparison_rows


def _generated_at() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def report_payload(artifacts: ProcessingArtifacts) -> dict[str, Any]:
    email_by_id = {email["email_id"]: email for email in artifacts.emails}
    cases = []
    for email_id, submission in artifacts.submission.items():
        detail = artifacts.internal_results[email_id]
        email = email_by_id[email_id]
        cases.append(
            {
                "email_id": email_id,
                "subject": str(email.get("subject", "")),
                "from": str(email.get("from", "")),
                "submission": submission,
                "processing_status": detail.get("processing_status", detail.get("task_status")),
                "processing_attempts": detail.get("processing_attempts", 1),
                "retry_count": detail.get("retry_count", 0),
                "extracted": detail.get("extracted", {}),
                "mismatches": detail.get("mismatches", []),
                "error_history": detail.get("error_history", []),
                "human_review": detail.get("human_review"),
            }
        )
    return {
        "generated_at": _generated_at(),
        "summary": artifacts.summary,
        "cases": cases,
    }


def results_json_bytes(artifacts: ProcessingArtifacts) -> bytes:
    return (json.dumps(report_payload(artifacts), indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def results_csv_bytes(artifacts: ProcessingArtifacts) -> bytes:
    output = StringIO(newline="")
    fieldnames = [
        "email_id",
        "subject",
        "category",
        "submission_status",
        "processing_status",
        "review_reason",
        "review_decision",
        "processing_attempts",
        "error_count",
        "field",
        "si_value",
        "bl_value",
        "field_status",
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    email_by_id = {email["email_id"]: email for email in artifacts.emails}
    for email_id, submission in artifacts.submission.items():
        email = email_by_id[email_id]
        detail = artifacts.internal_results[email_id]
        base = {
            "email_id": email_id,
            "subject": str(email.get("subject", "")),
            "category": submission["category"],
            "submission_status": submission["status"],
            "processing_status": detail.get("processing_status", detail.get("task_status", "")),
            "review_reason": submission.get("review_reason") or "",
            "review_decision": detail.get("review_state", ""),
            "processing_attempts": detail.get("processing_attempts", 1),
            "error_count": len(detail.get("error_history", [])),
        }
        if submission["category"] == "BL_COMPARISON":
            for row in comparison_rows(detail):
                writer.writerow(
                    {
                        **base,
                        "field": row["Field"],
                        "si_value": row["SI"],
                        "bl_value": row["BL"],
                        "field_status": row["Status"],
                    }
                )
        else:
            writer.writerow(base)
    return output.getvalue().encode("utf-8-sig")


def _safe(value: Any) -> str:
    return escape(str(value if value not in (None, "") else "-"))


def results_pdf_bytes(artifacts: ProcessingArtifacts) -> bytes:
    """Build a complete, paginated verification report."""
    buffer = BytesIO()
    page_size = landscape(A4)
    doc = SimpleDocTemplate(
        buffer,
        pagesize=page_size,
        rightMargin=14 * mm,
        leftMargin=14 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title="Shipping Document Verification Report",
        author="CargoCheck",
    )
    styles = getSampleStyleSheet()
    styles.add(
        ParagraphStyle(
            name="ReportTitle",
            parent=styles["Title"],
            fontName="Helvetica-Bold",
            fontSize=22,
            leading=26,
            textColor=colors.HexColor("#161616"),
            spaceAfter=4 * mm,
        )
    )
    styles.add(
        ParagraphStyle(
            name="SectionTitle",
            parent=styles["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=13,
            leading=16,
            textColor=colors.HexColor("#161616"),
            spaceBefore=5 * mm,
            spaceAfter=2.5 * mm,
        )
    )
    styles.add(
        ParagraphStyle(
            name="SmallCell",
            parent=styles["BodyText"],
            fontName="Helvetica",
            fontSize=7.5,
            leading=9.5,
            textColor=colors.HexColor("#202020"),
        )
    )
    styles.add(
        ParagraphStyle(
            name="TinyCell",
            parent=styles["BodyText"],
            fontName="Helvetica",
            fontSize=6.5,
            leading=8,
            textColor=colors.HexColor("#202020"),
        )
    )

    story: list[Any] = [
        Paragraph("Shipping Document Verification Report", styles["ReportTitle"]),
        Paragraph(
            f"Generated {_safe(_generated_at())}. Includes processing errors, retry history, human review decisions, and SI/BL comparison results.",
            styles["BodyText"],
        ),
        Spacer(1, 5 * mm),
        Paragraph("Summary", styles["SectionTitle"]),
    ]

    summary = artifacts.summary
    summary_rows = [
        ["Emails", "Comparison requests", "No mismatch", "Mismatch", "Manual review", "Failed"],
        [
            summary.get("emails_processed", 0),
            summary.get("comparison_requests", 0),
            summary.get("no_mismatch", 0),
            summary.get("mismatch", 0),
            summary.get("manual_review", 0),
            summary.get("failed", 0),
        ],
    ]
    summary_table = Table(summary_rows, colWidths=[42 * mm] * 6, repeatRows=1)
    summary_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#161616")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#777777")),
                ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#F5F1E8")),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    story.extend([summary_table, Paragraph("All processed cases", styles["SectionTitle"])])

    email_by_id = {email["email_id"]: email for email in artifacts.emails}
    result_rows: list[list[Any]] = [["Email ID", "Subject", "Category", "Result", "Processing", "Reason / fields"]]
    for email_id, result in artifacts.submission.items():
        detail = artifacts.internal_results[email_id]
        reason = result.get("review_reason") or ", ".join(result.get("defect_fields", [])) or "-"
        result_rows.append(
            [
                Paragraph(_safe(email_id), styles["SmallCell"]),
                Paragraph(_safe(email_by_id[email_id].get("subject", "")), styles["SmallCell"]),
                Paragraph(_safe(result["category"]), styles["SmallCell"]),
                Paragraph(_safe(result["status"]), styles["SmallCell"]),
                Paragraph(_safe(detail.get("processing_status", detail.get("task_status"))), styles["SmallCell"]),
                Paragraph(_safe(reason), styles["SmallCell"]),
            ]
        )
    result_table = Table(
        result_rows,
        colWidths=[24 * mm, 78 * mm, 34 * mm, 27 * mm, 31 * mm, 59 * mm],
        repeatRows=1,
    )
    result_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#161616")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 8),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#AAAAAA")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F5F1E8")]),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story.extend([result_table, PageBreak(), Paragraph("Cases requiring action", styles["SectionTitle"])])

    action_ids = [
        email_id
        for email_id, result in artifacts.submission.items()
        if result["status"] != "OK" or artifacts.internal_results[email_id].get("human_review")
    ]
    if not action_ids:
        story.append(Paragraph("No cases require action.", styles["BodyText"]))
    for index, email_id in enumerate(action_ids):
        result = artifacts.submission[email_id]
        detail = artifacts.internal_results[email_id]
        subject = email_by_id[email_id].get("subject", "")
        story.append(
            Paragraph(
                f"{_safe(email_id)} - {_safe(subject)}",
                styles["SectionTitle"],
            )
        )
        metadata = (
            f"Result: {_safe(result['status'])} | Processing: "
            f"{_safe(detail.get('processing_status', detail.get('task_status')))} | "
            f"Attempts: {_safe(detail.get('processing_attempts', 1))}"
        )
        story.append(Paragraph(metadata, styles["BodyText"]))
        if result["category"] == "BL_COMPARISON":
            comparison_data: list[list[Any]] = [["Field", "SI value", "BL value", "Status"]]
            for row in comparison_rows(detail):
                comparison_data.append(
                    [
                        Paragraph(_safe(row["Field"]), styles["TinyCell"]),
                        Paragraph(_safe(row["SI"]), styles["TinyCell"]),
                        Paragraph(_safe(row["BL"]), styles["TinyCell"]),
                        Paragraph(_safe(row["Status"]), styles["TinyCell"]),
                    ]
                )
            comparison_table = Table(
                comparison_data,
                colWidths=[42 * mm, 80 * mm, 80 * mm, 34 * mm],
                repeatRows=1,
            )
            comparison_table.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E5E0D6")),
                        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#999999")),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("TOPPADDING", (0, 0), (-1, -1), 3),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                    ]
                )
            )
            story.extend([Spacer(1, 2 * mm), comparison_table])
        if detail.get("error_history"):
            last_error = detail["error_history"][-1]
            story.append(
                Paragraph(
                    f"Latest error: {_safe(last_error.get('type'))}: {_safe(last_error.get('message'))}",
                    styles["BodyText"],
                )
            )
        if detail.get("human_review"):
            review = detail["human_review"]
            story.append(
                Paragraph(
                    f"Human review: {_safe(review.get('decision'))} at {_safe(review.get('reviewed_at'))}. Note: {_safe(review.get('note'))}",
                    styles["BodyText"],
                )
            )
        if index < len(action_ids) - 1:
            story.append(Spacer(1, 3 * mm))

    def add_page_number(canvas: Any, document: Any) -> None:
        canvas.saveState()
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(colors.HexColor("#555555"))
        canvas.drawString(14 * mm, 8 * mm, "CargoCheck verification report")
        canvas.drawRightString(page_size[0] - 14 * mm, 8 * mm, f"Page {document.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=add_page_number, onLaterPages=add_page_number)
    return buffer.getvalue()
