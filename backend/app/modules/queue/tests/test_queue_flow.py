import pytest
from sqlalchemy import text

PATIENT = {
    "document_number": "1020304050",
    "first_name": "JUAN",
    "first_last_name": "GOMEZ",
    "second_last_name": "RODRIGUEZ",
    "sex": "male",
    "birth_date": "1985-03-12",
}


async def _ids(client):
    pr = {
        priority["code"]: priority["id"]
        for priority in (await client.get("/api/v1/priorities")).json()
    }
    rm = (await client.get("/api/v1/removal-reasons")).json()
    rt = (await client.get("/api/v1/return-reasons")).json()
    return pr, rm[0]["id"], rt[0]["id"]


async def _enter(client, priority="media", **over):
    pr, _, _ = await _ids(client)
    body = {"patient": {**PATIENT, **over}, "priority_id": pr[priority]}
    return await client.post("/api/v1/queue", json=body)


async def test_prioridades_parametrizadas_vienen_ordenadas(client):
    prios = (await client.get("/api/v1/priorities")).json()
    assert [priority["code"] for priority in prios] == [
        "extrema",
        "alta",
        "media",
        "baja",
    ]
    assert all(priority["color_hex"].startswith("#") for priority in prios)


async def test_ingreso_y_orden_por_prioridad_luego_llegada(client):
    first_response = await _enter(client, "baja", document_number="111111")
    second_response = await _enter(client, "extrema", document_number="222222")
    third_response = await _enter(client, "baja", document_number="333333")
    assert first_response.status_code == second_response.status_code == 201
    queue = (await client.get("/api/v1/queue?status=pre_recepcion")).json()
    docs = [queue_entry["patient"]["document_number"] for queue_entry in queue]
    assert docs[:3] == ["222222", "111111", "333333"]
    assert third_response.json()["status"] == "pre_recepcion"


async def test_paciente_no_puede_estar_dos_veces(client):
    assert (await _enter(client)).status_code == 201
    dup = await _enter(client)
    assert dup.status_code == 409


async def test_paciente_con_turno_finalizado_puede_volver_a_la_cola(client, session):
    first = (await _enter(client)).json()
    await session.execute(
        text("UPDATE queue_entries SET status = 'finalizada' WHERE id = :e"),
        {"e": first["id"]},
    )
    again = await _enter(client)
    assert again.status_code == 201
    assert again.json()["id"] != first["id"]
    # con un turno activo, otro ingreso sigue rechazado
    assert (await _enter(client)).status_code == 409


async def test_claim_devolver_y_retirar_con_motivo(client):
    entry = (await _enter(client)).json()
    _, removal, ret = await _ids(client)
    eid = entry["id"]

    claimed = await client.post(f"/api/v1/queue/{eid}/claim", json={"actor": "ana"})
    assert claimed.json()["status"] == "en_atencion_recepcion"
    assert claimed.json()["claimed_by"] == "Tester Uno"  # actor = sesion
    # nadie mas puede tomarlo
    again = await client.post(f"/api/v1/queue/{eid}/claim", json={"actor": "luis"})
    assert again.status_code == 409

    sin_motivo = await client.post(f"/api/v1/queue/{eid}/return", json={})
    assert sin_motivo.status_code == 422
    back = await client.post(f"/api/v1/queue/{eid}/return", json={"reason_id": ret})
    assert back.json()["status"] == "pre_recepcion"

    gone = await client.post(
        f"/api/v1/queue/{eid}/remove", json={"reason_id": removal, "note": "se fue"}
    )
    assert gone.json()["status"] == "retirado"
    # tras el retiro puede volver a ingresar
    assert (await _enter(client)).status_code == 201


async def test_historial_registra_cada_transicion(client):
    eid = (await _enter(client)).json()["id"]
    _, _, ret = await _ids(client)
    await client.post(f"/api/v1/queue/{eid}/claim", json={})
    await client.post(f"/api/v1/queue/{eid}/return", json={"reason_id": ret})
    hist = (await client.get(f"/api/v1/queue/{eid}/history")).json()
    assert [
        (
            history_entry["from_status"],
            history_entry["to_status"],
            history_entry["kind"],
        )
        for history_entry in hist
    ] == [
        (None, "pre_recepcion", "enter"),
        ("pre_recepcion", "en_atencion_recepcion", "advance"),
        ("en_atencion_recepcion", "pre_recepcion", "return"),
    ]
    stamps = [history_entry["changed_at"] for history_entry in hist]
    assert stamps == sorted(stamps)


async def test_historial_es_inmutable(client, session):
    eid = (await _enter(client)).json()["id"]
    await session.commit()
    with pytest.raises(Exception, match="nada se elimina"):
        await session.execute(
            text(
                "UPDATE queue_status_history SET note = 'x' WHERE queue_entry_id = :e"
            ),
            {"e": eid},
        )


async def test_parse_cedula_endpoint(client):
    raw = (
        "PubDSK_1\x00\x000001020304050\x00GOMEZ\x00RODRIGUEZ\x00JUAN\x00M19850312\x00O+"
    )
    res = await client.post("/api/v1/patients/parse-cedula", json={"raw": raw})
    assert res.status_code == 200
    assert res.json()["document_number"] == "1020304050"
    bad = await client.post("/api/v1/patients/parse-cedula", json={"raw": "x"})
    assert bad.status_code == 422
