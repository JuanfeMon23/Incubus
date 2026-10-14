"""Etiquetas de tubo en PDF (una pagina por etiqueta).

Contenido: nombre completo del paciente, numero de orden, codigo de barras
Code 128 del numero de orden y acronimos de las areas a las que va el tubo.
El PDF es la salida basica; ZPL para impresora termica queda como mejora.
"""

from dataclasses import dataclass, field
from io import BytesIO

from reportlab.graphics.barcode import code128
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

LABEL_WIDTH = 70 * mm
LABEL_HEIGHT = 35 * mm


@dataclass(frozen=True)
class LabelData:
    patient_name: str
    order_number: str
    tube_name: str
    area_route: list[str] = field(default_factory=list)
    cap_color_hex: str | None = None
    document: str | None = None


def label_text_lines(label: LabelData) -> list[str]:
    route = " > ".join(label.area_route) if label.area_route else "-"
    lines = [label.patient_name, f"Orden {label.order_number}"]
    if label.document:
        lines.append(label.document)
    lines.append(f"{label.tube_name} | {route}")
    return lines


def _fit(c: canvas.Canvas, text: str, font: str, size: float, width: float) -> float:
    while size > 5 and c.stringWidth(text, font, size) > width:
        size -= 0.5
    return size


def render_labels_pdf(labels: list[LabelData]) -> bytes:
    if not labels:
        raise ValueError("No hay etiquetas para imprimir.")
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=(LABEL_WIDTH, LABEL_HEIGHT))
    margin = 3 * mm
    usable = LABEL_WIDTH - 2 * margin
    for label in labels:
        name_size = _fit(c, label.patient_name, "Helvetica-Bold", 9, usable)
        c.setFont("Helvetica-Bold", name_size)
        c.drawString(margin, LABEL_HEIGHT - 6 * mm, label.patient_name)

        c.setFont("Helvetica", 7)
        meta = f"{label.document + ' | ' if label.document else ''}Orden {label.order_number}"
        c.drawString(margin, LABEL_HEIGHT - 10 * mm, meta)

        barcode = code128.Code128(
            label.order_number, barHeight=11 * mm, barWidth=0.32 * mm, quiet=False
        )
        barcode.drawOn(c, margin, LABEL_HEIGHT - 23.5 * mm)

        route = " > ".join(label.area_route) if label.area_route else "-"
        c.setFont("Helvetica-Bold", 9)
        c.drawString(margin, 4 * mm, route)
        c.setFont("Helvetica", 6)
        c.drawRightString(LABEL_WIDTH - margin, 4 * mm, label.tube_name[:28])
        c.showPage()
    c.save()
    return buffer.getvalue()
