PATIENT = {"first_name": "ANA", "first_last_name": "LOPEZ", "sex": "F"}


async def _enter(client, doc, priority):
    pr = {p["code"]: p["id"] for p in (await client.get("/api/v1/priorities")).json()}
    res = await client.post(
        "/api/v1/queue",
        json={
            "patient": {**PATIENT, "document_number": doc},
            "priority_id": pr[priority],
        },
    )
    assert res.status_code == 201, res.text
    return res.json()["id"]


async def test_llama_al_siguiente_por_prioridad_y_luego_llegada(client):
    baja = await _enter(client, "1001", "baja")
    alta1 = await _enter(client, "1002", "alta")
    await _enter(client, "1003", "alta")

    first = await client.post("/api/v1/queue/call-next", json={"actor": "ana"})
    assert first.status_code == 200
    assert first.json()["id"] == alta1  # mas urgente y mas antiguo
    assert first.json()["status"] == "en_atencion_recepcion"
    assert first.json()["claimed_by"] == "ana"

    second = await client.post("/api/v1/queue/call-next", json={"actor": "ana"})
    assert second.json()["patient"]["document_number"] == "1003"
    third = await client.post("/api/v1/queue/call-next", json={"actor": "ana"})
    assert third.json()["id"] == baja


async def test_sin_pacientes_en_espera_responde_404(client):
    res = await client.post("/api/v1/queue/call-next", json={"actor": "ana"})
    assert res.status_code == 404
    assert res.json()["code"] == "queue_empty"


async def test_el_historial_registra_quien_llamo(client):
    await _enter(client, "2001", "media")
    called = (
        await client.post("/api/v1/queue/call-next", json={"actor": "ana"})
    ).json()
    hist = (await client.get(f"/api/v1/queue/{called['id']}/history")).json()
    assert hist[-1]["kind"] == "advance"
    assert hist[-1]["actor"] == "ana"
