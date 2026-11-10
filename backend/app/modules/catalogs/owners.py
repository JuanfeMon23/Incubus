"""Catalogos que son de otro servicio, consumidos por API con cache corta.

- Vladimir: sexos, unidades de edad y de duracion, tipos de resultado
  (`GET /api/v1/catalogs/{slug}`, mismas credenciales de servicio que el catalogo).
- Leo: tipos de documento (`GET /api/v1/document-types`, audiencia `leo`).

Cada lista se guarda `ttl_seconds`; si el dueno falla, se sirve la ultima copia
(vencida) y se reintenta pasados `retry_seconds`. Sin copia, 502.
"""

import asyncio
import logging
import time
from collections.abc import Callable
from typing import Any, Protocol

import httpx
from leo_sdk import LeoError, ServiceAccessDenied

from app.core.exceptions import AppError, ValidationAppError
from app.core.leo import settings as leo_settings
from app.modules.catalog_client.client import get_catalog_client, service_auth

logger = logging.getLogger("app.catalogs.owners")

LEO_AUDIENCE = "leo"
DEFAULT_TTL_SECONDS = 300.0
DEFAULT_RETRY_SECONDS = 30.0


class OwnerCatalogUnavailableError(AppError):
    status_code = 502
    code = "owner_catalog_unavailable"


class VladimirSource(Protocol):
    async def catalog(self, slug: str) -> list[dict]: ...


class LeoSource(Protocol):
    async def document_types(self) -> list[dict]: ...


class LeoDocumentTypes:
    """Tipos de documento activos de Leo (Bearer de servicio, audiencia `leo`)."""

    def __init__(
        self,
        base_url: str,
        auth: httpx.Auth | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._auth = auth
        self._transport = transport

    async def document_types(self) -> list[dict]:
        try:
            async with httpx.AsyncClient(
                base_url=self._base_url,
                timeout=10.0,
                transport=self._transport,
                auth=self._auth,
            ) as http:
                response = await http.get("/document-types")
                response.raise_for_status()
                return response.json()
        except (ServiceAccessDenied, LeoError, httpx.HTTPError) as exc:
            raise OwnerCatalogUnavailableError(
                "No se pudo consultar los tipos de documento de Leo.",
                {"owner": "leo", "catalog": "document-types"},
            ) from exc


class OwnerCatalogs:
    def __init__(
        self,
        vladimir: VladimirSource,
        leo: LeoSource,
        ttl_seconds: float = DEFAULT_TTL_SECONDS,
        retry_seconds: float = DEFAULT_RETRY_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._vladimir = vladimir
        self._leo = leo
        self._ttl = ttl_seconds
        self._retry = retry_seconds
        self._clock = clock
        self._cache: dict[str, tuple[float, list[dict]]] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    async def _load(self, key: str, fetch: Callable[[], Any]) -> list[dict]:
        entry = self._cache.get(key)
        if entry is not None and entry[0] > self._clock():
            return entry[1]
        async with self._locks.setdefault(key, asyncio.Lock()):
            entry = self._cache.get(key)  # otro request ya lo refresco
            if entry is not None and entry[0] > self._clock():
                return entry[1]
            try:
                data = await fetch()
            except AppError:
                if entry is None:
                    raise
                logger.warning("Catalogo %s caido: se usa la copia vencida.", key)
                self._cache[key] = (self._clock() + self._retry, entry[1])
                return entry[1]
            self._cache[key] = (self._clock() + self._ttl, data)
            return data

    async def _vladimir_catalog(self, slug: str) -> list[dict]:
        return await self._load(slug, lambda: self._vladimir.catalog(slug))

    async def sexes(self) -> list[dict]:
        """Sexos de Vladimir tal cual (incluye el comodin `is_wildcard`)."""
        return await self._vladimir_catalog("sexes")

    async def selectable_sexes(self) -> list[dict]:
        """Sexos que se pueden asignar a un paciente (sin el comodin)."""
        return [
            sex
            for sex in await self.sexes()
            if not sex.get("is_wildcard") and sex.get("is_active", True)
        ]

    async def document_types(self) -> list[dict]:
        rows = await self._load("document-types", self._leo.document_types)
        return [row for row in rows if row.get("is_active", True)]

    async def age_unit_days(self) -> dict[str, float]:
        """Unidad de edad (`code`) -> dias que dura (para pasar rangos a anos)."""
        return {
            unit["code"]: unit["days"]
            for unit in await self._vladimir_catalog("age-units")
        }

    async def validate_sex(self, code: str | None) -> None:
        if code is None:
            return
        if code not in {sex["code"] for sex in await self.selectable_sexes()}:
            raise ValidationAppError("El sexo no existe o no es válido.", {"sex": code})

    async def validate_document_type(self, code: str) -> None:
        if code not in {row["code"] for row in await self.document_types()}:
            raise ValidationAppError(
                "El tipo de documento no existe o esta inactivo.",
                {"document_type": code},
            )


_owners: OwnerCatalogs | None = None


def get_owner_catalogs() -> OwnerCatalogs:
    """Instancia unica por proceso (la cache vive en ella); inyectable en tests."""
    global _owners
    if _owners is None:
        _owners = OwnerCatalogs(
            get_catalog_client(),
            LeoDocumentTypes(leo_settings.leo_api_url, auth=service_auth(LEO_AUDIENCE)),
        )
    return _owners
