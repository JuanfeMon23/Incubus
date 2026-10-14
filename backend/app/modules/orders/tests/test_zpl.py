from app.modules.orders.labels import LabelData, render_labels_zpl


def label(**over) -> LabelData:
    base = {
        "patient_name": "JUAN CARLOS GOMEZ RODRIGUEZ",
        "order_number": "26100001",
        "tube_name": "Tapa roja",
        "area_route": ["QUI", "HEM"],
        "document": "CC 1020304050",
    }
    base.update(over)
    return LabelData(**base)


def test_un_bloque_zpl_por_etiqueta():
    zpl = render_labels_zpl([label(), label(tube_name="Tapa lila")])
    assert zpl.count("^XA") == 2
    assert zpl.count("^XZ") == 2


def test_incluye_codigo_de_barras_code128_de_la_orden_y_datos():
    zpl = render_labels_zpl([label()])
    assert "^BCN" in zpl  # Code 128
    assert "^FD26100001^FS" in zpl
    assert "JUAN CARLOS GOMEZ RODRIGUEZ" in zpl
    assert "QUI > HEM" in zpl


def test_dimensiones_segun_dpi_y_tamano():
    zpl = render_labels_zpl([label()], width_mm=70, height_mm=35, dpi=203)
    assert "^PW560" in zpl  # 70 mm a 203 dpi
    assert "^LL280" in zpl  # 35 mm a 203 dpi


def test_escapa_caracteres_de_control_de_zpl():
    zpl = render_labels_zpl([label(patient_name="NUNEZ^~ PEREZ")])
    assert "^~" not in zpl.split("^FD", 2)[1].split("^FS")[0]


def test_sin_etiquetas_error():
    import pytest

    with pytest.raises(ValueError):
        render_labels_zpl([])
