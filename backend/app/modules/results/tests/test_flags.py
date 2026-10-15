import pytest

from app.modules.results.flags import age_in_years, evaluate_flag, pick_range


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
    assert pick_range(ranges, "M", 30)["low"] == 3
    assert pick_range(ranges, "F", 30)["low"] == 2
    assert pick_range(ranges, None, 30)["low"] == 1


def test_filtra_por_edad_con_unidades():
    infant = rng(age_min=0, age_max=12, age_unit="meses", low=10, high=20)
    adult = rng(age_min=18, age_max=120, age_unit="anos", low=5, high=9)
    assert pick_range([infant, adult], "M", 0.5)["low"] == 10
    assert pick_range([infant, adult], "M", 30)["low"] == 5
    assert pick_range([infant, adult], "M", 5) is None


def test_ignora_rangos_inactivos():
    assert pick_range([rng(low=1, high=2, is_active=False)], "M", 30) is None


def test_banderas_numericas():
    r = rng(low=3.4, high=7.0, critical_low=2.0, critical_high=9.0)
    assert evaluate_flag(5.0, r) == "normal"
    assert evaluate_flag(3.4, r) == "normal"
    assert evaluate_flag(3.0, r) == "low"
    assert evaluate_flag(7.5, r) == "high"
    assert evaluate_flag(1.5, r) == "critical_low"
    assert evaluate_flag(9.5, r) == "critical_high"


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
