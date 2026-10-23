from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.leo import record_audit
from app.core.permissions import (
    QAD_CREATE,
    QAD_TOGGLE,
    QAD_UPDATE,
    CanCreateQueueAdmin,
    CanToggleQueueAdmin,
    CanUpdateQueueAdmin,
    CanViewQueueAdmin,
)
from app.modules.queue_admin import service
from app.modules.queue_admin.schemas import (
    CatalogAdminRead,
    CatalogCreate,
    CatalogKind,
    CatalogPage,
    CatalogUpdate,
    ToggleInput,
)

Session = Annotated[AsyncSession, Depends(get_session)]
router = APIRouter(tags=["queue-admin"])


@router.get("/{kind}", response_model=CatalogPage)
async def list_items(
    kind: CatalogKind,
    session: Session,
    _user: CanViewQueueAdmin,
    q: Annotated[str | None, Query(max_length=100)] = None,
    is_active: bool | None = None,
    page: Annotated[int, Query(ge=1, le=10_000)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> dict:
    items, total = await service.list_items(
        session,
        service.kind_of(kind),
        q=q,
        is_active=is_active,
        page=page,
        page_size=page_size,
    )
    return {"items": items, "page": page, "page_size": page_size, "total": total}


@router.get("/{kind}/{item_id}", response_model=CatalogAdminRead)
async def get_item(
    kind: CatalogKind, item_id: UUID, session: Session, _user: CanViewQueueAdmin
):
    return await service.get(session, service.kind_of(kind), item_id)


@router.post("/{kind}", response_model=CatalogAdminRead, status_code=201)
async def create_item(
    kind: CatalogKind, body: CatalogCreate, session: Session, user: CanCreateQueueAdmin
):
    k = service.kind_of(kind)
    row = await service.create(session, k, body)
    await session.commit()
    await record_audit(
        QAD_CREATE,
        user,
        entity_type=k.entity_type,
        entity_id=row.id,
        after=service.snapshot(row),
    )
    return row


@router.patch("/{kind}/{item_id}", response_model=CatalogAdminRead)
async def update_item(
    kind: CatalogKind,
    item_id: UUID,
    body: CatalogUpdate,
    session: Session,
    user: CanUpdateQueueAdmin,
):
    k = service.kind_of(kind)
    row, before = await service.update(session, k, item_id, body)
    await session.commit()
    if before:
        await record_audit(
            QAD_UPDATE,
            user,
            entity_type=k.entity_type,
            entity_id=row.id,
            before=before,
            after={f: getattr(row, f) for f in before},
            reason=(body.reason or "").strip() or None,
        )
    return row


async def _toggle(
    kind: CatalogKind,
    item_id: UUID,
    body: ToggleInput | None,
    session: AsyncSession,
    user,
    active: bool,
):
    k = service.kind_of(kind)
    reason = body.reason if body else None
    row = await service.set_active(session, k, item_id, active, reason)
    await session.commit()
    await record_audit(
        QAD_TOGGLE,
        user,
        entity_type=k.entity_type,
        entity_id=row.id,
        before={"is_active": not active},
        after={"is_active": active},
        reason=(reason or "").strip() or None,
    )
    return row


@router.post("/{kind}/{item_id}/activate", response_model=CatalogAdminRead)
async def activate_item(
    kind: CatalogKind,
    item_id: UUID,
    session: Session,
    user: CanToggleQueueAdmin,
    body: ToggleInput | None = None,
):
    return await _toggle(kind, item_id, body, session, user, True)


@router.post("/{kind}/{item_id}/deactivate", response_model=CatalogAdminRead)
async def deactivate_item(
    kind: CatalogKind,
    item_id: UUID,
    body: ToggleInput,
    session: Session,
    user: CanToggleQueueAdmin,
):
    return await _toggle(kind, item_id, body, session, user, False)
