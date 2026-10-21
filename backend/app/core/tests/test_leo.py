"""Integracion con Leo: cookies propias, CORS con DPoP, actor y auditoria."""

import logging

import pytest
from httpx import AsyncClient

from app.conftest import FakeLeo, make_leo_user
from app.core import permissions as p
from app.core.config import get_settings
from app.core.leo import actor_name, auth, record_audit, settings
from app.main import app

API = "/api/v1"


def test_session_cookies_are_incubus_own() -> None:
    """Todos los servicios comparten `localhost`: si usaran `leo_access` se
    pisarian la sesion entre si."""
    assert settings.access_cookie_name == "incubus_access"
    assert settings.refresh_cookie_name == "incubus_refresh"
    assert settings.flow_cookie_name == "incubus_oauth"
    assert (
        settings.cookie_name("incubus_access") == "incubus_access"
    )  # dev: sin __Host-


def test_cookie_names_can_be_overridden_by_env(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.leo import IncubusLeoSettings

    monkeypatch.setenv("ACCESS_COOKIE_NAME", "otra_access")
    assert IncubusLeoSettings().access_cookie_name == "otra_access"


async def test_leo_auth_routes_live_outside_api_v1(client: AsyncClient) -> None:
    paths = set(app.openapi()["paths"])
    assert {"/auth/login", "/auth/callback", "/auth/me", "/auth/logout"} <= paths
    assert not any(path.startswith(f"{API}/auth") for path in paths)


async def test_login_sets_incubus_flow_cookie(client: AsyncClient) -> None:
    from app.testing import DpopKey

    key = DpopKey()
    proof = key.proof("GET", "http://incubus.test/auth/login")
    response = await client.get("/auth/login", headers={"DPoP": proof})
    assert response.status_code == 200
    assert "incubus_oauth=" in response.headers["set-cookie"]
    assert "leo_oauth" not in response.headers["set-cookie"]


async def test_cors_preflight_allows_credentials_and_dpop_header(
    client: AsyncClient,
) -> None:
    origin = get_settings().cors_origins_list[0]
    response = await client.options(
        f"{API}/queue",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type,dpop",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin
    assert response.headers["access-control-allow-credentials"] == "true"
    allowed = response.headers["access-control-allow-headers"].lower()
    assert "dpop" in allowed and "content-type" in allowed


def test_actor_name_is_the_leo_name_or_username() -> None:
    assert actor_name(make_leo_user(set(), name="Ana Gomez")) == "Ana Gomez"
    assert actor_name(make_leo_user(set(), name="")) == "tester"


# --- Auditoria ------------------------------------------------------------------


async def test_record_audit_sends_the_diff_with_the_actor(leo: FakeLeo) -> None:
    await record_audit(
        p.REC_CLOSE,
        leo.user,
        entity_type="queue_entry",
        entity_id="abc",
        before={"status": "a"},
        after={"status": "b"},
    )
    (event,) = leo.events
    assert event["action_tag"] == p.REC_CLOSE
    assert event["entity_type"] == "queue_entry"
    assert event["entity_id"] == "abc"
    assert event["changes"] == {"status": {"before": "a", "after": "b"}}
    assert event["actor"]["jkt"] == "jkt-falso"


async def test_record_audit_never_propagates_leo_failures(
    leo: FakeLeo, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    async def boom(*_a: object, **_k: object) -> bool:
        raise RuntimeError("fallo inesperado")

    monkeypatch.setattr(auth.audit, "record", boom)
    with caplog.at_level(logging.ERROR, logger="app.leo"):
        await record_audit(p.REC_CLOSE, leo.user, entity_type="x", entity_id=1)
    assert "No se pudo registrar" in caplog.text


async def test_leo_down_does_not_break_the_operation(
    client: AsyncClient, leo: FakeLeo
) -> None:
    leo.down = True
    prio = (await client.get(f"{API}/priorities")).json()[0]["id"]
    response = await client.post(
        f"{API}/queue",
        json={
            "patient": {
                "document_number": "4455667",
                "first_name": "A",
                "first_last_name": "B",
            },
            "priority_id": prio,
        },
    )
    assert response.status_code == 201
    assert leo.events == []
    # y un acceso denegado sigue siendo 403 aunque Leo no registre el evento
    leo.grant(p.PRE_VIEW)
    assert (await client.post(f"{API}/queue/call-next")).status_code == 403


async def test_audit_failure_in_an_endpoint_never_breaks_it(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def boom(*_a: object, **_k: object) -> bool:
        raise RuntimeError("fallo inesperado")

    monkeypatch.setattr(auth.audit, "record", boom)
    prio = (await client.get(f"{API}/priorities")).json()[0]["id"]
    response = await client.post(
        f"{API}/queue",
        json={
            "patient": {
                "document_number": "5566778",
                "first_name": "A",
                "first_last_name": "B",
            },
            "priority_id": prio,
        },
    )
    assert response.status_code == 201
