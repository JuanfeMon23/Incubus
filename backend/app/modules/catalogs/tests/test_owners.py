"""Catalogos de los duenos (Vladimir: sexos/unidades; Leo: tipos de documento):
cache corta, copia vencida si el dueno cae y validacion de codigos."""

import httpx
import pytest

from app.core.exceptions import ValidationAppError
from app.modules.catalogs.owners import (
    LeoDocumentTypes,
    OwnerCatalogs,
    OwnerCatalogUnavailableError,
)

SEXES = [
    {"code": "male", "name": "Masculino", "is_wildcard": False},
    {"code": "female", "name": "Femenino", "is_wildcard": False},
    {"code": "any", "name": "Cualquiera", "is_wildcard": True},
]
DOCUMENT_TYPES = [
    {"code": "CC", "name": "Cédula", "sort_order": 1, "is_active": True},
    {"code": "OLD", "name": "Viejo", "sort_order": 2, "is_active": False},
]
AGE_UNITS = [
    {"code": "dias", "name": "Días", "days": 1},
    {"code": "meses", "name": "Meses", "days": 30.4375},
    {"code": "anos", "name": "Años", "days": 365.25},
]


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


class FakeVladimir:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.down = False
        self.data = {"sexes": SEXES, "age-units": AGE_UNITS}

    async def catalog(self, slug: str) -> list[dict]:
        self.calls.append(slug)
        if self.down:
            raise OwnerCatalogUnavailableError("Vladimir caido.")
        return self.data[slug]


class FakeLeo:
    def __init__(self) -> None:
        self.calls = 0
        self.down = False

    async def document_types(self) -> list[dict]:
        self.calls += 1
        if self.down:
            raise OwnerCatalogUnavailableError("Leo caido.")
        return DOCUMENT_TYPES


def build() -> tuple[OwnerCatalogs, FakeVladimir, FakeLeo, Clock]:
    vladimir, leo, clock = FakeVladimir(), FakeLeo(), Clock()
    owners = OwnerCatalogs(vladimir, leo, ttl_seconds=60, retry_seconds=10, clock=clock)
    return owners, vladimir, leo, clock


async def test_sex_validation_excludes_the_wildcard() -> None:
    owners, _, _, _ = build()
    await owners.validate_sex("male")
    await owners.validate_sex(None)
    for invalid in ("any", "M", "x"):
        with pytest.raises(ValidationAppError) as raised:
            await owners.validate_sex(invalid)
        assert raised.value.details == {"sex": invalid}


async def test_selectable_sexes_hide_the_wildcard() -> None:
    owners, _, _, _ = build()
    assert [sex["code"] for sex in await owners.selectable_sexes()] == [
        "male",
        "female",
    ]


async def test_document_type_validation_only_accepts_active_ones() -> None:
    owners, _, _, _ = build()
    await owners.validate_document_type("CC")
    for invalid in ("OLD", "XX"):
        with pytest.raises(ValidationAppError) as raised:
            await owners.validate_document_type(invalid)
        assert raised.value.details == {"document_type": invalid}


async def test_age_unit_days_by_code() -> None:
    owners, _, _, _ = build()
    assert await owners.age_unit_days() == {
        "dias": 1,
        "meses": 30.4375,
        "anos": 365.25,
    }


async def test_cache_is_reused_until_it_expires() -> None:
    owners, vladimir, leo, clock = build()
    await owners.validate_sex("male")
    await owners.validate_sex("female")
    await owners.validate_document_type("CC")
    await owners.validate_document_type("CC")
    assert vladimir.calls == ["sexes"] and leo.calls == 1
    clock.now = 61
    await owners.validate_sex("male")
    assert vladimir.calls == ["sexes", "sexes"]


async def test_stale_copy_is_served_when_the_owner_goes_down() -> None:
    owners, vladimir, leo, clock = build()
    await owners.validate_sex("male")
    await owners.validate_document_type("CC")
    vladimir.down = leo.down = True
    clock.now = 100
    await owners.validate_sex("female")
    await owners.validate_document_type("CC")
    # No martilla al dueno caido: reintenta pasado `retry_seconds`.
    await owners.validate_sex("female")
    assert vladimir.calls == ["sexes", "sexes"]
    clock.now = 111
    await owners.validate_sex("female")
    assert vladimir.calls == ["sexes", "sexes", "sexes"]


async def test_owner_down_without_a_copy_is_a_502() -> None:
    owners, vladimir, _, _ = build()
    vladimir.down = True
    with pytest.raises(OwnerCatalogUnavailableError) as raised:
        await owners.validate_sex("male")
    assert raised.value.status_code == 502


async def test_leo_client_reads_document_types_from_the_leo_api() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=DOCUMENT_TYPES)

    source = LeoDocumentTypes(
        "http://leo/api/v1", transport=httpx.MockTransport(handler)
    )
    assert await source.document_types() == DOCUMENT_TYPES
    assert seen[0].url.path == "/api/v1/document-types"


@pytest.mark.parametrize("status_code", [401, 403, 500])
async def test_leo_client_errors_become_unavailable(status_code: int) -> None:
    source = LeoDocumentTypes(
        "http://leo/api/v1",
        transport=httpx.MockTransport(lambda _: httpx.Response(status_code)),
    )
    with pytest.raises(OwnerCatalogUnavailableError):
        await source.document_types()


async def test_vladimir_client_reads_a_catalog_by_slug() -> None:
    from app.modules.catalog_client.client import CatalogClient

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/catalogs/sexes"
        return httpx.Response(200, json=SEXES)

    client = CatalogClient("http://vladimir", transport=httpx.MockTransport(handler))
    assert await client.catalog("sexes") == SEXES
