"""Autenticacion de servicio del cliente del catalogo (Leo -> Vladimir)."""

import httpx
import pytest
from leo_sdk import LeoClient, LeoSettings, ServiceTokenProvider

from app.modules.catalog_client.client import (
    CatalogClient,
    CatalogForbiddenError,
    CatalogUnavailableError,
)


def make_provider(leo_handler) -> ServiceTokenProvider:
    settings = LeoSettings(
        _env_file=None,
        leo_url="http://leo",
        leo_api_url="http://leo/api/v1",
        app_client_id="incubus",
        app_client_secret="s3cret",
        public_url="http://incubus",
    )
    http = httpx.AsyncClient(transport=httpx.MockTransport(leo_handler))
    return ServiceTokenProvider(LeoClient(settings, http=http))


def leo_issuing(tokens: list[str], audiences: list[str] | None = None):
    issued = iter(tokens)

    def handler(request: httpx.Request) -> httpx.Response:
        if audiences is not None:
            audiences.append(request.read().decode())
        return httpx.Response(
            200,
            json={
                "access_token": next(issued),
                "token_type": "Bearer",
                "audience": "vladimir",
                "expires_in": 600,
            },
        )

    return handler


def catalog(provider, vladimir_handler) -> CatalogClient:
    return CatalogClient(
        "http://vladimir",
        transport=httpx.MockTransport(vladimir_handler),
        auth=provider.auth("vladimir"),
    )


async def test_envia_bearer_del_token_de_servicio_para_vladimir():
    seen: list[str] = []
    bodies: list[str] = []

    def vladimir(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers.get("authorization", ""))
        return httpx.Response(200, json={"items": []})

    client = catalog(make_provider(leo_issuing(["tok-1"], bodies)), vladimir)
    await client.search_tests(None)
    assert seen == ["Bearer tok-1"]
    assert '"vladimir"' in bodies[0]


async def test_renueva_el_token_una_vez_tras_401():
    seen: list[str] = []

    def vladimir(request: httpx.Request) -> httpx.Response:
        auth = request.headers["authorization"]
        seen.append(auth)
        if auth == "Bearer viejo":
            return httpx.Response(401, json={"detail": "expired"})
        return httpx.Response(200, json={"items": []})

    client = catalog(make_provider(leo_issuing(["viejo", "nuevo"])), vladimir)
    assert await client.search_tests(None) == []
    assert seen == ["Bearer viejo", "Bearer nuevo"]


async def test_leo_caido_es_catalog_unavailable_sin_filtrar_detalles():
    def leo(_r: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"code": "x", "message": "interno secreto"})

    client = catalog(make_provider(leo), lambda r: httpx.Response(200, json={}))
    with pytest.raises(CatalogUnavailableError) as info:
        await client.search_tests(None)
    assert info.value.code == "catalog_unavailable"
    assert info.value.message.startswith("No se pudo autenticar con Leo")
    assert "secreto" not in info.value.message
    assert info.value.details == {"path": "/lab-tests"}


async def test_credenciales_invalidas_es_catalog_unavailable():
    def leo(_r: httpx.Request) -> httpx.Response:
        return httpx.Response(
            401, json={"code": "invalid_client", "message": "Credenciales invalidas"}
        )

    client = catalog(make_provider(leo), lambda r: httpx.Response(200, json={}))
    with pytest.raises(CatalogUnavailableError) as info:
        await client.search_tests(None)
    assert info.value.message.startswith("No se pudo autenticar con Leo")


@pytest.mark.parametrize("status", [401, 403])
async def test_vladimir_sin_acceso_es_catalog_forbidden(status):
    def vladimir(_r: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json={"code": "forbidden"})

    client = catalog(make_provider(leo_issuing(["a", "b"])), vladimir)
    with pytest.raises(CatalogForbiddenError) as info:
        await client.search_tests(None)
    assert info.value.code == "catalog_forbidden"
    assert info.value.status_code == 502
    assert "Pídele a un administrador de Leo" in info.value.message
    assert info.value.details == {"path": "/lab-tests"}


async def test_leo_deniega_la_concesion_es_catalog_forbidden():
    def leo(_r: httpx.Request) -> httpx.Response:
        return httpx.Response(
            403, json={"code": "access_denied", "message": "Sin concesion"}
        )

    client = catalog(make_provider(leo), lambda r: httpx.Response(200, json={}))
    with pytest.raises(CatalogForbiddenError):
        await client.search_tests(None)


async def test_otros_errores_siguen_siendo_catalog_unavailable():
    client = catalog(
        make_provider(leo_issuing(["a"])), lambda r: httpx.Response(500, json={})
    )
    with pytest.raises(CatalogUnavailableError) as info:
        await client.search_tests(None)
    assert info.value.message == "No se pudo consultar el catalogo de Vladimir."
