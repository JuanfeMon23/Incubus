from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.leo import catalog_reader_or_service
from app.core.permissions import DEL_VIEW
from app.modules.catalogs import service
from app.modules.catalogs.owners import OwnerCatalogs, get_owner_catalogs
from app.modules.catalogs.schemas import CatalogItem

Session = Annotated[AsyncSession, Depends(get_session)]
Owners = Annotated[OwnerCatalogs, Depends(get_owner_catalogs)]

# Cualquier persona con algun permiso de Incubus, o un servicio con la entrega de
# resultados (Acuarius lee estados de orden y marcas de resultado).
router = APIRouter(
    tags=["catalogos"], dependencies=[catalog_reader_or_service(DEL_VIEW)]
)
# Ruta anterior (sin /catalogs); se retira cuando el frontend migre.
legacy_router = APIRouter(
    tags=["catalogos"], dependencies=[catalog_reader_or_service(DEL_VIEW)]
)


@router.get(
    "/{slug}",
    response_model=list[CatalogItem],
    response_model_exclude_none=True,
    responses={404: {"description": "Catálogo inexistente"}},
)
async def list_catalog(
    slug: str, session: Session, owners: Owners, include_inactive: bool = False
) -> list[dict]:
    """Catálogo de categoría. Propios: `blood-types`, `queue-statuses`,
    `queue-transition-kinds`, `validation-statuses`, `result-flags`, `trace-steps`
    (`include_inactive` incluye los desactivados). De los dueños, solo activos:
    `sexes` (Vladimir, sin el comodín) y `document-types` (Leo)."""
    return await service.list_catalog(session, owners, slug, include_inactive)


@legacy_router.get(
    "/document-types",
    response_model=list[CatalogItem],
    response_model_exclude_none=True,
    deprecated=True,
)
async def list_document_types(session: Session, owners: Owners) -> list[dict]:
    """Alias de `/catalogs/document-types`."""
    return await service.list_catalog(session, owners, "document-types")
