"""Administracion de los catalogos de la cola (prioridades y motivos).

Nada se borra: las filas las referencian turnos e historial. Desactivar las
saca de los selectores (`/priorities`, `/removal-reasons`, `/return-reasons`),
pero los turnos existentes siguen mostrandolas.
"""

import re
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError, ValidationAppError
from app.modules.queue.models import Priority, RemovalReason, ReturnReason
from app.modules.queue_admin.schemas import CatalogCreate, CatalogKind, CatalogUpdate

# Prioridad que la pantalla de ingreso preselecciona: no se puede desactivar.
DEFAULT_PRIORITY_CODE = "media"
CODE_RE = re.compile(r"^[a-z0-9]+(?:[-_][a-z0-9]+)*$")
COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")


@dataclass(frozen=True)
class Kind:
    model: type
    entity_type: str
    label: str  # para mensajes
    has_style: bool = False


KINDS: dict[str, Kind] = {
    "priorities": Kind(Priority, "priority", "prioridades", has_style=True),
    "removal-reasons": Kind(RemovalReason, "removal_reason", "motivos de retiro"),
    "return-reasons": Kind(ReturnReason, "return_reason", "motivos de devolución"),
}


def kind_of(slug: CatalogKind) -> Kind:
    return KINDS[slug]


def snapshot(row: Any) -> dict[str, Any]:
    data = {"code": row.code, "name": row.name, "is_active": row.is_active}
    if hasattr(row, "rank"):
        data |= {"color_hex": row.color_hex, "rank": row.rank}
    return data


# --- Validaciones --------------------------------------------------------------


def _clean_name(value: str | None) -> str:
    name = " ".join((value or "").split())
    if not name:
        raise ValidationAppError("El nombre es obligatorio.", {"field": "name"})
    return name


def _clean_code(value: str) -> str:
    code = value.strip()
    if not CODE_RE.fullmatch(code):
        raise ValidationAppError(
            "El código solo admite minúsculas, números y guiones "
            "(por ejemplo «sin-convenio»).",
            {"field": "code"},
        )
    return code


def _clean_color(value: str | None) -> str:
    if value is None or not COLOR_RE.fullmatch(value.strip()):
        raise ValidationAppError(
            "El color debe tener el formato #RRGGBB (por ejemplo #DC2626).",
            {"field": "color_hex"},
        )
    return value.strip().upper()


def _clean_rank(value: int | None) -> int:
    if value is None or value < 1:
        raise ValidationAppError(
            "El orden debe ser un número entero mayor o igual a 1.", {"field": "rank"}
        )
    return value


def _reject_style(kind: Kind, fields: set[str]) -> None:
    if not kind.has_style and fields & {"color_hex", "rank"}:
        raise ValidationAppError(
            f"Este catálogo ({kind.label}) no tiene color ni orden.",
            {"fields": ["color_hex", "rank"]},
        )


async def _lock(session: AsyncSession, kind: Kind) -> None:
    """Serializa las escrituras de un catalogo (unicidad de nombre y orden)."""
    await session.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:key))"),
        {"key": f"queue_admin:{kind.entity_type}"},
    )


_CONFLICTS = {
    "code": "Ya existe un elemento con ese código.",
    "name": "Ya existe un elemento con ese nombre.",
    "rank": "Ya hay otra prioridad con ese orden.",
}


async def _ensure_unique(
    session: AsyncSession, kind: Kind, field: str, value: Any, exclude: UUID | None
) -> None:
    column = getattr(kind.model, field)
    same = (
        func.lower(column) == value.lower()
        if isinstance(value, str)
        else column == value
    )
    stmt = select(kind.model.id).where(same)
    if exclude is not None:
        stmt = stmt.where(kind.model.id != exclude)
    if (await session.execute(stmt.limit(1))).first() is not None:
        raise ConflictError(_CONFLICTS[field], {"field": field, "value": value})


async def get(session: AsyncSession, kind: Kind, item_id: UUID, lock: bool = False):
    stmt = select(kind.model).where(kind.model.id == item_id)
    if lock:
        stmt = stmt.with_for_update()
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise NotFoundError("El elemento no existe.", {"id": str(item_id)})
    return row


# --- Casos de uso ------------------------------------------------------------------


async def list_items(
    session: AsyncSession,
    kind: Kind,
    *,
    q: str | None,
    is_active: bool | None,
    page: int,
    page_size: int,
) -> tuple[list[Any], int]:
    model = kind.model
    conds = []
    if q and q.strip():
        term = q.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        like = f"%{term}%"
        conds.append(
            or_(
                model.code.ilike(like, escape="\\"), model.name.ilike(like, escape="\\")
            )
        )
    if is_active is not None:
        conds.append(model.is_active == is_active)
    total = (
        await session.execute(select(func.count()).select_from(model).where(*conds))
    ).scalar_one()
    order = (model.rank, model.code) if kind.has_style else (model.name, model.code)
    rows = (
        await session.execute(
            select(model)
            .where(*conds)
            .order_by(*order)
            .limit(page_size)
            .offset((page - 1) * page_size)
        )
    ).scalars()
    return list(rows), total


async def create(session: AsyncSession, kind: Kind, body: CatalogCreate):
    _reject_style(
        kind, {f for f in ("color_hex", "rank") if getattr(body, f) is not None}
    )
    values: dict[str, Any] = {
        "code": _clean_code(body.code),
        "name": _clean_name(body.name),
    }
    if kind.has_style:
        values["color_hex"] = _clean_color(body.color_hex)
        values["rank"] = _clean_rank(body.rank)
    await _lock(session, kind)
    for field, value in values.items():
        if field != "color_hex":
            await _ensure_unique(session, kind, field, value, None)
    row = kind.model(**values)
    session.add(row)
    await session.flush()
    await session.refresh(row)
    return row


async def update(session: AsyncSession, kind: Kind, item_id: UUID, body: CatalogUpdate):
    """Devuelve (fila, antes); `antes` solo trae los campos que cambian."""
    sent = body.model_dump(exclude_unset=True, exclude={"reason"})
    _reject_style(kind, set(sent))
    if not sent:
        raise ValidationAppError("No hay cambios que guardar.", None)
    cleaners = {"name": _clean_name, "color_hex": _clean_color, "rank": _clean_rank}
    cleaned = {field: cleaners[field](value) for field, value in sent.items()}
    await _lock(session, kind)
    row = await get(session, kind, item_id, lock=True)
    changes = {f: v for f, v in cleaned.items() if getattr(row, f) != v}
    before = {f: getattr(row, f) for f in changes}
    for field in ("name", "rank"):
        if field in changes:
            await _ensure_unique(session, kind, field, changes[field], item_id)
    for field, value in changes.items():
        setattr(row, field, value)
    await session.flush()
    await session.refresh(row)
    return row, before


async def set_active(
    session: AsyncSession, kind: Kind, item_id: UUID, active: bool, reason: str | None
):
    reason = (reason or "").strip() or None
    if not active and reason is None:
        raise ValidationAppError(
            "Indica el motivo para desactivar.", {"field": "reason"}
        )
    await _lock(session, kind)
    row = await get(session, kind, item_id, lock=True)
    if row.is_active == active:
        state = "activo" if active else "inactivo"
        raise ConflictError(f"El elemento ya está {state}.", {"is_active": active})
    if not active and kind.has_style:
        if row.code == DEFAULT_PRIORITY_CODE:
            raise ConflictError(
                "No se puede desactivar la prioridad por defecto del ingreso.",
                {"code": row.code},
            )
        others = (
            await session.execute(
                select(func.count())
                .select_from(Priority)
                .where(Priority.is_active, Priority.id != item_id)
            )
        ).scalar_one()
        if others == 0:
            raise ConflictError(
                "Debe quedar al menos una prioridad activa.", {"code": row.code}
            )
    row.is_active = active
    await session.flush()
    await session.refresh(row)
    return row
