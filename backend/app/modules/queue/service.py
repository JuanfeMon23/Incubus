"""Reglas de la cola: ingreso, avance, devolucion y retiro con historial.

Todo cambio de estado pasa por `change_status`: bloquea la fila, valida la
transicion y escribe el historial en la misma transaccion (sin historial no hay
cambio de estado).
"""

from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError, ValidationAppError
from app.core.leo import NO_ACTOR, Actor


class QueueEmptyError(NotFoundError):
    code = "queue_empty"


from app.core.permissions import SUPERVISE_BY_STATUS
from app.modules.orders.models import Order
from app.modules.queue.models import (
    DocumentType,
    Patient,
    Priority,
    QueueEntry,
    QueueStatusHistory,
    RemovalReason,
    ReturnReason,
)
from app.modules.queue.ownership import ensure_turn_owner
from app.modules.queue.schemas import PatientIn
from app.modules.queue.transitions import (
    CLAIM_TARGET,
    RETURN_TARGET,
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
        # `populate_existing`: si la sesion ya tenia la entrada cargada (lectura
        # previa sin bloqueo), se refresca con el estado confirmado por quien
        # solto el bloqueo; si no, se validaria contra datos viejos.
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    entry = (await session.execute(stmt)).scalar_one_or_none()
    if entry is None:
        raise NotFoundError(
            f"No existe la entrada de cola '{entry_id}'.", {"id": str(entry_id)}
        )
    return entry


def _ensure_expected(entry: QueueEntry, expected_status: str | None) -> None:
    """El permiso se evaluo contra la etapa que el router vio; si otra
    transaccion la cambio antes de bloquear la fila, se rechaza (409)."""
    if expected_status is not None and entry.status != expected_status:
        raise ConflictError(
            "El paciente cambio de etapa; vuelve a intentarlo.",
            {"status": entry.status},
        )


async def _write_history(
    session: AsyncSession,
    entry: QueueEntry,
    *,
    from_status: str | None,
    kind: str,
    actor: Actor,
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
            actor=actor.name,
            actor_user_id=actor.user_id,
            priority_id=entry.priority_id,
            removal_reason_id=removal_reason_id,
            return_reason_id=return_reason_id,
            note=note,
        )
    )
    await session.flush()


async def enter_queue(
    session: AsyncSession, patient_in: PatientIn, priority_id: UUID, actor: Actor
) -> QueueEntry:
    await _active_priority(session, priority_id)
    doc_type = (
        await session.execute(
            select(DocumentType).where(
                DocumentType.code == patient_in.document_type, DocumentType.is_active
            )
        )
    ).scalar_one_or_none()
    if doc_type is None:
        raise ValidationAppError(
            "El tipo de documento no existe o esta inactivo.",
            {"document_type": patient_in.document_type},
        )
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
    actor: Actor = NO_ACTOR,
    removal_reason_id: UUID | None = None,
    return_reason_id: UUID | None = None,
    note: str | None = None,
    expected_status: str | None = None,
) -> QueueEntry:
    entry = await get_entry(session, entry_id, lock=True)
    _ensure_expected(entry, expected_status)
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
    # El turno (nombre + id) solo existe mientras se atiende; al salir se limpia.
    owner = (
        actor
        if target
        in (
            QueueStatus.EN_ATENCION_RECEPCION,
            QueueStatus.EN_ATENCION_TOMA_MUESTRAS,
        )
        else NO_ACTOR
    )
    entry.status = target.value
    entry.claimed_by = owner.name
    entry.claimed_by_user_id = owner.user_id
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


_READ_COLUMNS = (QueueEntry, Patient, Priority, Order.order_number)


def _read_query():
    """Entrada + paciente + prioridad + numero de orden en UNA consulta."""
    return (
        select(*_READ_COLUMNS)
        .join(Patient, Patient.id == QueueEntry.patient_id)
        .join(Priority, Priority.id == QueueEntry.priority_id)
        .outerjoin(Order, Order.queue_entry_id == QueueEntry.id)
    )


async def list_entries(
    session: AsyncSession,
    statuses: list[QueueStatus],
    professional_id: str | None = None,
) -> list[tuple[QueueEntry, Patient, Priority, str | None]]:
    stmt = (
        _read_query()
        .where(QueueEntry.status.in_([s.value for s in statuses]))
        .order_by(Priority.rank, QueueEntry.arrived_at)
    )
    if professional_id is not None:
        stmt = stmt.where(QueueEntry.assigned_professional_id == professional_id)
    return [tuple(r) for r in (await session.execute(stmt)).all()]


async def get_entry_full(
    session: AsyncSession, entry_id: UUID
) -> tuple[QueueEntry, Patient, Priority, str | None]:
    """Lectura fresca (ignora lo cacheado en la sesion: `version` al dia)."""
    stmt = (
        _read_query()
        .where(QueueEntry.id == entry_id)
        .execution_options(populate_existing=True)
    )
    row = (await session.execute(stmt)).one_or_none()
    if row is None:
        raise NotFoundError(
            f"No existe la entrada de cola '{entry_id}'.", {"id": str(entry_id)}
        )
    return tuple(row)


async def touch_entry(session: AsyncSession, entry_id: UUID) -> None:
    """UPDATE sin cambios: el trigger sube `version` cuando cambia algo que
    cuelga de la entrada (tubos, verificaciones) y hay que avisar a los clientes."""
    await session.execute(
        update(QueueEntry)
        .where(QueueEntry.id == entry_id)
        .values(status=QueueEntry.status)
        .execution_options(synchronize_session=False)
    )


async def claim(
    session: AsyncSession,
    entry_id: UUID,
    *,
    actor: Actor,
    professional_id: str | None,
    expected_status: str | None = None,
) -> QueueEntry:
    """Toma al paciente validando con la fila bloqueada (sin TOCTOU)."""
    entry = await get_entry(session, entry_id, lock=True)
    _ensure_expected(entry, expected_status)
    target = CLAIM_TARGET.get(QueueStatus(entry.status))
    if target is None:
        raise ConflictError(
            f"No se puede tomar un paciente en «{entry.status}».",
            {"status": entry.status},
        )
    if (
        target is QueueStatus.EN_ATENCION_TOMA_MUESTRAS
        and entry.assigned_professional_id != professional_id
    ):
        raise ConflictError(
            "El paciente esta asignado a otro profesional de toma de muestras.",
            {"assigned_professional_id": entry.assigned_professional_id},
        )
    return await change_status(session, entry_id, target, actor=actor)


async def return_entry(
    session: AsyncSession,
    entry_id: UUID,
    *,
    actor: Actor,
    reason_id: UUID,
    note: str | None,
    expected_status: str | None = None,
    supervisor: bool = False,
) -> QueueEntry:
    entry = await get_entry(session, entry_id, lock=True)
    _ensure_expected(entry, expected_status)
    if entry.status in SUPERVISE_BY_STATUS:
        ensure_turn_owner(
            entry, actor, supervisor=supervisor, action="devolver al paciente"
        )
    back = RETURN_TARGET.get(QueueStatus(entry.status))
    if back is None:
        raise ConflictError(
            f"No se puede devolver un paciente en «{entry.status}».",
            {"status": entry.status},
        )
    return await change_status(
        session,
        entry_id,
        back,
        actor=actor,
        return_reason_id=reason_id,
        note=note,
    )


async def save_draft(
    session: AsyncSession,
    entry_id: UUID,
    test_codes: list[str],
    *,
    actor: Actor,
    supervisor: bool = False,
) -> QueueEntry:
    entry = await get_entry(session, entry_id, lock=True)
    if entry.status != QueueStatus.EN_ATENCION_RECEPCION:
        raise ConflictError(
            "El borrador solo se edita en atencion de recepcion.",
            {"status": entry.status},
        )
    ensure_turn_owner(entry, actor, supervisor=supervisor, action="editar la atención")
    entry.draft = {**entry.draft, "test_codes": list(dict.fromkeys(test_codes))}
    await session.flush()
    return entry


async def ensure_patient_turn_owner(
    session: AsyncSession, patient_id: UUID, actor: Actor, *, supervisor: bool
) -> None:
    """Si el paciente esta en atencion de recepcion, solo quien la tomo (o un
    supervisor) edita sus datos; sin turno en atencion no hay duenio."""
    entry = (
        await session.execute(
            select(QueueEntry)
            .where(
                QueueEntry.patient_id == patient_id,
                QueueEntry.status == QueueStatus.EN_ATENCION_RECEPCION.value,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    if entry is not None:
        ensure_turn_owner(
            entry,
            actor,
            supervisor=supervisor,
            action="editar los datos del paciente",
        )


async def history(
    session: AsyncSession, entry_id: UUID
) -> list[tuple[QueueStatusHistory, str | None, str | None]]:
    """Historial con el NOMBRE de cada motivo (una sola consulta, sin N+1)."""
    await get_entry(session, entry_id)
    stmt = (
        select(QueueStatusHistory, RemovalReason.name, ReturnReason.name)
        .outerjoin(
            RemovalReason, RemovalReason.id == QueueStatusHistory.removal_reason_id
        )
        .outerjoin(ReturnReason, ReturnReason.id == QueueStatusHistory.return_reason_id)
        .where(QueueStatusHistory.queue_entry_id == entry_id)
        .order_by(QueueStatusHistory.changed_at)
    )
    return [tuple(r) for r in (await session.execute(stmt)).all()]


async def previous_status(
    session: AsyncSession, entry_id: UUID, current: str
) -> str | None:
    """Etapa de la que vino la entrada en su ultimo cambio a `current` (historial)."""
    stmt = (
        select(QueueStatusHistory.from_status)
        .where(
            QueueStatusHistory.queue_entry_id == entry_id,
            QueueStatusHistory.to_status == current,
        )
        .order_by(QueueStatusHistory.changed_at.desc())
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


__all__ = [
    "change_status",
    "claim",
    "ensure_patient_turn_owner",
    "enter_queue",
    "get_entry",
    "get_entry_full",
    "history",
    "list_entries",
    "previous_status",
    "return_entry",
    "save_draft",
    "touch_entry",
]


async def claim_next(session: AsyncSession, actor: Actor) -> QueueEntry:
    """Llama al siguiente paciente de pre-recepcion (prioridad y luego llegada).

    `FOR UPDATE SKIP LOCKED`: dos secretarias que llaman a la vez reciben
    pacientes distintos, nunca el mismo.
    """
    stmt = (
        select(QueueEntry)
        .join(Priority, Priority.id == QueueEntry.priority_id)
        .where(QueueEntry.status == QueueStatus.PRE_RECEPCION.value)
        .order_by(Priority.rank, QueueEntry.arrived_at)
        .limit(1)
        .with_for_update(skip_locked=True, of=QueueEntry)
    )
    entry = (await session.execute(stmt)).scalar_one_or_none()
    if entry is None:
        raise QueueEmptyError("No hay pacientes en espera de recepcion.")
    return await change_status(
        session, entry.id, QueueStatus.EN_ATENCION_RECEPCION, actor=actor
    )
