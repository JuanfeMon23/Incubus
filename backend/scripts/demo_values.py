"""Valores de captura plausibles para los analitos (logica pura, sin red).

Dado un analito (tal como lo expone `GET /results/tests/{id}`) devuelve el valor
a digitar: dentro del rango de referencia o, con cierta probabilidad, por fuera
(bajo, alto, critico) para que la orden traiga banderas. Reutiliza `pick_range`
de Incubus: el rango es el mismo que aplica el servidor.
"""

import random
from datetime import date

from app.modules.results.flags import age_in_years, pick_range

ABNORMAL_PROBABILITY = 0.25
CRITICAL_PROBABILITY = 0.2  # de los anormales, cuantos van mas alla del critico
OPTIONAL_FILL_PROBABILITY = 0.7


def _decimals(analyte: dict) -> int:
    value = analyte.get("decimals")
    return 2 if value is None else int(value)


def numeric_value(
    rng: dict | None, decimals: int, rand: random.Random, abnormal: bool
) -> float:
    """Numero dentro del rango (o fuera si `abnormal`). Sin rango: valor tipico."""
    low = (rng or {}).get("low")
    high = (rng or {}).get("high")
    c_low = (rng or {}).get("critical_low")
    c_high = (rng or {}).get("critical_high")
    if low is None and high is None:
        return round(rand.uniform(1, 100), decimals)
    span = (high - low) if (low is not None and high is not None) else None
    step = span if span else max(abs(high if high is not None else low) * 0.3, 0.1)
    if not abnormal:
        if low is not None and high is not None:
            value = rand.uniform(low + span * 0.1, high - span * 0.1)
        elif low is not None:
            value = low + step * rand.uniform(0.1, 1.0)
        else:
            value = max(high - step * rand.uniform(0.1, 0.9), 0.0)
        return round(value, decimals)
    if low is None:
        go_high = True
    elif high is None:
        go_high = False
    else:
        go_high = rand.random() < 0.5
    critical = rand.random() < CRITICAL_PROBABILITY
    if go_high:
        base = c_high if (critical and c_high is not None) else high
        value = base + step * rand.uniform(0.05, 0.3)
    else:
        base = c_low if (critical and c_low is not None) else low
        value = max(base - step * rand.uniform(0.05, 0.3), 0.0)
    return round(value, decimals)


def option_value(
    options: list[dict], rng: dict | None, rand: random.Random, abnormal: bool
) -> str | None:
    """Id de opcion: la esperada (normal) o una marcada/elegida como anormal."""
    if not options:
        return None
    expected = (rng or {}).get("expected_option_id")
    ids = [str(o["id"]) for o in options]
    if not abnormal:
        if expected is not None and str(expected) in ids:
            return str(expected)
        normal = [str(o["id"]) for o in options if not o.get("is_abnormal")]
        return rand.choice(normal or ids)
    others = [
        str(o["id"])
        for o in options
        if str(o["id"]) != str(expected) and (o.get("is_abnormal") or expected)
    ]
    return rand.choice(others or ids)


def value_for(
    analyte: dict,
    sex: str | None,
    birth_date: date | None,
    rand: random.Random,
    *,
    abnormal: bool,
) -> str | bool | float | None:
    """Valor a digitar para un analito; `None` = dejarlo vacio (calculado u opcional)."""
    kind = analyte["result_type"]
    if kind == "calculated":
        return None  # lo obtiene el servidor de su formula
    if not analyte.get("is_required", True) and rand.random() > (
        OPTIONAL_FILL_PROBABILITY
    ):
        return None
    ranges = analyte.get("ranges") or []
    # `GET /results/tests/{id}` expone el rango ya elegido en `range`; si solo hay
    # la lista completa (plantilla), se elige con la misma regla del servidor.
    rng = analyte.get("range") or pick_range(ranges, sex, age_in_years(birth_date))
    if kind == "numeric":
        return numeric_value(rng, _decimals(analyte), rand, abnormal)
    if kind == "boolean":
        expected = (rng or {}).get("expected_boolean")
        if expected is None:
            return rand.random() < 0.5
        return (not expected) if abnormal else bool(expected)
    if kind in ("qualitative", "semi_quantitative", "titer"):
        return option_value(analyte.get("options") or [], rng, rand, abnormal)
    return rand.choice(
        ["Sin hallazgos relevantes.", "Muestra adecuada.", "Dentro de lo esperado."]
    )


def values_for_test(
    analytes: list[dict],
    sex: str | None,
    birth_date: date | None,
    rand: random.Random,
) -> dict[str, str | bool | float | None]:
    """Valores de todos los analitos digitables de un examen (`{codigo: valor}`)."""
    out: dict[str, str | bool | float | None] = {}
    for analyte in analytes:
        if analyte["result_type"] == "calculated":
            continue
        abnormal = rand.random() < ABNORMAL_PROBABILITY
        value = value_for(analyte, sex, birth_date, rand, abnormal=abnormal)
        if value is not None:
            out[analyte["code"]] = value
    return out
