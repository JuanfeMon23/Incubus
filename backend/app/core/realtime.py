"""Transporte de tiempo real: Socket.IO.

Solo DIFUNDE: las acciones van siempre por REST. Aqui vive lo generico del
transporte (servidor `sio`, handshake, manager); los eventos y rooms de la cola
estan en `app.modules.queue` (`events`, `rooms`, `socket_handlers`).

Handshake y autenticacion
-------------------------
`authenticate_socket(environ, auth)` es el UNICO punto que decide si un socket
entra y quien es. Hoy: valida `Origin` contra `CORS_ORIGINS` y devuelve un
`Principal` anonimo (rol `unknown`).

Politica de `Origin`: un navegador siempre lo envia, asi que uno ajeno se
rechaza (aqui y, antes, por el propio python-engineio via `cors_allowed_origins`).
Sin `Origin` (herramientas que no son navegador) se rechaza salvo que
`SOCKETIO_ALLOW_NO_ORIGIN=true` (pruebas / desarrollo).

TODO(Leo): cuando se integre Leo (`programming/projects/leo/sdk/python`),
reemplazar el cuerpo de `authenticate_socket`: leer el token de `auth["token"]`
(el cliente lo manda en `io(url, {auth: {token}})`) o de la cookie de sesion en
`environ["HTTP_COOKIE"]`, validarlo con el SDK y devolver
`Principal(id=<usuario>, role=<rol>)`; `None` o excepcion = rechazo. Con el rol
se decide en `authorize_room(principal, room)` (hoy permite todo) que rooms
puede unir cada uno (p. ej. `staff:<id>` solo para ese profesional).

Escala horizontal: con `SOCKETIO_REDIS_URL` el manager es `AsyncRedisManager`
(los rooms se comparten entre procesos); sin ella, el manager en memoria.
"""

import asyncio
from dataclasses import dataclass
from typing import Any

import socketio

from app.core.config import get_settings

QUEUE_NAMESPACE = "/queue"
ANONYMOUS_ROLE = "unknown"


@dataclass(frozen=True)
class Principal:
    """Quien esta conectado. Hoy anonimo; Leo lo llenara con usuario y rol."""

    id: str | None = None
    role: str = ANONYMOUS_ROLE


def is_origin_allowed(origin: str | None) -> bool:
    settings = get_settings()
    if not origin:
        return settings.socketio_allow_no_origin
    return origin in settings.cors_origins_list


async def authenticate_socket(environ: dict[str, Any], auth: Any) -> Principal | None:
    """Decide si el socket entra. `None` = rechazado. Ver TODO(Leo) arriba."""
    if not is_origin_allowed(environ.get("HTTP_ORIGIN")):
        return None
    return Principal()


def authorize_room(principal: Principal, room: str) -> bool:
    """Punto de extension: que rooms puede unir cada principal (hoy todos)."""
    return True


def build_manager(redis_url: str | None) -> Any:
    """`None` (manager en memoria) o `AsyncRedisManager` si hay URL."""
    if not redis_url:
        return None
    try:
        return socketio.AsyncRedisManager(redis_url)
    except Exception as exc:
        raise RuntimeError(
            "SOCKETIO_REDIS_URL requiere el paquete 'redis' (uv add redis)."
        ) from exc


sio = socketio.AsyncServer(
    async_mode="asgi",
    cors_allowed_origins=get_settings().cors_origins_list,
    client_manager=build_manager(get_settings().socketio_redis_url),
)

# Entregas en orden: dos eventos seguidos de una entrada no se cruzan.
_EMIT_LOCK = asyncio.Lock()


async def emit_to_rooms(event: str, payload: dict[str, Any], rooms: list[str]) -> None:
    """Emite al namespace de la cola. Cada socket tiene su cola de envio: un
    cliente lento no retrasa a los demas (python-socketio es async)."""
    async with _EMIT_LOCK:
        await sio.emit(event, payload, to=rooms, namespace=QUEUE_NAMESPACE)
