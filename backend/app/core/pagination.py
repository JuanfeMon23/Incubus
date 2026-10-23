"""Tope de `page_size` leido de Ajustes (en lugar de un `le=` fijo en la ruta)."""

from app.core import runtime_settings
from app.core.exceptions import ValidationAppError


async def enforce_max_page_size(key: str, page_size: int) -> None:
    """422 `validation_error` si `page_size` supera el ajuste `key` vigente."""
    maximum = await runtime_settings.get(key)
    if page_size > maximum:
        raise ValidationAppError(
            f"El tamaño de página máximo es {maximum}.",
            {"field": "page_size", "max": maximum},
        )
