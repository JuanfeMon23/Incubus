"""Catalogos de categoria de Incubus (`blood_types`, `queue_statuses`, ...) y
puente con los de los duenos (sexos de Vladimir, tipos de documento de Leo).

Los `code` de sistema (`QueueStatus`, pasos de traza) viven en el codigo; nombre,
orden y comportamiento de presentacion salen de aqui.
"""

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ValidationAppError
from app.modules.catalogs.owners import OwnerCatalogs
from app.modules.orders.models import ResultFlag, TraceStep, ValidationStatus
from app.modules.queue.models import BloodType, QueueStatusCatalog, QueueTransitionKind


@dataclass(frozen=True)
class OwnCatalog:
    model: type
    label: str  # para mensajes
    extra: tuple[str, ...] = ()  # columnas de comportamiento que se exponen


OWN_CATALOGS: dict[str, OwnCatalog] = {
    "blood-types": OwnCatalog(BloodType, "tipos de sangre"),
    "queue-statuses": OwnCatalog(
        QueueStatusCatalog, "estados de la cola", ("is_terminal",)
    ),
    "queue-transition-kinds": OwnCatalog(
        QueueTransitionKind, "tipos de cambio de estado"
    ),
    "validation-statuses": OwnCatalog(ValidationStatus, "estados de validación"),
    "result-flags": OwnCatalog(
        ResultFlag, "marcas de resultado", ("variant", "show_in_report")
    ),
    "trace-steps": OwnCatalog(TraceStep, "pasos de la trazabilidad", ("category",)),
}
OWNER_CATALOGS = ("sexes", "document-types")
ALL_SLUGS = (*OWN_CATALOGS, *OWNER_CATALOGS)


def own_item(row: Any, catalog: OwnCatalog) -> dict:
    item = {
        "code": row.code,
        "name": row.name,
        "sort_order": row.sort_order,
        "is_active": row.is_active,
    }
    return item | {column: getattr(row, column) for column in catalog.extra}


def _owner_item(row: dict, position: int) -> dict:
    return {
        "code": row["code"],
        "name": row["name"],
        "sort_order": row.get("sort_order", position),
        "is_active": row.get("is_active", True),
    }


async def list_own(
    session: AsyncSession, catalog: OwnCatalog, include_inactive: bool = False
) -> list[dict]:
    model = catalog.model
    stmt = select(model).order_by(model.sort_order, model.code)
    if not include_inactive:
        stmt = stmt.where(model.is_active)
    return [own_item(row, catalog) for row in (await session.execute(stmt)).scalars()]


async def list_catalog(
    session: AsyncSession,
    owners: OwnerCatalogs,
    slug: str,
    include_inactive: bool = False,
) -> list[dict]:
    if slug in OWN_CATALOGS:
        return await list_own(session, OWN_CATALOGS[slug], include_inactive)
    if slug == "sexes":
        rows = await owners.selectable_sexes()
    elif slug == "document-types":
        rows = await owners.document_types()
    else:
        raise NotFoundError("El catálogo no existe.", {"slug": slug})
    return [_owner_item(row, position) for position, row in enumerate(rows, start=1)]


async def ensure_active_code(
    session: AsyncSession, catalog: OwnCatalog, code: str | None, field: str
) -> None:
    """422 si `code` no existe en el catalogo o esta inactivo (`None` se acepta)."""
    if code is None:
        return
    model = catalog.model
    found = (
        await session.execute(
            select(model.id).where(model.code == code, model.is_active)
        )
    ).first()
    if found is None:
        raise ValidationAppError(
            f"El valor «{code}» no existe o está inactivo en {catalog.label}.",
            {field: code},
        )


async def ensure_known_codes(
    session: AsyncSession, catalog: OwnCatalog, codes: list[str], field: str
) -> None:
    """422 si algun `code` no existe en el catalogo (activo o no: sirve para
    filtrar datos historicos)."""
    model = catalog.model
    known = set(
        (
            await session.execute(select(model.code).where(model.code.in_(codes)))
        ).scalars()
    )
    for code in codes:
        if code not in known:
            raise ValidationAppError(
                f"El valor «{code}» no existe en {catalog.label}.", {field: code}
            )


async def report_flag_labels(session: AsyncSession) -> dict[str, str]:
    """Marca (`code`) -> nombre, solo las que el informe imprime."""
    rows = await session.execute(
        select(ResultFlag.code, ResultFlag.name).where(ResultFlag.show_in_report)
    )
    return {code: name for code, name in rows}


async def trace_step_names(session: AsyncSession) -> dict[str, str]:
    """Paso de la trazabilidad (`code`) -> nombre visible."""
    rows = await session.execute(select(TraceStep.code, TraceStep.name))
    return {code: name for code, name in rows}
