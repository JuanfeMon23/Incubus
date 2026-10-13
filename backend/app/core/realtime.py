"""Difusion en tiempo real de la cola por WebSocket (solo servidor -> clientes).

Las acciones van por REST; despues de confirmar la transaccion el router llama
`broadcast`. Un cliente que reconecta debe volver a listar la cola.
"""

import asyncio
from typing import Any

from fastapi import WebSocket


class ConnectionManager:
    def __init__(self) -> None:
        self._connections: set[WebSocket] = set()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._connections.add(ws)

    def disconnect(self, ws: WebSocket) -> None:
        self._connections.discard(ws)

    async def broadcast(self, event: dict[str, Any]) -> None:
        async def _send(ws: WebSocket) -> None:
            try:
                await ws.send_json(event)
            except Exception:  # noqa: BLE001 - conexion rota: se descarta
                self.disconnect(ws)

        await asyncio.gather(*(_send(ws) for ws in list(self._connections)))


queue_events = ConnectionManager()
