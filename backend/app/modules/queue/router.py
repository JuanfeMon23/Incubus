from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.exceptions import ConflictError, NotFoundError, ValidationAppError
from app.core.realtime import queue_events
from app.modules.orders.models import Order
from app.modules.patients.cedula import CedulaParseError, parse_cedula_barcode
from app.modules.queue import service
from app.modules.queue.models import Patient, Priority, RemovalReason, ReturnReason
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
ws_router = APIRouter()


# --- Catalogos parametrizados -------------------------------------------------


@catalogs_router.get("/priorities", response_model=list[PriorityRead])
async def list_priorities(session: Session) -> list[Priority]:
    stmt = select(Priority).where(Priority.is_active).order_by(Priority.rank)
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


async def _read(session: AsyncSession, entry_id: UUID) -> QueueEntryRead:
    entry, patient, priority = await service.get_entry_full(session, entry_id)
    order_number = (
        await session.execute(
            select(Order.order_number).where(Order.queue_entry_id == entry_id)
        )
    ).scalar_one_or_none()
    return _to_read(entry, patient, priority, order_number)


def _to_read(entry, patient, priority, order_number=None) -> QueueEntryRead:
    return QueueEntryRead(
        id=entry.id,
        status=entry.status,
        claimed_by=entry.claimed_by,
        arrived_at=entry.arrived_at,
        draft=entry.draft,
        patient=PatientRead.model_validate(patient),
        priority=PriorityRead.model_validate(priority),
        order_number=order_number,
    )


async def _publish(event: str, read: QueueEntryRead) -> None:
    await queue_events.broadcast(
        {"event": event, "entry": read.model_dump(mode="json")}
    )


@queue_router.get("", response_model=list[QueueEntryRead])
async def list_queue(
    session: Session,
    status_filter: Annotated[
        list[QueueStatusLiteral] | None, Query(alias="status")
    ] = None,
) -> list[QueueEntryRead]:
    statuses = (
        [QueueStatus(s) for s in status_filter]
        if status_filter
        else [s for s in QueueStatus if s is not QueueStatus.RETIRADO]
    )
    rows = await service.list_entries(session, statuses)
    numbers = dict(
        (await session.execute(select(Order.queue_entry_id, Order.order_number))).all()
    )
    return [_to_read(e, p, pr, numbers.get(e.id)) for e, p, pr in rows]


@queue_router.post(
    "", response_model=QueueEntryRead, status_code=status.HTTP_201_CREATED
)
async def enter_queue(body: QueueEntryCreate, session: Session) -> QueueEntryRead:
    entry = await service.enter_queue(
        session, body.patient, body.priority_id, body.actor
    )
    await session.commit()
    read = await _read(session, entry.id)
    await _publish("entry_created", read)
    return read


@queue_router.get("/{entry_id}", response_model=QueueEntryRead)
async def get_entry(entry_id: UUID, session: Session) -> QueueEntryRead:
    return await _read(session, entry_id)


@queue_router.get("/{entry_id}/history", response_model=list[HistoryRead])
async def entry_history(entry_id: UUID, session: Session):
    return await service.history(session, entry_id)


_CLAIM_TARGET = {
    QueueStatus.PRE_RECEPCION: QueueStatus.EN_ATENCION_RECEPCION,
    QueueStatus.EN_ESPERA_TOMA_MUESTRAS: QueueStatus.EN_ATENCION_TOMA_MUESTRAS,
}


@queue_router.post("/{entry_id}/claim", response_model=QueueEntryRead)
async def claim(entry_id: UUID, body: ClaimInput, session: Session) -> QueueEntryRead:
    """Toma al paciente: pre-recepcion -> en atencion de recepcion, o espera ->
    en atencion de toma de muestras. Si otro ya lo tomo responde 409."""
    entry = await service.get_entry(session, entry_id)
    target = _CLAIM_TARGET.get(QueueStatus(entry.status))
    if target is None:
        raise ConflictError(
            f"No se puede tomar un paciente en «{entry.status}».",
            {"status": entry.status},
        )
    await service.change_status(session, entry_id, target, actor=body.actor)
    await session.commit()
    read = await _read(session, entry_id)
    await _publish("status_changed", read)
    return read


@queue_router.post("/{entry_id}/return", response_model=QueueEntryRead)
async def return_entry(
    entry_id: UUID, body: ReasonedActionInput, session: Session
) -> QueueEntryRead:
    entry = await service.get_entry(session, entry_id)
    back = {
        QueueStatus.EN_ATENCION_RECEPCION: QueueStatus.PRE_RECEPCION,
        QueueStatus.EN_ATENCION_TOMA_MUESTRAS: QueueStatus.EN_ESPERA_TOMA_MUESTRAS,
    }.get(QueueStatus(entry.status))
    if back is None:
        raise ConflictError(
            f"No se puede devolver un paciente en «{entry.status}».",
            {"status": entry.status},
        )
    await service.change_status(
        session,
        entry_id,
        back,
        actor=body.actor,
        return_reason_id=body.reason_id,
        note=body.note,
    )
    await session.commit()
    read = await _read(session, entry_id)
    await _publish("status_changed", read)
    return read


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
    read = await _read(session, entry_id)
    await _publish("removed", read)
    return read


@queue_router.put("/{entry_id}/draft", response_model=QueueEntryRead)
async def save_draft(
    entry_id: UUID, body: DraftInput, session: Session
) -> QueueEntryRead:
    await service.save_draft(session, entry_id, body.test_codes)
    await session.commit()
    return await _read(session, entry_id)


@ws_router.websocket("/ws/queue")
async def queue_socket(ws: WebSocket) -> None:
    await queue_events.connect(ws)
    try:
        while True:
            await ws.receive_text()  # mantiene viva la conexion
    except WebSocketDisconnect:
        queue_events.disconnect(ws)
