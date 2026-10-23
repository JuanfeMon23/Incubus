"""Ajustes editables de Incubus (tabla `settings`): registro de claves + store.

Los umbrales operativos (vigencia y limites del codigo de activacion, rooms y
barrido del socket, tamanos maximos de pagina, medidas de etiqueta, tolerancia
de la traza) se declaran AQUI y se leen en cada peticion/ciclo con
`await get("<clave>")` (cache en proceso de ~10 s, invalidada al editar). Si la
BD falla o la fila falta se usa el default del registro. El modulo compartido es
`leo_sdk.settings_store`; el router vive en `app.modules.settings`.

Infraestructura (pepper, CORS, URLs, `socketio_redis_url`,
`socketio_allow_no_origin`, `database_url`) NO esta aqui: sigue en el entorno
(`app.core.config`).
"""

import logging
from typing import Any

from leo_sdk.settings_store import SettingDef, SettingsRegistry, SettingsStore

from app.core.config import LegacySettingsEnv
from app.core.database import AsyncSessionLocal
from app.core.db.settings_model import SETTINGS_MODELS

logger = logging.getLogger("incubus")

CACHE_TTL_SECONDS = 10.0


def _int(
    key: str,
    default: int,
    minimum: int,
    maximum: int,
    description: str,
    *,
    unit: str,
    security: bool = False,
) -> SettingDef:
    return SettingDef(
        key,
        "int",
        default,
        description,
        min=minimum,
        max=maximum,
        unit=unit,
        group=key.split(".", 1)[0],
        requires_security=security,
    )


INCUBUS_SETTINGS = SettingsRegistry(
    [
        _int(
            "activation.code_ttl_days", 30, 1, 365,
            "Días de vigencia de un código de activación nuevo.",
            unit="days", security=True,
        ),
        _int(
            "activation.verify_max_per_ip_doc", 5, 3, 20,
            "Intentos de verificar un código por ventana, por IP y documento.",
            unit="count", security=True,
        ),
        _int(
            "activation.verify_max_per_doc", 15, 5, 60,
            "Intentos de verificar un código por ventana, por documento "
            "(desde cualquier IP).",
            unit="count", security=True,
        ),
        _int(
            "activation.verify_window_seconds", 900, 60, 3600,
            "Duración de la ventana de los intentos de verificación.",
            unit="seconds", security=True,
        ),
        _int(
            "realtime.socket_max_rooms", 20, 5, 100,
            "Máximo de salas (rooms) que puede suscribir un socket.",
            unit="count",
        ),
        _int(
            "realtime.sweep_seconds", 30, 10, 300,
            "Cada cuántos segundos se desconectan los sockets con el token vencido.",
            unit="seconds",
        ),
        _int(
            "pagination.orders_max_page_size", 200, 50, 500,
            "Máximo de filas por página en la trazabilidad de órdenes.",
            unit="count",
        ),
        _int(
            "pagination.queue_admin_max_page_size", 100, 20, 500,
            "Máximo de filas por página en la administración de catálogos de la cola.",
            unit="count",
        ),
        _int(
            "pagination.results_max_page_size", 50, 10, 200,
            "Máximo de filas por página en la cola de resultados.",
            unit="count",
        ),
        _int(
            "labels.default_width_mm", 70, 20, 120,
            "Ancho por defecto de la etiqueta ZPL.",
            unit="mm",
        ),
        _int(
            "labels.default_height_mm", 35, 15, 120,
            "Alto por defecto de la etiqueta ZPL.",
            unit="mm",
        ),
        _int(
            "labels.default_dpi", 203, 150, 600,
            "Resolución por defecto de la impresora de etiquetas.",
            unit="dpi",
        ),
        _int(
            "trace.dedup_tolerance_seconds", 2, 1, 10,
            "Diferencia máxima entre un evento real y uno derivado para considerarlos "
            "el mismo en la trazabilidad.",
            unit="seconds",
        ),
    ]
)  # fmt: skip

store = SettingsStore(
    INCUBUS_SETTINGS,
    AsyncSessionLocal,
    SETTINGS_MODELS,
    cache_ttl=CACHE_TTL_SECONDS,
)


async def get(key: str) -> Any:
    """Valor vigente del ajuste (con cache; nunca lanza por la BD)."""
    return await store.get(key)


async def get_many(*keys: str) -> dict[str, Any]:
    return await store.get_many(keys)


async def sync_on_startup() -> None:
    """Alinea la tabla con el registro (llamar al arrancar la API). Las
    variables heredadas (`LegacySettingsEnv`) solo fijan el valor inicial de una
    clave que aun no existe. Si la BD no responde, la app arranca igual con los
    defaults (y el fallo queda en el log)."""
    try:
        result = await store.sync_registry(LegacySettingsEnv().initial_values())
    except Exception:
        logger.exception("No se pudo sincronizar la tabla de ajustes al arrancar.")
        return
    if result.inserted or result.updated or result.adjusted:
        logger.info(
            "Ajustes sincronizados: %d nuevos, %d con metadatos actualizados, "
            "%d valores ajustados al rango.",
            len(result.inserted),
            len(result.updated),
            len(result.adjusted),
        )
