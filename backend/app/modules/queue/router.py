from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.exceptions import ConflictError, NotFoundError, ValidationAppError
from app.modules.orders.errors import UnansweredPreconditionsError
from app.modules.orders.models import Order, OrderSample
from app.modules.orders.service import unanswered_checks
from app.modules.patients.cedula import CedulaParseError, parse_cedula_barcode
from app.modules.queue import events, service
from app.modules.queue.models import (
    DocumentType,
    Patient,
    Priority,
    RemovalReason,
    ReturnReason,
)
from app.modules.queue.schemas import (
    CatalogRead,
    ClaimInput,
    DraftInput,
    HistoryRead,
    PatientRead,
    PatientUpdate,
    PriorityRead,
    QueueEntryCreate,
    QueueEntryRead,
    QueueStatusLiteral,
    ReasonedActionInput,
)
from app.modules.queue.transitions import QueueStatus

Session = Annotated[AsyncSession, Depends(get_session)]

catalogs_router = APIRouter(tags=["catalogos"])
patients_router = APIRouter(tags=["patients"])
queue_router = APIRouter(tags=["queue"])


# --- Catalogos parametrizados -------------------------------------------------


@catalogs_router.get("/priorities", response_model=list[PriorityRead])
async def list_priorities(session: Session) -> list[Priority]:
    stmt = select(Priority).where(Priority.is_active).order_by(Priority.rank)
    return list((await session.execute(stmt)).scalars())


@catalogs_router.get("/document-types", response_model=list[CatalogRead])
async def list_document_types(session: Session) -> list[DocumentType]:
    """Tipos de documento de identidad parametrizados en BD (CC, TI, CE, PA...)."""
    stmt = (
        select(DocumentType).where(DocumentType.is_active).order_by(DocumentType.code)
    )
    return list((await session.execute(stmt)).scalars())


@catalogs_router.get("/removal-reasons", response_model=list[CatalogRead])
async def list_removal_reasons(session: Session) -> list[RemovalReason]:
    stmt = (
        select(RemovalReason)
        .where(RemovalReason.is_active)
        .order_by(RemovalReason.name)
    )
    return list((await session.execute(stmt)).scalars())


@catalogs_router.get("/return-reasons", response_model=list[CatalogRead])
async def list_return_reasons(session: Session) -> list[ReturnReason]:
    stmt = (
        select(ReturnReason).where(ReturnReason.is_active).order_by(ReturnReason.name)
    )
    return list((await session.execute(stmt)).scalars())


# --- Pacientes ----------------------------------------------------------------


@patients_router.post("/parse-cedula")
async def parse_cedula(body: dict) -> dict:
    """Interpreta la trama del PDF417 de la cedula (`{"raw": "..."}`)."""
    try:
        data = parse_cedula_barcode(str(body.get("raw", "")))
    except CedulaParseError as exc:
        raise ValidationAppError(str(exc), {"field": "raw"}) from exc
    return {
        "document_type": "CC",
        "document_number": data.document_number,
        "first_name": data.first_name,
        "second_name": data.second_name,
        "first_last_name": data.first_last_name,
        "second_last_name": data.second_last_name,
        "sex": data.sex,
        "birth_date": data.birth_date.isoformat(),
        "blood_type": data.blood_type,
    }


@patients_router.get("/lookup", response_model=PatientRead)
async def lookup_patient(
    session: Session,
    document_number: Annotated[str, Query(min_length=3, max_length=20)],
    document_type: Annotated[str, Query(max_length=8)] = "CC",
) -> Patient:
    """Paciente existente por documento (para autocompletar el formulario)."""
    patient = (
        await session.execute(
            select(Patient).where(
                Patient.document_type == document_type,
                Patient.document_number == document_number,
            )
        )
    ).scalar_one_or_none()
    if patient is None:
        raise NotFoundError(
            "No hay un paciente registrado con ese documento.",
            {"document_type": document_type, "document_number": document_number},
        )
    return patient


@patients_router.patch("/{patient_id}", response_model=PatientRead)
async def update_patient(
    patient_id: UUID, body: PatientUpdate, session: Session
) -> Patient:
    patient = await session.get(Patient, patient_id)
    if patient is None:
        raise NotFoundError(
            f"No existe el paciente '{patient_id}'.", {"id": str(patient_id)}
        )
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(patient, field, value)
    await session.commit()
    return patient


# --- Cola ---------------------------------------------------------------------


@queue_router.get("", response_model=list[QueueEntryRead])
async def list_queue(
    session: Session,
    status_filter: Annotated[
        list[QueueStatusLiteral] | None, Query(alias="status")
    ] = None,
    professional_id: Annotated[str | None, Query(max_length=64)] = None,
) -> list[QueueEntryRead]:
    statuses = (
        [QueueStatus(s) for s in status_filter]
        if status_filter
        else [s for s in QueueStatus if s is not QueueStatus.RETIRADO]
    )
    rows = await service.list_entries(session, statuses, professional_id)
    return [events.to_read(*row) for row in rows]


@queue_router.post(
    "", response_model=QueueEntryRead, status_code=status.HTTP_201_CREATED
)
async def enter_queue(body: QueueEntryCreate, session: Session) -> QueueEntryRead:
    entry = await service.enter_queue(
        session, body.patient, body.priority_id, body.actor
    )
    await session.commit()
    return await events.publish_entry(session, entry.id, events.ENTRY_CREATED)


@queue_router.post("/call-next", response_model=QueueEntryRead)
async def call_next(body: ClaimInput, session: Session) -> QueueEntryRead:
    """Recepcion llama al siguiente paciente (no se elige uno en concreto)."""
    entry = await service.claim_next(session, body.actor)
    await session.commit()
    return await events.publish_entry(session, entry.id, events.STATUS_CHANGED)


@queue_router.get("/{entry_id}", response_model=QueueEntryRead)
async def get_entry(entry_id: UUID, session: Session) -> QueueEntryRead:
    return await events.read_entry(session, entry_id)


@queue_router.get("/{entry_id}/history", response_model=list[HistoryRead])
async def entry_history(entry_id: UUID, session: Session):
    return await service.history(session, entry_id)


@queue_router.post("/{entry_id}/claim", response_model=QueueEntryRead)
async def claim(entry_id: UUID, body: ClaimInput, session: Session) -> QueueEntryRead:
    """Toma al paciente: pre-recepcion -> en atencion de recepcion, o espera de
    toma -> en atencion de toma de muestras (solo el profesional asignado)."""
    await service.claim(
        session, entry_id, actor=body.actor, professional_id=body.professional_id
    )
    await session.commit()
    return await events.publish_entry(session, entry_id, events.STATUS_CHANGED)


@queue_router.post("/{entry_id}/return", response_model=QueueEntryRead)
async def return_entry(
    entry_id: UUID, body: ReasonedActionInput, session: Session
) -> QueueEntryRead:
    await service.return_entry(
        session, entry_id, actor=body.actor, reason_id=body.reason_id, note=body.note
    )
    await session.commit()
    return await events.publish_entry(session, entry_id, events.STATUS_CHANGED)


@queue_router.post("/{entry_id}/remove", response_model=QueueEntryRead)
async def remove_entry(
    entry_id: UUID, body: ReasonedActionInput, session: Session
) -> QueueEntryRead:
    await service.change_status(
        session,
        entry_id,
        QueueStatus.RETIRADO,
        actor=body.actor,
        removal_reason_id=body.reason_id,
        note=body.note,
    )
    await session.commit()
    return await events.publish_entry(session, entry_id, events.REMOVED)


@queue_router.post("/{entry_id}/finish-sampling", response_model=QueueEntryRead)
async def finish_sampling(
    entry_id: UUID, body: ClaimInput, session: Session
) -> QueueEntryRead:
    """Finaliza la toma: exige todos los tubos de la orden recolectados."""
    entry = await service.get_entry(session, entry_id, lock=True)
    if entry.status != QueueStatus.EN_ATENCION_TOMA_MUESTRAS:
        raise ConflictError(
            f"No se puede finalizar la toma de un paciente en «{entry.status}».",
            {"status": entry.status},
        )
    pending = list(
        (
            await session.execute(
                select(OrderSample.name)
                .join(Order, Order.id == OrderSample.order_id)
                .where(
                    Order.queue_entry_id == entry_id,
                    OrderSample.collected_at.is_(None),
                )
            )
        ).scalars()
    )
    if pending:
        raise ValidationAppError("Faltan muestras por tomar.", {"pending": pending})
    unanswered = await unanswered_checks(session, entry_id, "sampling")
    if unanswered:
        raise UnansweredPreconditionsError(
            "Falta la segunda verificacion de precondiciones.", {"keys": unanswered}
        )
    await service.change_status(
        session, entry_id, QueueStatus.TOMA_FINALIZADA, actor=body.actor
    )
    await session.commit()
    return await events.publish_entry(session, entry_id, events.STATUS_CHANGED)


@queue_router.put("/{entry_id}/draft", response_model=QueueEntryRead)
async def save_draft(
    entry_id: UUID, body: DraftInput, session: Session
) -> QueueEntryRead:
    await service.save_draft(session, entry_id, body.test_codes)
    await session.commit()
    return await events.publish_entry(session, entry_id, events.ENTRY_UPDATED)
