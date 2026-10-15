"""Informe de resultados en PDF (una orden finalizada)."""

from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

FLAG_LABEL = {
    "low": "Bajo",
    "high": "Alto",
    "critical_low": "Critico bajo",
    "critical_high": "Critico alto",
    "abnormal": "Anormal",
    "normal": "",
}


def _display(row: dict) -> str:
    value = row.get("value")
    if value is None:
        return "-"
    if isinstance(value, bool):
        return "Si" if value else "No"
    if row.get("options"):
        match = next((o for o in row["options"] if o["id"] == value), None)
        if match:
            return match["label"]
    return f"{value:g}" if isinstance(value, float) else str(value)


def render_report_pdf(data: dict) -> bytes:
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm
    )
    styles = getSampleStyleSheet()
    patient = data["patient"]
    story = [
        Paragraph("Informe de resultados", styles["Title"]),
        Paragraph(
            f"<b>Orden:</b> {data['order_number']} &nbsp;&nbsp; "
            f"<b>Paciente:</b> {patient['name']} &nbsp;&nbsp; "
            f"<b>Documento:</b> {patient['document_type']} {patient['document_number']}",
            styles["Normal"],
        ),
        Spacer(1, 6 * mm),
    ]
    for test in data["tests"]:
        story.append(Paragraph(f"{test['name']} ({test['code']})", styles["Heading3"]))
        rows = [["Analito", "Resultado", "Unidad", "Referencia", ""]]
        for r in test["results"]:
            if not r.get("is_reportable", True):
                continue
            rows.append(
                [
                    r["name"],
                    _display(r),
                    r.get("unit") or "",
                    r.get("reference") or "",
                    FLAG_LABEL.get(r.get("flag") or "", ""),
                ]
            )
        table = Table(rows, colWidths=[62 * mm, 32 * mm, 22 * mm, 34 * mm, 24 * mm])
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f4f4f5")),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 9),
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#d4d4d8")),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ]
            )
        )
        story += [
            table,
            Paragraph(
                f"Validado por {test['validated_by'] or '-'}"
                + (
                    f" el {test['validated_at'][:16].replace('T', ' ')}"
                    if test.get("validated_at")
                    else ""
                ),
                styles["Italic"],
            ),
            Spacer(1, 5 * mm),
        ]
    doc.build(story)
    return buffer.getvalue()
