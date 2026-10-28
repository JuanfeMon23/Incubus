"""Exporta el catalogo de permisos al contrato que consume el frontend.

    uv run python -m app.core.permissions_export          # escribe el JSON
    uv run python -m app.core.permissions_export --check  # sale con 1 si difiere

El contrato (`frontend/app/generated/permissions.json`) es un artefacto
generado y commiteado. No toca la BD ni arranca servicios: solo lee el
catalogo declarado en `app.core.permissions`.
"""

import json
import sys
from pathlib import Path
from typing import Any

from app.core import permissions  # noqa: F401  (declara el catalogo al importarse)
from app.core.leo import APP_SLUG, catalog

CONTRACT_PATH = (
    Path(__file__).resolve().parents[3] / "frontend" / "app" / "generated" / "permissions.json"
)
MISMATCH_MESSAGE = "tags desalineados: ejecuta uv run python -m app.core.permissions_export"
EVENT_PREFIX = "Evento:"


def build_contract() -> dict[str, Any]:
    """Contrato en el orden del catalogo; `assignable=False` en eventos de auditoria."""
    modules = []
    for module in catalog.to_payload()["modules"]:
        actions = [
            {
                "tag": f"{APP_SLUG}.{module['slug']}.{action['verb']}",
                "verb": action["verb"],
                "name": action["name"],
                "description": action.get("description", ""),
                "assignable": not action["name"].startswith(EVENT_PREFIX),
            }
            for action in module["actions"]
        ]
        modules.append(
            {
                "slug": module["slug"],
                "name": module["name"],
                "description": module.get("description", ""),
                "actions": actions,
            }
        )
    return {"app": APP_SLUG, "modules": modules}


def render_contract() -> str:
    return json.dumps(build_contract(), ensure_ascii=False, indent=2) + "\n"


def main(argv: list[str]) -> int:
    rendered = render_contract()
    if "--check" in argv:
        current = CONTRACT_PATH.read_bytes().decode("utf-8") if CONTRACT_PATH.exists() else None
        if current != rendered:
            print(MISMATCH_MESSAGE)
            return 1
        return 0
    CONTRACT_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONTRACT_PATH.write_bytes(rendered.encode("utf-8"))
    print(f"escrito {CONTRACT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
