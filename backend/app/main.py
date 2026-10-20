"""App FastAPI de Incubus: registra routers y CORS."""

import socketio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.core.exceptions import register_exception_handlers
from app.core.realtime import QUEUE_NAMESPACE, sio
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

app = FastAPI(title="Incubus API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "PUT", "OPTIONS"],
    allow_headers=["*"],
)

register_exception_handlers(app)

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
sio.register_namespace(QueueNamespace(QUEUE_NAMESPACE))
app.mount("/socket.io", socketio.ASGIApp(sio, socketio_path=""))
