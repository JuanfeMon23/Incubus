"""Etiquetas de tubo en PDF (una pagina por etiqueta).

Contenido: nombre completo del paciente, numero de orden, codigo de barras
Code 128 del numero de orden y acronimos de las areas a las que va el tubo.
El PDF es la salida basica; ZPL para impresora termica queda como mejora.
"""

from dataclasses import dataclass, field
from io import BytesIO

from reportlab.graphics import renderSVG
from reportlab.graphics.barcode import code128, createBarcodeDrawing
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


def _zpl_text(value: str) -> str:
    """Quita los caracteres de control de ZPL (`^` y `~`) de un campo de texto."""
    return value.replace("^", " ").replace("~", " ").strip()


def render_labels_zpl(
    labels: list[LabelData],
    *,
    width_mm: float = 70,
    height_mm: float = 35,
    dpi: int = 203,
) -> str:
    """Etiquetas en ZPL II (impresoras termicas tipo Zebra): un bloque por tubo.

    Mismo contenido que el PDF. `dpi` tipico: 203 (8 dots/mm) o 300.
    """
    if not labels:
        raise ValueError("No hay etiquetas para imprimir.")
    dots_per_mm = round(dpi / 25.4)  # 203 dpi -> 8, 300 dpi -> 12 (estandar ZPL)
    width = round(width_mm * dots_per_mm)
    height = round(height_mm * dots_per_mm)
    margin = round(3 * dots_per_mm)
    blocks = []
    for label in labels:
        route = " > ".join(label.area_route) if label.area_route else "-"
        meta = f"{label.document + ' | ' if label.document else ''}Orden {label.order_number}"
        blocks.append(
            "\n".join(
                [
                    "^XA",
                    "^CI28",  # UTF-8
                    f"^PW{width}",
                    f"^LL{height}",
                    f"^FO{margin},{round(height * 0.06)}^A0N,32,32^FB{width - 2 * margin},1,0,L^FD{_zpl_text(label.patient_name)}^FS",
                    f"^FO{margin},{round(height * 0.22)}^A0N,22,22^FD{_zpl_text(meta)}^FS",
                    f"^FO{margin},{round(height * 0.34)}^BY2,3,{round(height * 0.3)}^BCN,{round(height * 0.3)},N,N,N^FD{label.order_number}^FS",
                    f"^FO{margin},{round(height * 0.80)}^A0N,32,32^FD{_zpl_text(route)}^FS",
                    f"^FO{round(width * 0.62)},{round(height * 0.84)}^A0N,20,20^FD{_zpl_text(label.tube_name)[:26]}^FS",
                    "^XZ",
                ]
            )
        )
    return "\n".join(blocks) + "\n"


def render_barcode_svg(value: str, *, bar_height_mm: float = 11) -> str:
    """Code 128 como SVG (misma simbologia que el PDF y el ZPL)."""
    drawing = createBarcodeDrawing(
        "Code128",
        value=value,
        barHeight=bar_height_mm * mm,
        barWidth=0.4 * mm,
        quiet=False,
        humanReadable=False,
    )
    return renderSVG.drawToString(drawing)
