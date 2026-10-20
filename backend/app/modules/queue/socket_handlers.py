"""Namespace Socket.IO `/queue`: handshake, suscripcion a rooms y `sync`.

Solo lectura: el cliente no escribe nada por aqui (las acciones van por REST).

Cliente -> servidor (todos responden con acknowledgement):
- `subscribe`   {rooms: [...]} -> {ok: true, joined: [...todos sus rooms]}
                o {ok: false, error: "invalid_rooms"|"too_many_rooms"|"forbidden"}.
                Atomico: si un room falla no se une ninguno.
- `unsubscribe` {rooms: [...]} -> {ok: true, joined: [...]}  (mismas validaciones
                de formato; salir de un room ajeno es inocuo).
- `sync`        (sin datos) -> {ok: true, entries: [QueueEntryLive...]} con las
                entradas ACTUALES de los rooms `stage:*` suscritos. Opcional: el
                cliente puede preferir `GET /queue`. Emitirlo al (re)conectar
                tras re-suscribirse.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import socketio
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import AsyncSessionLocal
from app.core.realtime import authenticate_socket, authorize_room
from app.modules.queue import events, rooms, service


@asynccontextmanager
async def open_session() -> AsyncIterator[AsyncSession]:
    """Sesion propia del handler (no hay request/Depends en Socket.IO)."""
    async with AsyncSessionLocal() as session:
        yield session


def _error(code: str) -> dict[str, Any]:
    return {"ok": False, "error": code}


def _parse_rooms(data: Any) -> list[str] | None:
    """Lista de rooms validos y sin repetir, o `None` si el payload es invalido."""
    if not isinstance(data, dict) or not isinstance(data.get("rooms"), list):
        return None
    if not all(rooms.is_valid_room(r) for r in data["rooms"]):
        return None
    return list(dict.fromkeys(data["rooms"]))


class QueueNamespace(socketio.AsyncNamespace):
    def _joined(self, sid: str) -> list[str]:
        return [r for r in self.rooms(sid) if r != sid]  # cada socket tiene su sid

    async def on_connect(self, sid: str, environ: dict, auth: Any = None) -> None:
        try:
            principal = await authenticate_socket(environ, auth)
        except Exception:  # noqa: BLE001 - cualquier fallo de autenticacion rechaza
            principal = None
        if principal is None:
            raise socketio.exceptions.ConnectionRefusedError("forbidden")
        await self.save_session(sid, {"principal": principal})

    async def on_subscribe(self, sid: str, data: Any = None) -> dict[str, Any]:
        wanted = _parse_rooms(data)
        if wanted is None:
            return _error("invalid_rooms")
        principal = (await self.get_session(sid))["principal"]
        if not all(authorize_room(principal, r) for r in wanted):
            return _error("forbidden")
        current = self._joined(sid)
        if len(set(current) | set(wanted)) > get_settings().socketio_max_rooms:
            return _error("too_many_rooms")
        for room in wanted:
            await self.enter_room(sid, room)
        return {"ok": True, "joined": self._joined(sid)}

    async def on_unsubscribe(self, sid: str, data: Any = None) -> dict[str, Any]:
        unwanted = _parse_rooms(data)
        if unwanted is None:
            return _error("invalid_rooms")
        for room in unwanted:
            await self.leave_room(sid, room)
        return {"ok": True, "joined": self._joined(sid)}

    async def on_sync(self, sid: str, data: Any = None) -> dict[str, Any]:
        statuses = rooms.stage_statuses(self._joined(sid))
        if not statuses:
            return {"ok": True, "entries": []}
        async with open_session() as session:
            rows = await service.list_entries(session, statuses)
        entries = [
            events.to_live(events.to_read(*row).model_dump(mode="json")).model_dump(
                mode="json"
            )
            for row in rows
        ]
        return {"ok": True, "entries": entries}
