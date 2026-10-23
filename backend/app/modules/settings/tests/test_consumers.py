"""Los consumidores leen sus umbrales de Ajustes (por peticion / ciclo) y los
valores iniciales salen de las variables heredadas solo al insertar la clave."""

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from leo_sdk.settings_store import SYSTEM_ACTOR
from sqlalchemy import text

from app.core import runtime_settings
from app.core.config import LegacySettingsEnv
from app.main import _sweep_expired_sockets
from app.modules.activation import service
from app.modules.orders import trace_view
from app.modules.orders.tests.test_sampling import _printed
from app.modules.orders.tests.test_trace_endpoint import _test_id, _url
from app.modules.results.tests.helpers import PATIENT, order_in_laboratory

API = "/api/v1"


async def put(key, value):
    grouped = await runtime_settings.store.list()
    version = next(
        v.version for views in grouped.values() for v in views if v.key == key
    )
    await runtime_settings.store.update(key, value, "Prueba", SYSTEM_ACTOR, version)


@pytest.fixture(autouse=True)
def _fresh_limiter():
    service.limiter.reset()
    yield
    service.limiter.reset()


# --- Activacion -----------------------------------------------------------------


async def test_la_vigencia_del_codigo_sale_de_ajustes(client, catalog, session):
    await put("activation.code_ttl_days", 7)
    await order_in_laboratory(client, catalog, ("GLU",))
    expires = (
        await session.execute(text("SELECT expires_at FROM activation_codes"))
    ).scalar_one()
    assert timedelta(days=6) < expires - datetime.now(UTC) <= timedelta(days=7)


async def test_los_limites_de_verificacion_salen_de_ajustes(client):
    await put("activation.verify_max_per_ip_doc", 3)
    body = {
        "code": "AAAAA-AAAAA",
        "document_type": "CC",
        "document_number": PATIENT["document_number"],
        "birth_date": PATIENT["birth_date"],
    }
    url = f"{API}/delivery/activation/verify"
    for _ in range(3):
        assert (await client.post(url, json=body)).status_code == 404
    assert (await client.post(url, json=body)).status_code == 429


# --- Tiempo real -----------------------------------------------------------------


async def test_el_barrido_lee_el_intervalo_en_cada_ciclo(monkeypatch, client):
    waits: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        waits.append(seconds)
        if len(waits) == 1:
            await put("realtime.sweep_seconds", 120)
        elif len(waits) == 2:
            raise asyncio.CancelledError

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)
    with pytest.raises(asyncio.CancelledError):
        await _sweep_expired_sockets()
    assert waits == [30, 120]


# --- Paginacion -------------------------------------------------------------------


async def test_los_topes_de_pagina_salen_de_ajustes(client):
    admin = f"{API}/queue-admin/priorities"
    assert (await client.get(admin, params={"page_size": 100})).status_code == 200
    over = await client.get(admin, params={"page_size": 101})
    assert over.status_code == 422
    assert over.json()["details"] == {"field": "page_size", "max": 100}
    await put("pagination.queue_admin_max_page_size", 150)
    assert (await client.get(admin, params={"page_size": 101})).status_code == 200
    await put("pagination.queue_admin_max_page_size", 20)
    assert (await client.get(admin, params={"page_size": 21})).status_code == 422

    delivery = f"{API}/delivery/patients/CC/0/orders"
    assert (await client.get(delivery, params={"page_size": 51})).status_code == 422
    await put("pagination.results_max_page_size", 200)
    assert (await client.get(delivery, params={"page_size": 51})).status_code == 200
    assert (await client.get(delivery, params={"page_size": 0})).status_code == 422


async def test_el_tope_de_trazabilidad_sale_de_ajustes(client, catalog, session):
    _, number = await order_in_laboratory(client, catalog, ("GLU",))
    tid = await _test_id(session, number, "GLU")
    await put("pagination.orders_max_page_size", 50)
    over = await client.get(_url(number, tid), params={"page_size": 51})
    assert over.status_code == 422
    ok = await client.get(_url(number, tid), params={"page_size": 50})
    assert ok.status_code == 200


# --- Etiquetas --------------------------------------------------------------------


async def test_las_medidas_por_defecto_de_etiqueta_salen_de_ajustes(client, catalog):
    entry_id, _ = await _printed(client, catalog)
    url = f"{API}/orders/by-entry/{entry_id}/labels.zpl"
    assert "^PW560" in (await client.get(url)).text  # 70 mm x 8 dots/mm
    await put("labels.default_width_mm", 50)
    await put("labels.default_dpi", 300)
    assert "^PW600" in (await client.get(url)).text  # 50 mm x 12 dots/mm
    explicit = await client.get(url, params={"width_mm": 70, "dpi": 203})
    assert "^PW560" in explicit.text  # lo explicito gana sobre el ajuste
    assert (await client.get(url, params={"dpi": 100})).status_code == 422


# --- Trazabilidad -----------------------------------------------------------------


def test_la_tolerancia_de_deduplicado_es_un_parametro():
    at = datetime(2026, 1, 1, tzinfo=UTC)
    derived = {"step": "queue.entered", "at": at + timedelta(seconds=5), "details": {}}
    real = {"step": "queue.entered", "at": at, "details": {}}
    assert not trace_view._covered(derived, [real])  # 2 s por defecto
    assert trace_view._covered(derived, [real], timedelta(seconds=6))


async def test_la_tolerancia_se_lee_de_ajustes_al_armar_la_traza(
    client, catalog, session, monkeypatch
):
    _, number = await order_in_laboratory(client, catalog, ("GLU",))
    tid = await _test_id(session, number, "GLU")
    seen: list[timedelta] = []
    original = trace_view._covered

    def spy(derived, reals, tolerance=trace_view.TOLERANCE):
        seen.append(tolerance)
        return original(derived, reals, tolerance)

    monkeypatch.setattr(trace_view, "_covered", spy)
    await put("trace.dedup_tolerance_seconds", 7)
    assert (await client.get(_url(number, tid))).status_code == 200
    assert seen and set(seen) == {timedelta(seconds=7)}


# --- Valores iniciales heredados ------------------------------------------------------


def test_las_variables_heredadas_dan_valores_iniciales_y_se_ignora_lo_invalido(
    monkeypatch,
):
    monkeypatch.setenv("ACTIVATION_CODE_TTL_DAYS", "45")
    monkeypatch.setenv("SOCKETIO_SWEEP_SECONDS", "60.0")
    monkeypatch.setenv("SOCKETIO_MAX_ROOMS", "muchos")
    assert LegacySettingsEnv().initial_values() == {
        "activation.code_ttl_days": 45,
        "realtime.sweep_seconds": 60,
    }


async def test_el_valor_heredado_solo_se_usa_en_el_primer_arranque(session):
    # El fixture `session` ya sembro con defaults: las claves existen.
    result = await runtime_settings.store.sync_registry(
        {"activation.code_ttl_days": 99}
    )
    assert result.inserted == []
    assert await runtime_settings.get("activation.code_ttl_days") == 30
    await session.execute(text("DELETE FROM settings"))
    runtime_settings.store.invalidate()
    result = await runtime_settings.store.sync_registry(
        {"activation.code_ttl_days": 99, "realtime.socket_max_rooms": 1}  # 1: invalido
    )
    assert len(result.inserted) == 13
    assert await runtime_settings.get("activation.code_ttl_days") == 99
    assert await runtime_settings.get("realtime.socket_max_rooms") == 20


async def test_si_la_bd_falla_se_usan_los_defaults(monkeypatch):
    def broken():
        raise RuntimeError("BD caida")

    monkeypatch.setattr(runtime_settings.store, "session_factory", broken)
    runtime_settings.store.invalidate()
    assert await runtime_settings.get("realtime.socket_max_rooms") == 20
