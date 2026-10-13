"""Unificacion de preanaliticos de varios examenes.

Regla: por `category` se muestra una sola precondicion con duracion, la de
mayor duracion normalizada a minutos (ayuno 8 h + 16 h -> 16 h; iguales -> una).
Las que no tienen duracion se deduplican por texto identico (sin mayusculas ni
espacios sobrantes). Orden estable: primera aparicion.
"""

from dataclasses import dataclass

_UNIT_MINUTES = {"minutos": 1, "horas": 60, "dias": 1440}


@dataclass(frozen=True)
class EffectivePrecondition:
    category: str
    name: str
    duration_value: float | None
    duration_unit: str | None
    patient_instructions: str | None

    @property
    def duration_minutes(self) -> float | None:
        if self.duration_value is None or self.duration_unit not in _UNIT_MINUTES:
            return None
        return self.duration_value * _UNIT_MINUTES[self.duration_unit]


def _text_key(item: EffectivePrecondition) -> str:
    base = item.patient_instructions or item.name
    return " ".join(base.lower().split())


def slot_key(item: EffectivePrecondition) -> tuple:
    """Clave de unificacion: categoria+duracion, o categoria+texto si no hay."""
    if item.duration_minutes is not None:
        return (item.category, "duration")
    return (item.category, "text", _text_key(item))


def dedupe_preconditions(
    items: list[EffectivePrecondition],
) -> list[EffectivePrecondition]:
    slots: dict[tuple, EffectivePrecondition] = {}
    for item in items:
        minutes = item.duration_minutes
        key = slot_key(item)
        current = slots.get(key)
        if current is None:
            slots[key] = item
        elif minutes is not None and minutes > (current.duration_minutes or 0):
            slots[key] = item  # reemplaza conservando la posicion de la clave
    return list(slots.values())
