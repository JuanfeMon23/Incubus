"""Tubos de una orden: agrupa los examenes por su tipo de muestra preferido.

Regla: cada examen aporta su tipo de muestra **preferido y activo** (si ninguno
es preferido, el primero activo; si no hay ninguno, el examen no genera tubo).
Los examenes con el mismo tipo comparten tubo y el volumen requerido es el mayor.
Los tubos se ordenan por `draw_order` (orden de extraccion), luego por nombre.
"""

from dataclasses import dataclass, field


@dataclass
class Tube:
    sample_type_id: str
    code: str
    name: str
    cap_color_hex: str | None
    draw_order: int | None
    collection_instructions: str | None
    required_volume_ml: float | None
    test_codes: list[str] = field(default_factory=list)


def _chosen_link(test: dict) -> dict | None:
    active = [s for s in test.get("sample_types", []) if s.get("is_active", True)]
    if not active:
        return None
    return next((s for s in active if s.get("is_preferred")), active[0])


def group_samples(tests: list[dict], sample_types: dict[str, dict]) -> list[Tube]:
    tubes: dict[str, Tube] = {}
    for test in tests:
        link = _chosen_link(test)
        if link is None:
            continue
        type_id = str(link["sample_type_id"])
        detail = sample_types.get(type_id, {})
        tube = tubes.get(type_id)
        if tube is None:
            tube = tubes[type_id] = Tube(
                sample_type_id=type_id,
                code=detail.get("code", type_id),
                name=detail.get("name", type_id),
                cap_color_hex=detail.get("cap_color_hex"),
                draw_order=detail.get("draw_order"),
                collection_instructions=detail.get("collection_instructions"),
                required_volume_ml=None,
            )
        volume = link.get("required_volume_ml")
        if volume is not None and (
            tube.required_volume_ml is None or volume > tube.required_volume_ml
        ):
            tube.required_volume_ml = volume
        tube.test_codes.append(test["code"])
    return sorted(
        tubes.values(),
        key=lambda t: (t.draw_order is None, t.draw_order or 0, t.name),
    )
