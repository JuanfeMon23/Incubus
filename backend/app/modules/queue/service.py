"""Reglas de la cola: ingreso, avance, devolucion y retiro con historial.

Todo cambio de estado pasa por `change_status`: bloquea la fila, valida la
transicion y escribe el historial en la misma transaccion (sin historial no hay
cambio de estado).
"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError, ValidationAppError
from app.modules.queue.models import (
    Patient,
    Priority,
    QueueEntry,
    QueueStatusHistory,
    RemovalReason,
    ReturnReason,
)
from app.modules.queue.schemas import PatientIn
from app.modules.queue.transitions import (
    InvalidTransitionError,
    QueueStatus,
    TransitionKind,
    resolve_transition,
)


async def _active_priority(session: AsyncSession, priority_id: UUID) -> Priority:
    priority = await session.get(Priority, priority_id)
    if priority is None or not priority.is_active:
        raise ValidationAppError(
            "La prioridad no existe o esta inactiva.",
            {"priority_id": str(priority_id)},
        )
    return priority


async def _active_reason(
    session: AsyncSession, model: type, reason_id: UUID, field: str
):
    reason = await session.get(model, reason_id)
    if reason is None or not reason.is_active:
        raise ValidationAppError(
            "El motivo no existe o esta inactivo.", {field: str(reason_id)}
        )
    return reason


async def get_entry(
    session: AsyncSession, entry_id: UUID, *, lock: bool = False
) -> QueueEntry:
    stmt = select(QueueEntry).where(QueueEntry.id == entry_id)
    if lock:
        stmt = stmt.with_for_update()
    entry = (await session.execute(stmt)).scalar_one_or_none()
    if entry is None:
        raise NotFoundError(
            f"No existe la entrada de cola '{entry_id}'.", {"id": str(entry_id)}
        )
    return entry


async def _write_history(
    session: AsyncSession,
    entry: QueueEntry,
    *,
    from_status: str | None,
    kind: str,
    actor: str | None,
    removal_reason_id: UUID | None = None,
    return_reason_id: UUID | None = None,
    note: str | None = None,
) -> None:
    session.add(
        QueueStatusHistory(
            queue_entry_id=entry.id,
            from_status=from_status,
            to_status=entry.status,
            kind=kind,
            actor=actor,
            priority_id=entry.priority_id,
            removal_reason_id=removal_reason_id,
            return_reason_id=return_reason_id,
            note=note,
        )
    )
    await session.flush()


async def enter_queue(
    session: AsyncSession, patient_in: PatientIn, priority_id: UUID, actor: str | None
) -> QueueEntry:
    await _active_priority(session, priority_id)
    patient = (
        await session.execute(
            select(Patient).where(
                Patient.document_type == patient_in.document_type,
                Patient.document_number == patient_in.document_number,
            )
        )
    ).scalar_one_or_none()
    if patient is None:
        patient = Patient(**patient_in.model_dump())
        session.add(patient)
        await session.flush()
    entry = QueueEntry(patient_id=patient.id, priority_id=priority_id)
    session.add(entry)
    try:
        async with session.begin_nested():
            await session.flush()
    except IntegrityError as exc:
        raise ConflictError(
            "El paciente ya se encuentra en la cola.",
            {"document_number": patient_in.document_number},
        ) from exc
    await _write_history(session, entry, from_status=None, kind="enter", actor=actor)
    return entry


async def change_status(
    session: AsyncSession,
    entry_id: UUID,
    target: QueueStatus,
    *,
    actor: str | None = None,
    removal_reason_id: UUID | None = None,
    return_reason_id: UUID | None = None,
    note: str | None = None,
) -> QueueEntry:
    entry = await get_entry(session, entry_id, lock=True)
    origin = QueueStatus(entry.status)
    try:
        kind = resolve_transition(origin, target)
    except InvalidTransitionError as exc:
        raise ConflictError(
            f"No se puede pasar de «{origin}» a «{target}».",
            {"from": origin.value, "to": target.value},
        ) from exc
    if kind is TransitionKind.REMOVE:
        if removal_reason_id is None:
            raise ValidationAppError("El retiro exige un motivo.", {"reason_id": None})
        await _active_reason(session, RemovalReason, removal_reason_id, "reason_id")
    if kind is TransitionKind.RETURN:
        if return_reason_id is None:
            raise ValidationAppError(
                "La devolucion exige un motivo.", {"reason_id": None}
            )
        await _active_reason(session, ReturnReason, return_reason_id, "reason_id")
    claimed = (
        actor
        if target
        in (
            QueueStatus.EN_ATENCION_RECEPCION,
            QueueStatus.EN_ATENCION_TOMA_MUESTRAS,
        )
        else None
    )
    entry.status = target.value
    entry.claimed_by = claimed
    await session.flush()
    await _write_history(
        session,
        entry,
        from_status=origin.value,
        kind=kind.value,
        actor=actor,
        removal_reason_id=removal_reason_id,
        return_reason_id=return_reason_id,
        note=note,
    )
    return entry


async def list_entries(
    session: AsyncSession, statuses: list[QueueStatus]
) -> list[tuple[QueueEntry, Patient, Priority]]:
    stmt = (
        select(QueueEntry, Patient, Priority)
        .join(Patient, Patient.id == QueueEntry.patient_id)
        .join(Priority, Priority.id == QueueEntry.priority_id)
        .where(QueueEntry.status.in_([s.value for s in statuses]))
        .order_by(Priority.rank, QueueEntry.arrived_at)
    )
    return [tuple(r) for r in (await session.execute(stmt)).all()]


async def get_entry_full(
    session: AsyncSession, entry_id: UUID
) -> tuple[QueueEntry, Patient, Priority]:
    stmt = (
        select(QueueEntry, Patient, Priority)
        .join(Patient, Patient.id == QueueEntry.patient_id)
        .join(Priority, Priority.id == QueueEntry.priority_id)
        .where(QueueEntry.id == entry_id)
    )
    row = (await session.execute(stmt)).one_or_none()
    if row is None:
        raise NotFoundError(
            f"No existe la entrada de cola '{entry_id}'.", {"id": str(entry_id)}
        )
    return tuple(row)


async def save_draft(
    session: AsyncSession, entry_id: UUID, test_codes: list[str]
) -> QueueEntry:
    entry = await get_entry(session, entry_id, lock=True)
    if entry.status != QueueStatus.EN_ATENCION_RECEPCION:
        raise ConflictError(
            "El borrador solo se edita en atencion de recepcion.",
            {"status": entry.status},
        )
    entry.draft = {**entry.draft, "test_codes": list(dict.fromkeys(test_codes))}
    await session.flush()
    return entry


async def history(session: AsyncSession, entry_id: UUID) -> list[QueueStatusHistory]:
    await get_entry(session, entry_id)
    stmt = (
        select(QueueStatusHistory)
        .where(QueueStatusHistory.queue_entry_id == entry_id)
        .order_by(QueueStatusHistory.changed_at)
    )
    return list((await session.execute(stmt)).scalars())


__all__ = [
    "change_status",
    "enter_queue",
    "get_entry",
    "get_entry_full",
    "history",
    "list_entries",
    "save_draft",
]
