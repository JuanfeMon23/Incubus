"""Limitador de intentos en memoria (ventana deslizante), por proceso.

Sin awaits entre leer y escribir, por lo que es seguro dentro de un event loop.
Con varios workers el limite efectivo es por proceso; si hace falta uno global,
sustituir `hit` por un contador compartido (Redis) manteniendo la interfaz.
"""

import time
from collections import deque


class SlidingWindowLimiter:
    def __init__(self, clock=time.monotonic) -> None:
        self._clock = clock
        self._hits: dict[str, deque[float]] = {}

    def hit(self, key: str, limit: int, window_seconds: float) -> float | None:
        """Cuenta un intento. `None` si se permite; si no, segundos para reintentar."""
        now = self._clock()
        q = self._hits.setdefault(key, deque())
        while q and now - q[0] >= window_seconds:
            q.popleft()
        if len(q) >= limit:
            return max(window_seconds - (now - q[0]), 1.0)
        q.append(now)
        if len(self._hits) > 10_000:  # poda de claves ya vencidas
            stale = [k for k, v in self._hits.items() if now - v[-1] >= window_seconds]
            for k in stale:
                del self._hits[k]
        return None

    def reset(self) -> None:
        self._hits.clear()
