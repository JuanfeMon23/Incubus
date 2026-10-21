"""Publica el catalogo de modulos y acciones de Incubus en Leo.

    cd backend; uv run python -m app.core.leo_sync [--deactivate-missing]

Se ejecuta como paso de despliegue (no al arrancar la app: Leo caido no debe
tumbar la API ni varios workers deben sincronizar a la vez).
"""

import argparse
import asyncio
import json

from app.core.leo import auth


async def main(deactivate_missing: bool) -> None:
    import app.main  # noqa: F401  (importa los routers: registra sus require_action)

    try:
        result = await auth.sync_catalog(deactivate_missing=deactivate_missing)
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    finally:
        await auth.aclose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--deactivate-missing", action="store_true")
    args = parser.parse_args()
    asyncio.run(main(args.deactivate_missing))
