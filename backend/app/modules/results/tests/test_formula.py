import pytest

from app.modules.results.formula import FormulaError, evaluate_formula, formula_codes


def test_operaciones_basicas_y_precedencia():
    assert evaluate_formula("2 + 3 * 4", {}) == 14
    assert evaluate_formula("(2 + 3) * 4", {}) == 20
    assert evaluate_formula("-5 + 10 / 4", {}) == pytest.approx(-2.5)


def test_usa_codigos_de_analitos():
    values = {"COL_TOTAL": 200.0, "HDL": 50.0, "TG": 100.0}
    # Friedewald: LDL = CT - HDL - TG/5
    assert evaluate_formula("COL_TOTAL - HDL - TG / 5", values) == pytest.approx(130.0)


def test_codigos_entre_llaves():
    assert evaluate_formula("{ALT-TGP} * 2", {"ALT-TGP": 21.0}) == 42


def test_falta_un_valor_devuelve_none():
    assert evaluate_formula("A + B", {"A": 1.0}) is None


def test_division_por_cero_devuelve_none():
    assert evaluate_formula("A / B", {"A": 1.0, "B": 0.0}) is None


def test_sintaxis_invalida():
    for bad in ("2 +", "A $ B", "((1)", "1 2", "foo(1)"):
        with pytest.raises(FormulaError):
            evaluate_formula(bad, {"foo": 1.0})


def test_codigos_referenciados():
    assert formula_codes("A + {B-C} * 2 / A") == ["A", "B-C"]
