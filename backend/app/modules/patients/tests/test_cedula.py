import pytest

from app.modules.patients.cedula import CedulaParseError, parse_cedula_barcode

# Trama sintetica con la estructura de la cedula amarilla (campos de ancho fijo
# rellenos con NUL). Validar con muestras reales (pendiente documentado).
RAW = (
    "\x00\x00PubDSK_1\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00"
    "\x000001020304050\x00GOMEZ\x00\x00\x00\x00RODRIGUEZ\x00\x00"
    "JUAN\x00\x00CARLOS\x00\x00\x00\x00M19850312\x0005001\x00O+\x00"
)


def test_parsea_campos_principales():
    c = parse_cedula_barcode(RAW)
    assert c.document_number == "1020304050"
    assert c.first_last_name == "GOMEZ"
    assert c.second_last_name == "RODRIGUEZ"
    assert c.first_name == "JUAN"
    assert c.second_name == "CARLOS"
    assert c.sex == "M"
    assert c.birth_date.isoformat() == "1985-03-12"
    assert c.blood_type == "O+"


def test_sin_segundo_apellido_ni_segundo_nombre():
    raw = (
        "PubDSK_1\x00\x00\x000000123456789\x00PEREZ\x00\x00LUCIA\x00F19990101\x00A-\x00"
    )
    c = parse_cedula_barcode(raw)
    assert c.document_number == "123456789"
    assert c.first_last_name == "PEREZ"
    assert c.first_name == "LUCIA"
    assert c.second_last_name is None and c.second_name is None
    assert c.sex == "F" and c.blood_type == "A-"


def test_trama_invalida():
    with pytest.raises(CedulaParseError):
        parse_cedula_barcode("hola mundo")
