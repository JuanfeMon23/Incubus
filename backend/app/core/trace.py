"""Traza de una prueba: eventos append-only en `order_test_events`.

`record_test_event` agrega el evento a la MISMA sesion (transaccion) que la
mutacion que describe: si esta se revierte, el evento tambien. El actor es el
mismo que ya manejan los servicios (`Actor`) o el `LeoUser` que recibe
`record_audit`. `details` guarda datos de la operacion (valores de captura SI),
nunca documentos ni nombres del paciente.
"""

from collections.abc import Mapping
from contextvars import ContextVar
from typing import Any
from uuid import UUID

from fastapi.encoders import jsonable_encoder
from leo_sdk import LeoUser
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.types import ASGIApp, Receive, Scope, Send

from app.core.leo import Actor
from app.modules.orders.models import OrderSample, OrderTest, OrderTestEvent

SUMMARY_MAX = 300
REQUEST_ID_MAX = 64

_request_id: ContextVar[str | None] = ContextVar("trace_request_id", default=None)


class RequestIdMiddleware:
    """Guarda `X-Request-ID` (si llega) para que los eventos lo registren."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        value = None
        for key, raw in scope.get("headers", []):
            if key == b"x-request-id":
                value = raw.decode("latin-1").strip()[:REQUEST_ID_MAX] or None
                break
        token = _request_id.set(value)
        try:
            await self.app(scope, receive, send)
        finally:
            _request_id.reset(token)


def as_uuid(value: object) -> UUID | None:
    """UUID de un id externo (p. ej. personal de Vladimir) o `None` si no lo es."""
    if isinstance(value, UUID):
        return value
    try:
        return UUID(str(value))
    except (ValueError, TypeError):
        return None


def _actor(actor: Actor | LeoUser | None) -> Actor:
    if actor is None:
        return Actor()
    return actor if isinstance(actor, Actor) else Actor.of(actor)


async def record_test_event(
    session: AsyncSession,
    step: str,
    actor: Actor | LeoUser | None,
    order_id: UUID,
    order_test_id: UUID | None = None,
    sample_id: UUID | None = None,
    *,
    summary: str,
    details: Mapping[str, Any] | None = None,
    staff_id: object = None,
) -> OrderTestEvent:
    """Inserta un evento en la transaccion de `session`.

    `order_test_id=None` es un evento de la orden; `sample_id` lo liga a un tubo.
    `staff_id` (personal de Vladimir) solo se guarda si es un UUID.
    """
    who = _actor(actor)
    event = OrderTestEvent(
        order_id=order_id,
        order_test_id=order_test_id,
        order_sample_id=sample_id,
        step=step,
        actor_name=who.name,
        actor_user_id=who.user_id,
        staff_id=as_uuid(staff_id) if staff_id is not None else None,
        summary=summary[:SUMMARY_MAX],
        details=jsonable_encoder(dict(details or {})),
        request_id=_request_id.get(),
    )
    session.add(event)
    await session.flush()  # fija el orden de `occurred_at` (clock_timestamp)
    return event


async def record_sample_events(
    session: AsyncSession,
    step: str,
    actor: Actor | LeoUser | None,
    sample: OrderSample,
    *,
    summary: str,
    details: Mapping[str, Any] | None = None,
) -> None:
    """Un evento por prueba cuyo codigo esta en el tubo (`details.sample_id`)."""
    tests = (
        await session.execute(
            select(OrderTest.id, OrderTest.test_code).where(
                OrderTest.order_id == sample.order_id,
                OrderTest.test_code.in_(list(sample.test_codes)),
            )
        )
    ).all()
    for test_id, code in sorted(tests, key=lambda t: t[1]):
        await record_test_event(
            session,
            step,
            actor,
            sample.order_id,
            test_id,
            sample.id,
            summary=summary,
            details={
                "sample_id": sample.id,
                "sample_type": sample.sample_type_code,
                "test_code": code,
                **(details or {}),
            },
        )
