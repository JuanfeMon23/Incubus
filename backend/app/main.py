"""App FastAPI de Incubus: registra routers, CORS y la integracion con Leo."""

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import socketio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from leo_sdk import leo_router

from app.core.config import get_settings
from app.core.exceptions import register_exception_handlers
from app.core.leo import auth
from app.core.realtime import QUEUE_NAMESPACE, sio
from app.modules.catalog_client.client import close_token_provider
from app.modules.orders.router import catalog_router
from app.modules.orders.router import router as orders_router
from app.modules.queue.router import catalogs_router, patients_router, queue_router
from app.modules.queue.socket_handlers import QueueNamespace
from app.modules.results.router import (
    delivery_router,
    lab_router,
    results_router,
    validators_router,
)

queue_namespace = QueueNamespace(QUEUE_NAMESPACE)
log = logging.getLogger(__name__)


async def _sweep_expired_sockets() -> None:
    """Desconecta sockets con el access token vencido (sin llamar a Leo)."""
    while True:
        await asyncio.sleep(get_settings().socketio_sweep_seconds)
        try:
            await queue_namespace.disconnect_expired()
        except Exception:
            log.exception("Fallo el barrido de sockets vencidos.")


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    # Falla al arrancar si algun `require_action` usa un tag sin declarar. La
    # sincronizacion con Leo NO va aqui (ver `python -m app.core.leo_sync`).
    auth.check_catalog()
    sweeper = asyncio.create_task(_sweep_expired_sockets())
    try:
        yield
    finally:
        sweeper.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await sweeper
        await close_token_provider()
        await auth.aclose()


app = FastAPI(title="Incubus API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "PUT", "OPTIONS"],
    # `DPoP`: prueba de posesion de la sesion de Leo en cada peticion.
    allow_headers=["Content-Type", "DPoP", "Authorization", "X-Request-ID"],
)

register_exception_handlers(app)
auth.install(app)  # errores de Leo con el formato {code, message, details}
app.include_router(leo_router(auth))  # /auth/login /callback /me /activity /logout

app.include_router(catalogs_router, prefix="/api/v1")
app.include_router(patients_router, prefix="/api/v1/patients")
app.include_router(queue_router, prefix="/api/v1/queue")
app.include_router(orders_router, prefix="/api/v1/orders")
app.include_router(catalog_router, prefix="/api/v1/catalog")
app.include_router(validators_router, prefix="/api/v1/catalog")
app.include_router(lab_router, prefix="/api/v1/lab")
app.include_router(results_router, prefix="/api/v1/results")
app.include_router(delivery_router, prefix="/api/v1/delivery")

# Socket.IO en /socket.io (namespace /queue). `app` sigue siendo la app FastAPI.
sio.register_namespace(queue_namespace)
app.mount("/socket.io", socketio.ASGIApp(sio, socketio_path=""))
