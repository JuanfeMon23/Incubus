from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.exceptions import NotFoundError
from app.core.leo import CatalogReader, actor_name, record_audit
from app.core.permissions import (
    RES_ENTER,
    RES_VALIDATE,
    CanEnterResults,
    CanValidateResults,
    CanViewDelivery,
    CanViewLab,
    CanViewResults,
)
from app.modules.catalog_client.client import CatalogClient, get_catalog_client
from app.modules.orders.models import Order, OrderResult, OrderTest
from app.modules.queue import events
from app.modules.queue.models import Patient, QueueEntry
from app.modules.queue.transitions import QueueStatus
from app.modules.results import service
from app.modules.results.flags import age_in_years, pick_range, reference_text
from app.modules.results.report import render_report_pdf

Session = Annotated[AsyncSession, Depends(get_session)]
Catalog = Annotated[CatalogClient, Depends(get_catalog_client)]

lab_router = APIRouter(tags=["laboratorio"])
results_router = APIRouter(tags=["resultados"])
delivery_router = APIRouter(tags=["entrega"])
validators_router = APIRouter(tags=["catalog"])


class ValuesInput(BaseModel):
    professional_id: str = Field(max_length=64)
    professional_name: str = Field(max_length=150)
    values: dict[str, str | bool | float | None] = Field(default_factory=dict)


# ------------------------------------------------------------------ catalogo


@validators_router.get("/validators")
async def list_validators(catalog: Catalog, _user: CatalogReader) -> list[dict]:
    """Profesionales que validan: quienes son encargados de al menos un area."""
    by_staff: dict[str, dict] = {}
    for area in await catalog.areas_with_managers():
        staff_id = area.get("manager_staff_id")
        if not staff_id:
            continue
        item = by_staff.setdefault(
            staff_id,
            {"id": staff_id, "name": area.get("manager_name") or staff_id, "areas": []},
        )
        item["areas"].append(
            {"id": area["id"], "code": area["code"], "name": area["name"]}
        )
    return sorted(by_staff.values(), key=lambda v: v["name"])


# ------------------------------------------------------ recepcion laboratorio


@lab_router.get("/reception")
async def lab_reception(
    session: Session,
    _user: CanViewLab,
    q: Annotated[str | None, Query(max_length=100)] = None,
) -> list[dict]:
    """Cola de ordenes con tubos que esperan el check de entrada al laboratorio."""
    return await service.lab_reception_queue(session, q)


# ---------------------------------------------------------------- resultados


@results_router.get("/queue")
async def results_queue(
    session: Session,
    catalog: Catalog,
    _user: CanViewResults,
    professional_id: Annotated[str, Query(max_length=64)],
    q: Annotated[str | None, Query(max_length=100)] = None,
) -> list[dict]:
    """Ordenes con examenes pendientes de validar en las areas del profesional."""
    return await service.results_queue(session, catalog, professional_id, q)


@results_router.get("/orders/{entry_id}")
async def get_order(
    entry_id: UUID,
    session: Session,
    catalog: Catalog,
    _user: CanViewResults,
    professional_id: Annotated[str, Query(max_length=64)],
) -> dict:
    """Examenes de la orden en las areas del profesional (validados incluidos)."""
    return await service.order_for_professional(
        session, catalog, entry_id, professional_id
    )


@results_router.get("/tests/{order_test_id}")
async def get_test(
    order_test_id: UUID,
    session: Session,
    catalog: Catalog,
    _user: CanViewResults,
    professional_id: Annotated[str, Query(max_length=64)],
) -> dict:
    detail = await service.test_detail(session, catalog, order_test_id, professional_id)
    await session.commit()  # la estructura se crea la primera vez que se abre
    return detail


@results_router.put("/tests/{order_test_id}/values")
async def save_values(
    order_test_id: UUID,
    body: ValuesInput,
    session: Session,
    catalog: Catalog,
    user: CanEnterResults,
) -> dict:
    """Guarda valores. `professional_*` identifica al profesional del area (se
    conserva hasta enlazar usuarios de Leo con personal de Vladimir); quien
    captura queda como el usuario autenticado."""
    detail = await service.save_values(
        session,
        catalog,
        order_test_id,
        body.professional_id,
        body.professional_name,
        body.values,
        actor_name(user),
    )
    await session.commit()
    await record_audit(
        RES_ENTER,
        user,
        entity_type="order_test",
        entity_id=order_test_id,
        after={
            "validation_status": detail["validation_status"],
            "analytes_with_value": sum(
                1 for r in detail["results"] if r.get("value") is not None
            ),
        },
    )
    return detail


@results_router.post("/tests/{order_test_id}/validate")
async def validate_test(
    order_test_id: UUID,
    body: ValuesInput,
    session: Session,
    catalog: Catalog,
    user: CanValidateResults,
) -> dict:
    detail, finalized = await service.validate_test(
        session,
        catalog,
        order_test_id,
        body.professional_id,
        body.professional_name,
        body.values,
        actor_name(user),
    )
    await session.commit()
    await record_audit(
        RES_VALIDATE,
        user,
        entity_type="order_test",
        entity_id=order_test_id,
        before={"validation_status": "pending"},
        after={"validation_status": "validated", "order_finalized": finalized},
    )
    if finalized:
        entry_id = (
            await session.execute(
                select(Order.queue_entry_id)
                .join(OrderTest, OrderTest.order_id == Order.id)
                .where(OrderTest.id == order_test_id)
            )
        ).scalar_one()
        await events.publish_entry(session, entry_id, events.STATUS_CHANGED)
    return {**detail, "order_finalized": finalized}


# -------------------------------------------------------------------- entrega


async def _finalized_order(
    session: AsyncSession, order_number: str
) -> tuple[Order, Patient]:
    row = (
        await session.execute(
            select(Order, QueueEntry)
            .join(QueueEntry, QueueEntry.id == Order.queue_entry_id)
            .where(Order.order_number == order_number)
        )
    ).first()
    if row is None or row[1].status != QueueStatus.FINALIZADA.value:
        raise NotFoundError(
            f"No hay resultados finalizados para la orden '{order_number}'.",
            {"order_number": order_number},
        )
    order = row[0]
    return order, await session.get(Patient, order.patient_id)


async def _delivery_payload(
    session: AsyncSession, order: Order, patient: Patient
) -> dict:
    tests = list(
        (
            await session.execute(
                select(OrderTest)
                .where(OrderTest.order_id == order.id)
                .order_by(OrderTest.test_code)
            )
        ).scalars()
    )
    age = age_in_years(patient.birth_date)
    out_tests = []
    for t in tests:
        rows = list(
            (
                await session.execute(
                    select(OrderResult)
                    .where(OrderResult.order_test_id == t.id)
                    .order_by(OrderResult.sort_order)
                )
            ).scalars()
        )
        out_tests.append(
            {
                "code": t.test_code,
                "name": t.test_name,
                "area": t.area_code,
                "validated_by": t.validated_by_name,
                "validated_at": t.validated_at.isoformat() if t.validated_at else None,
                "results": [
                    {
                        "code": r.analyte_code,
                        "name": r.analyte_name,
                        "section": r.section_name,
                        "value": (r.value or {}).get("v"),
                        "unit": r.unit,
                        "options": r.options,
                        "reference": reference_text(
                            pick_range(r.ranges, patient.sex, age)
                        ),
                        "flag": r.flag,
                        "is_reportable": r.is_reportable,
                    }
                    for r in rows
                ],
            }
        )
    return {
        "order_number": order.order_number,
        "patient": {
            "name": service._patient_context(patient)["name"],
            "document_type": patient.document_type,
            "document_number": patient.document_number,
            "sex": patient.sex,
            "birth_date": patient.birth_date.isoformat()
            if patient.birth_date
            else None,
        },
        "tests": out_tests,
    }


@delivery_router.get("/orders/{order_number}")
async def delivery_order(
    order_number: str, session: Session, _user: CanViewDelivery
) -> dict:
    """Resultados finalizados de una orden (para el servicio de pacientes)."""
    order, patient = await _finalized_order(session, order_number)
    return await _delivery_payload(session, order, patient)


@delivery_router.get("/orders/{order_number}/report.pdf")
async def delivery_report(
    order_number: str, session: Session, _user: CanViewDelivery
) -> Response:
    order, patient = await _finalized_order(session, order_number)
    data = await _delivery_payload(session, order, patient)
    return Response(
        content=render_report_pdf(data),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="resultados-{order_number}.pdf"'
        },
    )
