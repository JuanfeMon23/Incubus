import pytest

from app.modules.patients.cedula import CedulaParseError, parse_cedula_barcode

NUL = chr(0)


def frame(*fields: str) -> str:
    """Trama sintetica: campos separados por NUL, como los entrega el lector."""
    return NUL.join(("PubDSK_1", "", *fields, ""))


def test_nombres_con_enie():
    raw = frame("0000987654321", "NUÑEZ", "PEÑA", "MUÑOZ", "M19720229", "B+")
    c = parse_cedula_barcode(raw)
    assert c.first_last_name == "NUÑEZ"
    assert c.birth_date.isoformat() == "1972-02-29"
    assert c.blood_type == "B+"


def test_sin_tipo_de_sangre():
    c = parse_cedula_barcode(frame("0001111111111", "RAMIREZ", "LUZ", "F20001231"))
    assert c.blood_type is None
    assert c.sex == "F"


def test_fecha_imposible_es_error_de_parseo():
    raw = frame("0001111111111", "RAMIREZ", "LUZ", "F20000230", "O+")
    with pytest.raises(CedulaParseError):
        parse_cedula_barcode(raw)
