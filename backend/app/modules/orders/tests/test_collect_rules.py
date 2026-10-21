from app.modules.orders.tests.test_sampling import _claim, _printed


async def _tubes(client, entry_id):
    return (await client.get(f"/api/v1/orders/by-entry/{entry_id}")).json()["samples"]


async def test_no_se_marca_un_tubo_fuera_de_atencion_de_toma(client, catalog):
    entry_id, _ = await _printed(client, catalog)  # en espera de toma
    tube = (await _tubes(client, entry_id))[0]
    res = await client.post(f"/api/v1/orders/samples/{tube['id']}/collect", json={})
    assert res.status_code == 409
    assert res.json()["details"]["status"] == "en_espera_toma_muestras"
    assert (await _tubes(client, entry_id))[0]["collected_at"] is None


async def test_no_se_desmarca_un_tubo_con_la_toma_finalizada(client, catalog):
    entry_id, _ = await _printed(client, catalog)
    await _claim(client, entry_id)
    for tube in await _tubes(client, entry_id):
        await client.post(f"/api/v1/orders/samples/{tube['id']}/collect", json={})
    keys = [
        p["key"]
        for p in (await client.get(f"/api/v1/orders/by-entry/{entry_id}")).json()[
            "preconditions"
        ]
    ]
    await client.post(
        f"/api/v1/orders/by-entry/{entry_id}/precondition-checks",
        json={
            "stage": "sampling",
            "checks": [{"key": k, "met": True} for k in keys],
        },
    )
    done = await client.post(f"/api/v1/queue/{entry_id}/finish-sampling", json={})
    assert done.status_code == 200
    tube = (await _tubes(client, entry_id))[0]
    res = await client.post(f"/api/v1/orders/samples/{tube['id']}/uncollect", json={})
    assert res.status_code == 409
    assert (await _tubes(client, entry_id))[0]["collected_at"] is not None


async def test_marcar_en_atencion_de_toma_sigue_funcionando(client, catalog):
    entry_id, _ = await _printed(client, catalog)
    await _claim(client, entry_id)
    tube = (await _tubes(client, entry_id))[0]
    res = await client.post(
        f"/api/v1/orders/samples/{tube['id']}/collect", json={"actor": "luis"}
    )
    assert res.status_code == 200
    assert res.json()["collected_by"] == "Tester Uno"  # actor = sesion, no el body
