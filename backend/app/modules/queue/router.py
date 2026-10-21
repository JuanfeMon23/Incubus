from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status
from leo_sdk import LeoUser
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.exceptions import ConflictError, NotFoundError, ValidationAppError
from app.core.leo import Actor, CatalogReader, authorize, record_audit
from app.core.permissions import (
    CLAIM_BY_STATUS,
    PRE_ENQUEUE,
    REC_CALL_NEXT,
    REC_EDIT_PATIENT,
    REMOVE_BY_STATUS,
    RETURN_BY_STATUS,
    SAM_FINISH,
    STAGE_VIEW,
    CanCallNext,
    CanClaim,
    CanEditPatient,
    CanEnqueue,
    CanFinishSampling,
    CanHandlePatients,
    CanRemove,
    CanReturn,
    CanViewAnyStage,
)
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
from app.modules.queue.ownership import (
    audit_not_owner,
    can_supervise,
    ensure_turn_owner,
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

# Catalogos compartidos: cualquier persona con algun permiso de Incubus
# (`CatalogReader`). El resto de rutas exige el tag de su pantalla.
catalogs_router = APIRouter(tags=["catalogos"])
patients_router = APIRouter(tags=["patients"])
queue_router = APIRouter(tags=["queue"])


async def _authorize_for_status(
    request: Request,
    user: LeoUser,
    session: AsyncSession,
    entry_id: UUID,
    by_status: dict[str, str],
) -> str:
    """Exige el tag que corresponde a la etapa ACTUAL de la entrada y devuelve
    esa etapa (el servicio la reverifica con la fila bloqueada). Una etapa sin
    tag para la accion la rechaza el servicio con 409."""
    current = (await service.get_entry(session, entry_id)).status
    if (tag := by_status.get(current)) is not None:
        await authorize(request, user, tag)
    return current


# --- Catalogos parametrizados -------------------------------------------------


@catalogs_router.get("/priorities", response_model=list[PriorityRead])
async def list_priorities(session: Session, _user: CatalogReader) -> list[Priority]:
    stmt = select(Priority).where(Priority.is_active).order_by(Priority.rank)
    return list((await session.execute(stmt)).scalars())


@catalogs_router.get("/document-types", response_model=list[CatalogRead])
async def list_document_types(
    session: Session, _user: CatalogReader
) -> list[DocumentType]:
    """Tipos de documento de identidad parametrizados en BD (CC, TI, CE, PA...)."""
    stmt = (
        select(DocumentType).where(DocumentType.is_active).order_by(DocumentType.code)
    )
    return list((await session.execute(stmt)).scalars())


@catalogs_router.get("/removal-reasons", response_model=list[CatalogRead])
async def list_removal_reasons(
    session: Session, _user: CatalogReader
) -> list[RemovalReason]:
    stmt = (
        select(RemovalReason)
        .where(RemovalReason.is_active)
        .order_by(RemovalReason.name)
    )
    return list((await session.execute(stmt)).scalars())


@catalogs_router.get("/return-reasons", response_model=list[CatalogRead])
async def list_return_reasons(
    session: Session, _user: CatalogReader
) -> list[ReturnReason]:
    stmt = (
        select(ReturnReason).where(ReturnReason.is_active).order_by(ReturnReason.name)
    )
    return list((await session.execute(stmt)).scalars())


# --- Pacientes ----------------------------------------------------------------


@patients_router.post("/parse-cedula")
async def parse_cedula(body: dict, _user: CanHandlePatients) -> dict:
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
    _user: CanHandlePatients,
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
    patient_id: UUID,
    body: PatientUpdate,
    request: Request,
    session: Session,
    user: CanEditPatient,
) -> Patient:
    async with audit_not_owner(request, user, REC_EDIT_PATIENT):
        await service.ensure_patient_turn_owner(
            session,
            patient_id,
            Actor.of(user),
            supervisor=can_supervise(user, QueueStatus.EN_ATENCION_RECEPCION.value),
        )
    patient = await session.get(Patient, patient_id)
    if patient is None:
        raise NotFoundError(
            f"No existe el paciente '{patient_id}'.", {"id": str(patient_id)}
        )
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(patient, field, value)
    await session.commit()
    # Solo los NOMBRES de los campos editados (los valores son datos personales).
    await record_audit(
        REC_EDIT_PATIENT,
        user,
        entity_type="patient",
        entity_id=patient_id,
        after={"changed_fields": sorted(body.model_dump(exclude_unset=True))},
    )
    return patient


# --- Cola ---------------------------------------------------------------------


@queue_router.get("", response_model=list[QueueEntryRead])
async def list_queue(
    request: Request,
    session: Session,
    user: CanViewAnyStage,
    status_filter: Annotated[
        list[QueueStatusLiteral] | None, Query(alias="status")
    ] = None,
    professional_id: Annotated[str | None, Query(max_length=64)] = None,
) -> list[QueueEntryRead]:
    """Entradas de las etapas pedidas. Cada etapa exige el `view` de su pantalla;
    sin filtro se devuelven solo las etapas que la persona puede ver."""
    if status_filter:
        statuses = [QueueStatus(s) for s in status_filter]
        for stage in statuses:
            await authorize(request, user, STAGE_VIEW[stage.value])
    else:
        statuses = [
            s
            for s in QueueStatus
            if s is not QueueStatus.RETIRADO and user.can(STAGE_VIEW[s.value])
        ]
    rows = await service.list_entries(session, statuses, professional_id)
    return [events.to_read(*row) for row in rows]


@queue_router.post(
    "", response_model=QueueEntryRead, status_code=status.HTTP_201_CREATED
)
async def enter_queue(
    body: QueueEntryCreate, session: Session, user: CanEnqueue
) -> QueueEntryRead:
    entry = await service.enter_queue(
        session, body.patient, body.priority_id, Actor.of(user)
    )
    await session.commit()
    return await events.publish_entry(
        session,
        entry.id,
        events.ENTRY_CREATED,
        audit=events.AuditInfo(
            user, PRE_ENQUEUE, after={"priority_id": str(body.priority_id)}
        ),
    )


@queue_router.post("/call-next", response_model=QueueEntryRead)
async def call_next(session: Session, user: CanCallNext) -> QueueEntryRead:
    """Recepcion llama al siguiente paciente (no se elige uno en concreto).

    El cuerpo ya no se usa (el actor sale de la sesion): se ignora por
    compatibilidad con clientes que aun lo envian."""
    entry = await service.claim_next(session, Actor.of(user))
    await session.commit()
    return await events.publish_entry(
        session,
        entry.id,
        events.STATUS_CHANGED,
        audit=events.AuditInfo(user, REC_CALL_NEXT),
    )


@queue_router.get("/{entry_id}", response_model=QueueEntryRead)
async def get_entry(
    entry_id: UUID, session: Session, _user: CanViewAnyStage
) -> QueueEntryRead:
    return await events.read_entry(session, entry_id)


@queue_router.get("/{entry_id}/history", response_model=list[HistoryRead])
async def entry_history(
    entry_id: UUID, session: Session, _user: CanViewAnyStage
) -> list[HistoryRead]:
    return [
        HistoryRead.model_validate(row).model_copy(
            update={"removal_reason_name": removal, "return_reason_name": returned}
        )
        for row, removal, returned in await service.history(session, entry_id)
    ]


@queue_router.post("/{entry_id}/claim", response_model=QueueEntryRead)
async def claim(
    entry_id: UUID,
    request: Request,
    session: Session,
    user: CanClaim,
    body: ClaimInput | None = None,
) -> QueueEntryRead:
    """Toma al paciente: pre-recepcion -> en atencion de recepcion (exige
    `reception.call-next`), o espera de toma -> en atencion de toma de muestras
    (exige `sampling.claim` y ser el profesional asignado). El actor es la
    persona autenticada; `body.actor` se ignora."""
    expected = await _authorize_for_status(
        request, user, session, entry_id, CLAIM_BY_STATUS
    )
    await service.claim(
        session,
        entry_id,
        actor=Actor.of(user),
        professional_id=body.professional_id if body else None,
        expected_status=expected,
    )
    await session.commit()
    return await events.publish_entry(
        session,
        entry_id,
        events.STATUS_CHANGED,
        audit=events.AuditInfo(user, CLAIM_BY_STATUS[expected]),
    )


@queue_router.post("/{entry_id}/return", response_model=QueueEntryRead)
async def return_entry(
    entry_id: UUID,
    body: ReasonedActionInput,
    request: Request,
    session: Session,
    user: CanReturn,
) -> QueueEntryRead:
    expected = await _authorize_for_status(
        request, user, session, entry_id, RETURN_BY_STATUS
    )
    async with audit_not_owner(request, user, RETURN_BY_STATUS.get(expected, "")):
        await service.return_entry(
            session,
            entry_id,
            actor=Actor.of(user),
            reason_id=body.reason_id,
            note=body.note,
            expected_status=expected,
            supervisor=can_supervise(user, expected),
        )
    await session.commit()
    return await events.publish_entry(
        session,
        entry_id,
        events.STATUS_CHANGED,
        audit=events.AuditInfo(
            user,
            RETURN_BY_STATUS[expected],
            after={"return_reason_id": str(body.reason_id)},
        ),
    )


@queue_router.post("/{entry_id}/remove", response_model=QueueEntryRead)
async def remove_entry(
    entry_id: UUID,
    body: ReasonedActionInput,
    request: Request,
    session: Session,
    user: CanRemove,
) -> QueueEntryRead:
    expected = await _authorize_for_status(
        request, user, session, entry_id, REMOVE_BY_STATUS
    )
    await service.change_status(
        session,
        entry_id,
        QueueStatus.RETIRADO,
        actor=Actor.of(user),
        removal_reason_id=body.reason_id,
        note=body.note,
        expected_status=expected,
    )
    await session.commit()
    return await events.publish_entry(
        session,
        entry_id,
        events.REMOVED,
        audit=events.AuditInfo(
            user,
            REMOVE_BY_STATUS[expected],
            after={"removal_reason_id": str(body.reason_id)},
        ),
    )


@queue_router.post("/{entry_id}/finish-sampling", response_model=QueueEntryRead)
async def finish_sampling(
    entry_id: UUID, request: Request, session: Session, user: CanFinishSampling
) -> QueueEntryRead:
    """Finaliza la toma: exige todos los tubos de la orden recolectados."""
    entry = await service.get_entry(session, entry_id, lock=True)
    if entry.status != QueueStatus.EN_ATENCION_TOMA_MUESTRAS:
        raise ConflictError(
            f"No se puede finalizar la toma de un paciente en «{entry.status}».",
            {"status": entry.status},
        )
    async with audit_not_owner(request, user, SAM_FINISH):
        ensure_turn_owner(
            entry,
            Actor.of(user),
            supervisor=can_supervise(user, entry.status),
            action="finalizar la toma",
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
        session, entry_id, QueueStatus.TOMA_FINALIZADA, actor=Actor.of(user)
    )
    await session.commit()
    return await events.publish_entry(
        session,
        entry_id,
        events.STATUS_CHANGED,
        audit=events.AuditInfo(user, SAM_FINISH),
    )


@queue_router.put("/{entry_id}/draft", response_model=QueueEntryRead)
async def save_draft(
    entry_id: UUID,
    body: DraftInput,
    request: Request,
    session: Session,
    user: CanEditPatient,
) -> QueueEntryRead:
    async with audit_not_owner(request, user, REC_EDIT_PATIENT):
        await service.save_draft(
            session,
            entry_id,
            body.test_codes,
            actor=Actor.of(user),
            supervisor=can_supervise(user, QueueStatus.EN_ATENCION_RECEPCION.value),
        )
    await session.commit()
    return await events.publish_entry(
        session,
        entry_id,
        events.ENTRY_UPDATED,
        audit=events.AuditInfo(
            user, REC_EDIT_PATIENT, after={"draft_test_codes": body.test_codes}
        ),
    )
