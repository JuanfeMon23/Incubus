import pytest

from app.modules.results.values import ResultValueError, normalize_value

OPTIONS = [{"id": "o1", "label": "Positivo"}, {"id": "o2", "label": "Negativo"}]


def test_numerico_con_coma_decimal_y_redondeo():
    assert normalize_value("numeric", "5,26", decimals=1) == 5.3
    assert normalize_value("numeric", " 12 ", decimals=0) == 12


def test_numerico_invalido():
    with pytest.raises(ResultValueError):
        normalize_value("numeric", "abc", decimals=1)


def test_vacio_es_none():
    assert normalize_value("numeric", "", decimals=1) is None
    assert normalize_value("text", None) is None


def test_booleano():
    assert normalize_value("boolean", "true") is True
    assert normalize_value("boolean", False) is False
    with pytest.raises(ResultValueError):
        normalize_value("boolean", "quizas")


def test_opcion_debe_pertenecer_al_conjunto():
    assert normalize_value("qualitative", "o1", options=OPTIONS) == "o1"
    with pytest.raises(ResultValueError):
        normalize_value("qualitative", "zzz", options=OPTIONS)


def test_titulo_y_semicuantitativo_aceptan_opciones():
    assert normalize_value("semi_quantitative", "o2", options=OPTIONS) == "o2"
    assert normalize_value("titer", "o1", options=OPTIONS) == "o1"


def test_texto_libre_se_recorta():
    assert normalize_value("text", "  hallazgos normales  ") == "hallazgos normales"
