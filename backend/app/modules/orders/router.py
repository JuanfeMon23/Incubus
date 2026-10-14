from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.exceptions import NotFoundError
from app.modules.catalog_client.client import CatalogClient, get_catalog_client
from app.modules.orders import service
from app.modules.orders.labels import LabelData, render_labels_pdf
from app.modules.orders.models import Order, OrderPrecondition, OrderSample, OrderTest
from app.modules.queue.models import Patient
from app.modules.queue.router import _publish, _read

Session = Annotated[AsyncSession, Depends(get_session)]
Catalog = Annotated[CatalogClient, Depends(get_catalog_client)]

router = APIRouter(tags=["orders"])
catalog_router = APIRouter(tags=["catalog"])


class PreviewInput(BaseModel):
    test_codes: list[str] = Field(default_factory=list)


class CheckInput(BaseModel):
    key: str = Field(max_length=64)
    met: bool | None = None
    note: str | None = None


class CloseReceptionInput(BaseModel):
    test_codes: list[str]
    actor: str | None = Field(default=None, max_length=120)
    precondition_checks: list[CheckInput] = Field(default_factory=list)


class PrintLabelsInput(BaseModel):
    professional_id: str = Field(max_length=64)
    professional_name: str = Field(max_length=150)
    actor: str | None = Field(default=None, max_length=120)


class StageChecksInput(BaseModel):
    stage: str = Field(pattern="^(reception|sampling)$")
    checks: list[CheckInput]
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


@catalog_router.get("/staff")
async def list_staff(catalog: Catalog) -> list[dict]:
    """Personal activo de Vladimir (profesionales de toma de muestras)."""
    return await catalog.list_staff()


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
        session,
        catalog,
        entry_id,
        body.test_codes,
        body.actor,
        [c.model_dump() for c in body.precondition_checks],
    )
    await session.commit()
    await _publish("status_changed", await _read(session, entry_id))
    return {"order_number": order.order_number, "order_id": str(order.id)}


class CollectInput(BaseModel):
    actor: str | None = Field(default=None, max_length=120)


def sample_dict(s: OrderSample) -> dict:
    return {
        "id": str(s.id),
        "sample_type_code": s.sample_type_code,
        "name": s.name,
        "cap_color_hex": s.cap_color_hex,
        "draw_order": s.draw_order,
        "collection_instructions": s.collection_instructions,
        "required_volume_ml": s.required_volume_ml,
        "test_codes": s.test_codes,
        "area_route": s.area_route,
        "labels_printed_at": s.labels_printed_at.isoformat()
        if s.labels_printed_at
        else None,
        "collected_at": s.collected_at.isoformat() if s.collected_at else None,
        "collected_by": s.collected_by,
    }


async def _order_detail(session: AsyncSession, order: Order) -> dict:
    tests = (
        await session.execute(select(OrderTest).where(OrderTest.order_id == order.id))
    ).scalars()
    pres = (
        await session.execute(
            select(OrderPrecondition).where(OrderPrecondition.order_id == order.id)
        )
    ).scalars()
    samples = (
        await session.execute(
            select(OrderSample)
            .where(OrderSample.order_id == order.id)
            .order_by(OrderSample.draw_order.nulls_last(), OrderSample.name)
        )
    ).scalars()
    return {
        "order_number": order.order_number,
        "queue_entry_id": str(order.queue_entry_id),
        "tests": [{"code": t.test_code, "name": t.test_name} for t in tests],
        "preconditions": [
            {
                "key": p.key,
                "category": p.category,
                "name": p.name,
                "duration_value": p.duration_value,
                "duration_unit": p.duration_unit,
                "patient_instructions": p.patient_instructions,
                "source_test_codes": p.source_test_codes,
                "reception_met": p.reception_met,
                "reception_note": p.reception_note,
                "sampling_met": p.sampling_met,
                "sampling_note": p.sampling_note,
            }
            for p in pres
        ],
        "samples": [sample_dict(s) for s in samples],
    }


@router.get("/by-entry/{entry_id}")
async def get_order_by_entry(entry_id: UUID, session: Session) -> dict:
    order = (
        await session.execute(select(Order).where(Order.queue_entry_id == entry_id))
    ).scalar_one_or_none()
    if order is None:
        raise NotFoundError(
            f"La entrada '{entry_id}' no tiene orden.",
            {"queue_entry_id": str(entry_id)},
        )
    return await _order_detail(session, order)


async def _set_collected(
    session: AsyncSession, sample_id: UUID, actor: str | None, collected: bool
) -> dict:
    sample = await session.get(OrderSample, sample_id)
    if sample is None:
        raise NotFoundError(
            f"No existe la muestra '{sample_id}'.", {"id": str(sample_id)}
        )
    sample.collected_at = datetime.now(UTC) if collected else None
    sample.collected_by = actor if collected else None
    await session.commit()
    return sample_dict(sample)


@router.post("/samples/{sample_id}/collect")
async def collect_sample(sample_id: UUID, body: CollectInput, session: Session) -> dict:
    return await _set_collected(session, sample_id, body.actor, True)


@router.post("/samples/{sample_id}/uncollect")
async def uncollect_sample(
    sample_id: UUID, body: CollectInput, session: Session
) -> dict:
    return await _set_collected(session, sample_id, body.actor, False)


async def _entry_order(session: AsyncSession, entry_id: UUID) -> Order:
    order = (
        await session.execute(select(Order).where(Order.queue_entry_id == entry_id))
    ).scalar_one_or_none()
    if order is None:
        raise NotFoundError(
            f"La entrada '{entry_id}' no tiene orden.",
            {"queue_entry_id": str(entry_id)},
        )
    return order


@router.post("/by-entry/{entry_id}/print-labels")
async def print_labels(
    entry_id: UUID, body: PrintLabelsInput, session: Session, catalog: Catalog
) -> dict:
    """Imprime etiquetas: crea tubos, asigna profesional y pasa a espera de toma."""
    order = await service.print_labels(
        session,
        catalog,
        entry_id,
        body.professional_id,
        body.professional_name,
        body.actor,
    )
    await session.commit()
    await _publish("status_changed", await _read(session, entry_id))
    return await _order_detail(session, order)


@router.post("/by-entry/{entry_id}/samples")
async def prepare_samples(entry_id: UUID, session: Session, catalog: Catalog) -> dict:
    """Crea (si faltan) los tubos para mostrarlos en la vista de impresion."""
    await _entry_order(session, entry_id)
    await service.ensure_samples(session, catalog, entry_id)
    await session.commit()
    return await _order_detail(session, await _entry_order(session, entry_id))


@router.get("/by-entry/{entry_id}/labels.pdf")
async def labels_pdf(entry_id: UUID, session: Session) -> Response:
    order = await _entry_order(session, entry_id)
    patient = await session.get(Patient, order.patient_id)
    tubes = list(
        (
            await session.execute(
                select(OrderSample)
                .where(OrderSample.order_id == order.id)
                .order_by(OrderSample.draw_order.nulls_last(), OrderSample.name)
            )
        ).scalars()
    )
    if not tubes:
        raise NotFoundError(
            "La orden aun no tiene tubos para etiquetar.",
            {"order": order.order_number},
        )
    name = " ".join(
        filter(
            None,
            [
                patient.first_name,
                patient.second_name,
                patient.first_last_name,
                patient.second_last_name,
            ],
        )
    )
    labels = [
        LabelData(
            patient_name=name,
            order_number=order.order_number,
            tube_name=t.name,
            area_route=list(t.area_route),
            cap_color_hex=t.cap_color_hex,
            document=f"{patient.document_type} {patient.document_number}",
        )
        for t in tubes
    ]
    filename = f"etiquetas-{order.order_number}.pdf"
    return Response(
        content=render_labels_pdf(labels),
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


@router.post("/by-entry/{entry_id}/precondition-checks")
async def precondition_checks(
    entry_id: UUID, body: StageChecksInput, session: Session
) -> dict:
    await service.save_checks(
        session, entry_id, body.stage, [c.model_dump() for c in body.checks], body.actor
    )
    await session.commit()
    return await _order_detail(session, await _entry_order(session, entry_id))


@router.get("/{order_number}")
async def get_order(order_number: str, session: Session) -> dict:
    order = (
        await session.execute(select(Order).where(Order.order_number == order_number))
    ).scalar_one_or_none()
    if order is None:
        raise NotFoundError(
            f"No existe la orden '{order_number}'.", {"order_number": order_number}
        )
    return await _order_detail(session, order)
