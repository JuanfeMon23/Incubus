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
        attempts = self._hits.setdefault(key, deque())
        while attempts and now - attempts[0] >= window_seconds:
            attempts.popleft()
        if len(attempts) >= limit:
            return max(window_seconds - (now - attempts[0]), 1.0)
        attempts.append(now)
        if len(self._hits) > 10_000:  # poda de claves ya vencidas
            stale = [
                stale_key
                for stale_key, value in self._hits.items()
                if now - value[-1] >= window_seconds
            ]
            for stale_key in stale:
                del self._hits[stale_key]
        return None

    def reset(self) -> None:
        self._hits.clear()
