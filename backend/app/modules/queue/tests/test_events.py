"""Eventos de tiempo real: tipos, payload (con `version`) y entrega en segundo plano."""

import asyncio
import logging

from sqlalchemy import event

from app.core.database import engine
from app.core.realtime import sio
from app.modules.orders.tests.test_sampling import _claim, _printed, _reception_closed
from app.modules.queue import events

PATIENT = {"document_number": "4040", "first_name": "A", "first_last_name": "B"}


async def _enter(client):
    pr = {p["code"]: p["id"] for p in (await client.get("/api/v1/priorities")).json()}
    res = await client.post(
        "/api/v1/queue", json={"patient": PATIENT, "priority_id": pr["media"]}
    )
    assert res.status_code == 201
    return res.json()


async def test_alta_emite_entry_created_con_la_forma_de_siempre_y_version(
    client, published
):
    entry = await _enter(client)
    await events.drain()
    assert len(published) == 1
    msg = published[0]
    assert set(msg) == {"event", "entry"}
    assert msg["event"] == "entry_created"
    assert msg["entry"] == entry
    assert isinstance(msg["entry"]["version"], int)


async def test_guardar_borrador_emite_entry_updated_con_version_mayor(
    client, published
):
    entry = await _enter(client)
    claimed = await client.post(
        f"/api/v1/queue/{entry['id']}/claim", json={"actor": "a"}
    )
    await events.drain()
    published.clear()
    res = await client.put(
        f"/api/v1/queue/{entry['id']}/draft", json={"test_codes": ["GLU"]}
    )
    assert res.status_code == 200
    await events.drain()
    assert [m["event"] for m in published] == ["entry_updated"]
    assert published[0]["entry"]["draft"] == {"test_codes": ["GLU"]}
    assert published[0]["entry"]["version"] == res.json()["version"]
    assert res.json()["version"] > claimed.json()["version"]


async def test_marcar_y_desmarcar_tubo_emiten_sample_updated_y_suben_version(
    client, catalog, published
):
    entry_id, _ = await _printed(client, catalog)
    await _claim(client, entry_id)
    tube = (await client.get(f"/api/v1/orders/by-entry/{entry_id}")).json()["samples"][
        0
    ]
    await events.drain()
    published.clear()
    await client.post(f"/api/v1/orders/samples/{tube['id']}/collect", json={})
    await client.post(f"/api/v1/orders/samples/{tube['id']}/uncollect", json={})
    await events.drain()
    assert [m["event"] for m in published] == ["sample_updated", "sample_updated"]
    assert all(m["sample_id"] == tube["id"] for m in published)
    assert all(m["entry"]["id"] == entry_id for m in published)
    v = [m["entry"]["version"] for m in published]
    assert v[0] < v[1]


async def test_verificaciones_de_precondiciones_emiten_entry_updated(
    client, catalog, published
):
    entry_id, _ = await _reception_closed(client, catalog)
    detail = (await client.get(f"/api/v1/orders/by-entry/{entry_id}")).json()
    key = detail["preconditions"][0]["key"]
    await events.drain()
    published.clear()
    res = await client.post(
        f"/api/v1/orders/by-entry/{entry_id}/precondition-checks",
        json={"stage": "sampling", "checks": [{"key": key, "met": True}]},
    )
    assert res.status_code == 200, res.text
    await events.drain()
    assert [m["event"] for m in published] == ["entry_updated"]


async def test_publicar_no_retrasa_la_respuesta_ni_falla_si_el_envio_falla(
    client, monkeypatch, caplog
):
    gate = asyncio.Event()

    async def slow(*_a, **_k):
        await gate.wait()

    monkeypatch.setattr(sio, "emit", slow)
    priority = (await client.get("/api/v1/priorities")).json()[0]["id"]
    res = await asyncio.wait_for(
        client.post(
            "/api/v1/queue", json={"patient": PATIENT, "priority_id": priority}
        ),
        timeout=2,
    )
    assert res.status_code == 201
    gate.set()
    await events.drain()

    async def boom(*_a, **_k):
        raise RuntimeError("cliente roto")

    monkeypatch.setattr(sio, "emit", boom)
    with caplog.at_level(logging.ERROR):
        res = await client.post(
            f"/api/v1/queue/{res.json()['id']}/claim", json={"actor": "ana"}
        )
        await events.drain()
    assert res.status_code == 200
    assert "cliente roto" in caplog.text


async def test_construir_el_evento_hace_una_sola_consulta(client, session, published):
    entry = await _enter(client)
    await events.drain()
    count = 0

    def spy(*_args):
        nonlocal count
        count += 1

    event.listen(engine.sync_engine, "before_cursor_execute", spy)
    try:
        await events.publish_entry(session, entry["id"], events.ENTRY_UPDATED)
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", spy)
    await events.drain()
    assert count == 1
