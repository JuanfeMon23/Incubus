"""Seleccion del rango de referencia y banderas de interpretacion."""

from datetime import date

_UNIT_YEARS = {"dias": 1 / 365.25, "meses": 1 / 12, "anos": 1.0}
_SEX_MAP = {"M": "male", "F": "female"}


def age_in_years(birth_date: date | None, today: date | None = None) -> float | None:
    if birth_date is None:
        return None
    today = today or date.today()
    return (today - birth_date).days / 365.25


def _bounds_years(rng: dict) -> tuple[float | None, float | None]:
    factor = _UNIT_YEARS.get(rng.get("age_unit") or "anos", 1.0)
    low = rng.get("age_min")
    high = rng.get("age_max")
    return (
        None if low is None else low * factor,
        None if high is None else high * factor,
    )


def pick_range(
    ranges: list[dict], sex: str | None, age_years: float | None
) -> dict | None:
    """Rango que aplica al paciente: mas especifico primero (sexo, luego edad)."""
    patient_sex = _SEX_MAP.get(sex or "")
    best: tuple[int, dict] | None = None
    for rng in ranges:
        if not rng.get("is_active", True):
            continue
        rng_sex = rng.get("sex") or "any"
        if rng_sex != "any" and rng_sex != patient_sex:
            continue
        low, high = _bounds_years(rng)
        has_age = low is not None or high is not None
        if has_age:
            if age_years is None:
                continue
            if low is not None and age_years < low:
                continue
            if high is not None and age_years > high:
                continue
        score = (2 if rng_sex != "any" else 0) + (1 if has_age else 0)
        if best is None or score > best[0]:
            best = (score, rng)
    return best[1] if best else None


def evaluate_flag(value, rng: dict | None) -> str | None:
    """`normal|low|high|critical_low|critical_high|abnormal` o `None` sin referencia."""
    if rng is None or value is None:
        return None
    if isinstance(value, bool):
        expected = rng.get("expected_boolean")
        if expected is None:
            return None
        return "normal" if value == expected else "abnormal"
    if isinstance(value, str):
        expected_option = rng.get("expected_option_id")
        if expected_option is None:
            return None
        return "normal" if value == expected_option else "abnormal"

    critical_low = rng.get("critical_low")
    critical_high = rng.get("critical_high")
    low = rng.get("low")
    high = rng.get("high")
    if critical_low is not None and value < critical_low:
        return "critical_low"
    if critical_high is not None and value > critical_high:
        return "critical_high"
    if low is None and high is None:
        return None
    if low is not None and value < low:
        return "low"
    if high is not None and value > high:
        return "high"
    return "normal"


def reference_text(rng: dict | None) -> str | None:
    """Texto del rango para mostrar junto al resultado (`70 - 100`, `< 200`)."""
    if rng is None:
        return None
    if rng.get("display_text"):
        return rng["display_text"]
    low, high = rng.get("low"), rng.get("high")

    def fmt(x: float) -> str:
        return f"{x:g}"

    if low is not None and high is not None:
        return f"{fmt(low)} - {fmt(high)}"
    if high is not None:
        return f"< {fmt(high)}"
    if low is not None:
        return f"> {fmt(low)}"
    return None
