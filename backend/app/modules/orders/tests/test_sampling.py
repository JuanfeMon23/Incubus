PATIENT = {
    "document_number": "5544332211",
    "first_name": "ANA",
    "first_last_name": "LOPEZ",
    "sex": "F",
    "birth_date": "1990-01-01",
}


async def _closed_order(client, catalog):
    catalog.add_sample_type("red", "Tapa roja", "#DC2626", draw_order=2)
    catalog.add_sample_type("lila", "Tapa lila", "#7C3AED", draw_order=1)
    catalog.add_test("COL", "Colesterol", [], sample_types=[("red", True, 3.0)])
    catalog.add_test("TRI", "Trigliceridos", [], sample_types=[("red", True, 5.0)])
    catalog.add_test("HEM", "Hemograma", [], sample_types=[("lila", True, 2.0)])
    pr = {p["code"]: p["id"] for p in (await client.get("/api/v1/priorities")).json()}
    entry = (
        await client.post(
            "/api/v1/queue", json={"patient": PATIENT, "priority_id": pr["media"]}
        )
    ).json()
    await client.post(f"/api/v1/queue/{entry['id']}/claim", json={"actor": "ana"})
    await client.patch(
        f"/api/v1/patients/{entry['patient']['id']}", json={"address": "Calle 1"}
    )
    res = await client.post(
        f"/api/v1/orders/close-reception/{entry['id']}",
        json={"test_codes": ["COL", "TRI", "HEM"], "actor": "ana"},
    )
    assert res.status_code == 200, res.text
    return entry["id"], res.json()["order_number"]


async def test_cierre_de_recepcion_no_crea_tubos(client, catalog):
    entry_id, _ = await _closed_order(client, catalog)
    detail = (await client.get(f"/api/v1/orders/by-entry/{entry_id}")).json()
    assert detail["samples"] == []


async def test_tubos_aparecen_al_tomar_al_paciente_en_toma_de_muestras(client, catalog):
    entry_id, _ = await _closed_order(client, catalog)
    await client.post(f"/api/v1/queue/{entry_id}/claim", json={"actor": "luis"})
    tubes = (await client.get(f"/api/v1/orders/by-entry/{entry_id}")).json()["samples"]
    assert [t["name"] for t in tubes] == ["Tapa lila", "Tapa roja"]
    assert tubes[1]["required_volume_ml"] == 5.0
    assert tubes[1]["test_codes"] == ["COL", "TRI"]
    assert all(t["collected_at"] is None for t in tubes)


async def test_devolver_y_volver_a_tomar_no_duplica_tubos(client, catalog):
    entry_id, _ = await _closed_order(client, catalog)
    await client.post(f"/api/v1/queue/{entry_id}/claim", json={"actor": "luis"})
    ret = (await client.get("/api/v1/return-reasons")).json()[0]["id"]
    await client.post(f"/api/v1/queue/{entry_id}/return", json={"reason_id": ret})
    await client.post(f"/api/v1/queue/{entry_id}/claim", json={"actor": "luis"})
    tubes = (await client.get(f"/api/v1/orders/by-entry/{entry_id}")).json()["samples"]
    assert len(tubes) == 2


async def test_finalizar_exige_todos_los_tubos_tomados(client, catalog):
    entry_id, _ = await _closed_order(client, catalog)
    await client.post(f"/api/v1/queue/{entry_id}/claim", json={"actor": "luis"})
    detail = (await client.get(f"/api/v1/orders/by-entry/{entry_id}")).json()

    early = await client.post(
        f"/api/v1/queue/{entry_id}/finish-sampling", json={"actor": "luis"}
    )
    assert early.status_code == 422
    assert len(early.json()["details"]["pending"]) == 2

    for tube in detail["samples"]:
        res = await client.post(
            f"/api/v1/orders/samples/{tube['id']}/collect", json={"actor": "luis"}
        )
        assert res.status_code == 200
        assert res.json()["collected_by"] == "luis"

    done = await client.post(
        f"/api/v1/queue/{entry_id}/finish-sampling", json={"actor": "luis"}
    )
    assert done.status_code == 200
    assert done.json()["status"] == "toma_finalizada"
    hist = (await client.get(f"/api/v1/queue/{entry_id}/history")).json()
    assert hist[-1]["to_status"] == "toma_finalizada"


async def test_destomar_un_tubo(client, catalog):
    entry_id, _ = await _closed_order(client, catalog)
    await client.post(f"/api/v1/queue/{entry_id}/claim", json={"actor": "luis"})
    tube = (await client.get(f"/api/v1/orders/by-entry/{entry_id}")).json()["samples"][
        0
    ]
    await client.post(f"/api/v1/orders/samples/{tube['id']}/collect", json={})
    back = await client.post(f"/api/v1/orders/samples/{tube['id']}/uncollect", json={})
    assert back.json()["collected_at"] is None


async def test_no_finaliza_si_no_esta_en_atencion_de_toma(client, catalog):
    entry_id, _ = await _closed_order(client, catalog)
    res = await client.post(f"/api/v1/queue/{entry_id}/finish-sampling", json={})
    assert res.status_code == 409
