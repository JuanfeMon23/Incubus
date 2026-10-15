"""Normalizacion de un valor digitado segun el tipo de resultado del analito."""

OPTION_TYPES = ("qualitative", "semi_quantitative", "titer")


class ResultValueError(ValueError):
    """El valor no corresponde al tipo de resultado."""


def normalize_value(
    result_type: str,
    raw,
    *,
    decimals: int | None = None,
    options: list[dict] | None = None,
):
    """Devuelve el valor tipado (`float`, `bool`, id de opcion, `str`) o `None`."""
    if raw is None:
        return None
    if isinstance(raw, str):
        raw = raw.strip()
        if raw == "":
            return None

    if result_type in ("numeric", "calculated"):
        try:
            number = float(str(raw).replace(",", "."))
        except ValueError as exc:
            raise ResultValueError("El resultado debe ser un numero.") from exc
        return round(number, decimals) if decimals is not None else number

    if result_type == "boolean":
        if isinstance(raw, bool):
            return raw
        text = str(raw).lower()
        if text in ("true", "si", "sí", "1", "positivo"):
            return True
        if text in ("false", "no", "0", "negativo"):
            return False
        raise ResultValueError("El resultado debe ser si/no.")

    if result_type in OPTION_TYPES:
        valid = {str(o["id"]) for o in (options or [])}
        if str(raw) not in valid:
            raise ResultValueError("La opcion elegida no pertenece al conjunto.")
        return str(raw)

    return str(raw)
