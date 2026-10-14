import io
import re

from app.modules.orders.labels import LabelData, render_labels_pdf


def label(**over) -> LabelData:
    base = {
        "patient_name": "JUAN CARLOS GOMEZ RODRIGUEZ",
        "order_number": "26100001",
        "tube_name": "Tapa roja",
        "area_route": ["QC", "HEM"],
        "cap_color_hex": "#DC2626",
        "document": "CC 1020304050",
    }
    base.update(over)
    return LabelData(**base)


def test_un_pdf_con_una_pagina_por_etiqueta():
    pdf = render_labels_pdf([label(), label(tube_name="Tapa lila"), label()])
    assert pdf.startswith(b"%PDF")
    assert len(re.findall(rb"/Type\s*/Page\b", pdf)) == 3


def test_sin_etiquetas_devuelve_error():
    import pytest

    with pytest.raises(ValueError):
        render_labels_pdf([])


def test_el_texto_de_la_etiqueta_incluye_los_datos_clave():
    from app.modules.orders.labels import label_text_lines

    lines = label_text_lines(label())
    joined = " ".join(lines)
    assert "JUAN CARLOS GOMEZ RODRIGUEZ" in joined
    assert "26100001" in joined
    assert "QC" in joined and "HEM" in joined
    assert io.BytesIO  # silence unused import
