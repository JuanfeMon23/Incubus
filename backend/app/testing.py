"""Utilidades compartidas solo para pruebas."""

import asyncio


class Rendezvous:
    """Fuerza a dos transacciones a solaparse en un punto concreto.

    Si no hay serializacion (falta un bloqueo), ambas llegan a `wait()` antes de
    continuar. Si una espera a la otra y esta no llega (porque un bloqueo la
    serializa), se libera por tiempo."""

    def __init__(self, timeout: float = 0.4) -> None:
        self.timeout = timeout
        self.arrived = 0
        self.both = asyncio.Event()

    async def wait(self) -> None:
        self.arrived += 1
        if self.arrived >= 2:
            self.both.set()
        try:
            await asyncio.wait_for(self.both.wait(), self.timeout)
        except TimeoutError:
            self.both.set()
