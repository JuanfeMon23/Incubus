import pytest

from app.modules.results.flags import age_in_years, evaluate_flag, pick_range

# `age-units` de Vladimir: unidad -> dias.
UNIT_DAYS = {"dias": 1, "meses": 30.4375, "anos": 365.25}


def rng(**over):
    base = {
        "sex": "any",
        "age_min": None,
        "age_max": None,
        "age_unit": None,
        "low": None,
        "high": None,
        "critical_low": None,
        "critical_high": None,
        "expected_option_id": None,
        "expected_boolean": None,
        "is_active": True,
    }
    base.update(over)
    return base


def test_edad_en_anios():
    from datetime import date

    assert age_in_years(date(1985, 3, 12), today=date(2026, 3, 11)) == pytest.approx(
        40.99, abs=0.01
    )
    assert age_in_years(None) is None


def test_prefiere_rango_especifico_del_sexo():
    ranges = [
        rng(low=1, high=10),
        rng(sex="male", low=3, high=7),
        rng(sex="female", low=2, high=5),
    ]
    assert pick_range(ranges, "male", 30, UNIT_DAYS)["low"] == 3
    assert pick_range(ranges, "female", 30, UNIT_DAYS)["low"] == 2
    assert pick_range(ranges, None, 30, UNIT_DAYS)["low"] == 1


def test_filtra_por_edad_con_unidades():
    infant = rng(age_min=0, age_max=12, age_unit="meses", low=10, high=20)
    adult = rng(age_min=18, age_max=120, age_unit="anos", low=5, high=9)
    assert pick_range([infant, adult], "male", 0.5, UNIT_DAYS)["low"] == 10
    assert pick_range([infant, adult], "male", 30, UNIT_DAYS)["low"] == 5
    assert pick_range([infant, adult], "male", 5, UNIT_DAYS) is None


def test_las_unidades_de_edad_salen_del_catalogo_del_dueno():
    # 400 dias = 1.095 anos: cae en un rango de 1 a 2 anos solo si la unidad se
    # convierte con los `days` del catalogo, no con una tabla fija.
    toddler = rng(age_min=360, age_max=800, age_unit="dias", low=1, high=2)
    assert pick_range([toddler], "male", 400 / 365.25, UNIT_DAYS)["low"] == 1
    custom = {"dias": 2}  # el dueno redefine la unidad
    assert pick_range([toddler], "male", 400 / 365.25, custom) is None


def test_una_unidad_sin_catalogo_se_toma_como_anos():
    adult = rng(age_min=18, age_max=120, age_unit="desconocida", low=5, high=9)
    assert pick_range([adult], "male", 30, UNIT_DAYS)["low"] == 5


def test_ignora_rangos_inactivos():
    assert (
        pick_range([rng(low=1, high=2, is_active=False)], "male", 30, UNIT_DAYS) is None
    )


def test_banderas_numericas():
    response = rng(low=3.4, high=7.0, critical_low=2.0, critical_high=9.0)
    assert evaluate_flag(5.0, response) == "normal"
    assert evaluate_flag(3.4, response) == "normal"
    assert evaluate_flag(3.0, response) == "low"
    assert evaluate_flag(7.5, response) == "high"
    assert evaluate_flag(1.5, response) == "critical_low"
    assert evaluate_flag(9.5, response) == "critical_high"


def test_sin_rango_no_hay_bandera():
    assert evaluate_flag(5.0, None) is None
    assert evaluate_flag(5.0, rng()) is None


def test_cualitativos_contra_lo_esperado():
    assert evaluate_flag("opt-1", rng(expected_option_id="opt-1")) == "normal"
    assert evaluate_flag("opt-2", rng(expected_option_id="opt-1")) == "abnormal"
    assert evaluate_flag(True, rng(expected_boolean=False)) == "abnormal"
    assert evaluate_flag(False, rng(expected_boolean=False)) == "normal"


def test_texto_de_referencia():
    from app.modules.results.flags import reference_text

    assert reference_text(rng(low=70, high=100)) == "70 - 100"
    assert reference_text(rng(high=200)) == "< 200"
    assert reference_text(rng(low=3.5)) == "> 3.5"
    assert reference_text(rng(display_text="Negativo")) == "Negativo"
    assert reference_text(None) is None
