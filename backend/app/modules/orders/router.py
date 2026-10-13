from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.exceptions import NotFoundError
from app.modules.catalog_client.client import CatalogClient, get_catalog_client
from app.modules.orders import service
from app.modules.orders.models import Order, OrderPrecondition, OrderTest
from app.modules.queue.router import _publish, _read

Session = Annotated[AsyncSession, Depends(get_session)]
Catalog = Annotated[CatalogClient, Depends(get_catalog_client)]

router = APIRouter(tags=["orders"])
catalog_router = APIRouter(tags=["catalog"])


class PreviewInput(BaseModel):
    test_codes: list[str] = Field(default_factory=list)


class CloseReceptionInput(BaseModel):
    test_codes: list[str]
    actor: str | None = Field(default=None, max_length=120)


@catalog_router.get("/tests")
async def search_tests(
    catalog: Catalog, q: Annotated[str | None, Query(max_length=100)] = None
) -> list[dict]:
    """Busqueda de examenes activos en el catalogo de Vladimir."""
    return [
        {
            "code": t["code"],
            "name": t["name"],
            "abbreviation": t.get("abbreviation"),
        }
        for t in await catalog.search_tests(q)
    ]


@router.post("/preview")
async def preview(body: PreviewInput, catalog: Catalog) -> dict:
    """Preanaliticos ya unificados para los examenes elegidos (panel en vivo)."""
    tests, preconditions = await service.resolve_tests(catalog, body.test_codes)
    return {
        "tests": [{"code": t["code"], "name": t["name"]} for t in tests],
        "preconditions": preconditions,
    }


@router.post("/close-reception/{entry_id}")
async def close_reception(
    entry_id: UUID, body: CloseReceptionInput, session: Session, catalog: Catalog
) -> dict:
    order = await service.close_reception(
        session, catalog, entry_id, body.test_codes, body.actor
    )
    await session.commit()
    await _publish("status_changed", await _read(session, entry_id))
    return {"order_number": order.order_number, "order_id": str(order.id)}


@router.get("/{order_number}")
async def get_order(order_number: str, session: Session) -> dict:
    order = (
        await session.execute(select(Order).where(Order.order_number == order_number))
    ).scalar_one_or_none()
    if order is None:
        raise NotFoundError(
            f"No existe la orden '{order_number}'.", {"order_number": order_number}
        )
    tests = (
        await session.execute(select(OrderTest).where(OrderTest.order_id == order.id))
    ).scalars()
    pres = (
        await session.execute(
            select(OrderPrecondition).where(OrderPrecondition.order_id == order.id)
        )
    ).scalars()
    return {
        "order_number": order.order_number,
        "queue_entry_id": str(order.queue_entry_id),
        "tests": [{"code": t.test_code, "name": t.test_name} for t in tests],
        "preconditions": [
            {
                "category": p.category,
                "name": p.name,
                "duration_value": p.duration_value,
                "duration_unit": p.duration_unit,
                "patient_instructions": p.patient_instructions,
                "source_test_codes": p.source_test_codes,
            }
            for p in pres
        ],
    }
