"""Transporte de tiempo real: Socket.IO.

Solo DIFUNDE: las acciones van siempre por REST. Aqui vive lo generico del
transporte (servidor `sio`, handshake, manager); los eventos y rooms de la cola
estan en `app.modules.queue` (`events`, `rooms`, `socket_handlers`).

Autenticacion (Leo)
-------------------
`authenticate_socket(environ, auth)` es el UNICO punto que decide si un socket
entra y quien es. Contrato del handshake (lo que debe hacer el frontend):

- Conectar al namespace `/queue` de `PUBLIC_URL` (path `/socket.io`) desde un
  origen de `CORS_ORIGINS`, con credenciales (cookies HttpOnly de Leo; el
  handshake las envia solo porque es el mismo sitio).
- Un WebSocket del navegador NO puede enviar el header `DPoP`, asi que la prueba
  va en el payload `auth`: `io(url + "/queue", {auth: {dpop: "<jws>"}})`. Es una
  prueba DPoP normal (ES256, la misma llave de la sesion) con `htm = "GET"`,
  `htu = PUBLIC_URL + "/socket.io/"` (esquema + host + puerto de `PUBLIC_URL`,
  path con la barra final, sin query), `iat` dentro de +-60 s del reloj del
  servidor y un `jti` nuevo (anti-replay: cada intento/reconexion necesita una
  prueba nueva; `auth` puede ser una funcion que la genere).
- El servidor lee la cookie de acceso (`incubus_access` por defecto), verifica
  la prueba, introspecciona en Leo (misma cache de 30 s del SDK) y exige que el
  usuario tenga al menos un permiso `incubus.*`. Cualquier fallo = conexion
  rechazada (`ConnectionRefusedError("forbidden")`).

Autorizacion de rooms: `authorize_room(principal, room)`.
- `stage:<estado>`  -> permiso `view` de la pantalla que muestra esa etapa
                       (`core.permissions.STAGE_VIEW`).
- `entry:<id>`      -> `view` de alguna etapa (`ANY_STAGE_VIEW`).
- `staff:<id>`      -> `incubus.sampling.view` (toma de muestras).

Sesion con el socket abierto: en cada evento del cliente (`subscribe`, `sync`)
se revalida con la introspeccion cacheada (30 s): sesion revocada o vencida =
desconexion; permisos nuevos se aplican y los rooms que ya no corresponden se
abandonan. Ademas un barrido (cada `SOCKET_SWEEP_SECONDS`) desconecta los
sockets cuyo access token ya vencio, SIN llamar a Leo (una conexion abierta no
cuenta como actividad: la inactividad la desliza solo el heartbeat
`POST /auth/activity` del frontend). Tras una desconexion del servidor el
cliente debe pedir `/auth/me` (renueva las cookies si hace falta) y reconectar
con una prueba nueva. Un socket de un usuario inactivo puede seguir recibiendo
eventos (solo ids/estados, sin datos personales) hasta que venza su access
token.

Politica de `Origin`: un navegador siempre lo envia, asi que uno ajeno se
rechaza (aqui y, antes, por el propio python-engineio via `cors_allowed_origins`).
Sin `Origin` (herramientas que no son navegador) se rechaza salvo que
`SOCKETIO_ALLOW_NO_ORIGIN=true` (pruebas / desarrollo).

Escala horizontal: con `SOCKETIO_REDIS_URL` el manager es `AsyncRedisManager`
(los rooms se comparten entre procesos); sin ella, el manager en memoria.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field, replace
from http.cookies import CookieError, SimpleCookie
from typing import Any

import socketio
from leo_sdk import DpopError, LeoUser

from app.core.config import get_settings
from app.core.leo import APP_SLUG
from app.core.leo import auth as leo_auth
from app.core.permissions import ANY_STAGE_VIEW, SAM_VIEW, STAGE_VIEW
from app.modules.queue.rooms import ENTRY, STAFF, STAGE

log = logging.getLogger(__name__)

QUEUE_NAMESPACE = "/queue"
# Path del `htu` de la prueba DPoP del handshake (se le antepone `PUBLIC_URL`).
SOCKET_HTU_PATH = "/socket.io/"
_now = time.time  # reloj (las pruebas lo reemplazan)


@dataclass(frozen=True)
class Principal:
    """Quien esta conectado: la persona de Leo y sus permisos en Incubus."""

    id: str
    username: str
    name: str
    permissions: frozenset[str]
    access_token: str = field(repr=False, default="")
    jkt: str = field(repr=False, default="")
    expires_at: float | None = None  # epoch del vencimiento del access token

    def can(self, tag: str) -> bool:
        return tag in self.permissions

    @classmethod
    def from_user(cls, user: LeoUser) -> "Principal":
        return cls(
            id=str(user.id),
            username=user.username,
            name=user.name,
            permissions=user.permissions,
            access_token=user.access_token,
            jkt=user.jkt,
            expires_at=user.expires_at.timestamp() if user.expires_at else None,
        )


def is_origin_allowed(origin: str | None) -> bool:
    settings = get_settings()
    if not origin:
        return settings.socketio_allow_no_origin
    return origin in settings.cors_origins_list


def _cookie(environ: dict[str, Any], name: str) -> str | None:
    jar: SimpleCookie = SimpleCookie()
    try:
        jar.load(environ.get("HTTP_COOKIE", ""))
    except CookieError:
        return None
    morsel = jar.get(name)
    return morsel.value if morsel else None


def _is_incubus_user(user: LeoUser) -> bool:
    return not user.is_service and any(
        p.startswith(f"{APP_SLUG}.") for p in user.permissions
    )


async def authenticate_socket(environ: dict[str, Any], auth: Any) -> Principal | None:
    """Decide si el socket entra. `None` = rechazado. Ver contrato arriba."""
    if not is_origin_allowed(environ.get("HTTP_ORIGIN")):
        return None
    settings = leo_auth.settings
    access = _cookie(environ, settings.cookie_name(settings.access_cookie_name))
    proof = auth.get("dpop") if isinstance(auth, dict) else None
    if not access or not isinstance(proof, str):
        return None
    try:
        verified = await leo_auth.sessions.verify_proof("GET", SOCKET_HTU_PATH, proof)
    except DpopError as exc:
        log.info("Prueba DPoP del socket rechazada: %s", exc.reason)
        return None
    user = await leo_auth.sessions.user_for(access, verified.jkt)
    if user is None or not _is_incubus_user(user):
        return None
    return Principal.from_user(user)


def is_expired(principal: Principal) -> bool:
    return principal.expires_at is not None and principal.expires_at <= _now()


async def refresh_principal(principal: Principal) -> Principal | None:
    """Revalida la sesion de un socket abierto (introspeccion cacheada).

    `None` = ya no es valida (vencida, revocada o sin permisos de Incubus).
    Si Leo no responde se conserva el principal (no se expulsa a todos por una
    caida de Leo); el barrido por vencimiento sigue vigente.
    """
    if is_expired(principal):
        return None
    try:
        user = await leo_auth.sessions.user_for(principal.access_token, principal.jkt)
    except Exception:
        log.warning("No se pudo revalidar la sesion del socket.", exc_info=True)
        return principal
    if user is None or not _is_incubus_user(user):
        return None
    return replace(Principal.from_user(user), expires_at=principal.expires_at)


def authorize_room(principal: Principal, room: str) -> bool:
    """Que rooms puede unir cada principal (ver docstring del modulo)."""
    kind, _, value = room.partition(":")
    if kind == STAGE:
        tag = STAGE_VIEW.get(value)
        return tag is not None and principal.can(tag)
    if kind == ENTRY:
        return any(principal.can(t) for t in ANY_STAGE_VIEW)
    if kind == STAFF:
        return principal.can(SAM_VIEW)
    return False


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
