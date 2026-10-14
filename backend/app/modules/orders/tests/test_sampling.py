PATIENT = {
    "document_number": "5544332211",
    "first_name": "ANA",
    "first_last_name": "LOPEZ",
    "sex": "F",
    "birth_date": "1990-01-01",
}
PRO = {"professional_id": "staff-1", "professional_name": "Luis Perez"}


async def _reception_closed(client, catalog):
    catalog.add_sample_type("red", "Tapa roja", "#DC2626", draw_order=2)
    catalog.add_sample_type("lila", "Tapa lila", "#7C3AED", draw_order=1)
    catalog.add_area("area-qc", "QC")
    catalog.add_area("area-hem", "HEM")
    catalog.add_test(
        "COL",
        "Colesterol",
        [{"category": "ayuno", "value": 8, "unit": "horas", "text": "Ayuno 8h"}],
        sample_types=[("red", True, 3.0)],
        area_id="area-qc",
    )
    catalog.add_test(
        "TRI", "Trigliceridos", [], sample_types=[("red", True, 5.0)], area_id="area-qc"
    )
    catalog.add_test(
        "HEM", "Hemograma", [], sample_types=[("lila", True, 2.0)], area_id="area-hem"
    )
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
    preview = (
        await client.post(
            "/api/v1/orders/preview", json={"test_codes": ["COL", "TRI", "HEM"]}
        )
    ).json()
    body = {
        "test_codes": ["COL", "TRI", "HEM"],
        "actor": "ana",
        "precondition_checks": [
            {"key": p["key"], "met": True, "note": None}
            for p in preview["preconditions"]
        ],
    }
    res = await client.post(f"/api/v1/orders/close-reception/{entry['id']}", json=body)
    assert res.status_code == 200, res.text
    return entry["id"], res.json()["order_number"]


async def _printed(client, catalog):
    entry_id, number = await _reception_closed(client, catalog)
    res = await client.post(
        f"/api/v1/orders/by-entry/{entry_id}/print-labels", json={**PRO, "actor": "imp"}
    )
    assert res.status_code == 200, res.text
    return entry_id, number


async def _claim(client, entry_id):
    res = await client.post(
        f"/api/v1/queue/{entry_id}/claim",
        json={"actor": "Luis Perez", "professional_id": "staff-1"},
    )
    assert res.status_code == 200, res.text


async def test_cierre_deja_la_orden_en_espera_de_impresion_sin_tubos(client, catalog):
    entry_id, _ = await _reception_closed(client, catalog)
    entry = (await client.get(f"/api/v1/queue/{entry_id}")).json()
    assert entry["status"] == "en_espera_impresion"
    detail = (await client.get(f"/api/v1/orders/by-entry/{entry_id}")).json()
    assert detail["samples"] == []
    assert detail["preconditions"][0]["reception_met"] is True


async def test_cierre_exige_responder_cada_precondicion(client, catalog):
    pr = {p["code"]: p["id"] for p in (await client.get("/api/v1/priorities")).json()}
    catalog.add_test(
        "COL",
        "Colesterol",
        [{"category": "ayuno", "value": 8, "unit": "horas", "text": "Ayuno 8h"}],
    )
    entry = (
        await client.post(
            "/api/v1/queue", json={"patient": PATIENT, "priority_id": pr["media"]}
        )
    ).json()
    await client.post(f"/api/v1/queue/{entry['id']}/claim", json={"actor": "ana"})
    await client.patch(
        f"/api/v1/patients/{entry['patient']['id']}", json={"address": "Calle 1"}
    )
    url = f"/api/v1/orders/close-reception/{entry['id']}"
    sin = await client.post(url, json={"test_codes": ["COL"]})
    assert sin.status_code == 422
    assert sin.json()["code"] == "unanswered_preconditions"
    key = sin.json()["details"]["keys"][0]
    sin_nota = await client.post(
        url,
        json={
            "test_codes": ["COL"],
            "precondition_checks": [{"key": key, "met": False}],
        },
    )
    assert sin_nota.status_code == 422
    assert sin_nota.json()["code"] == "note_required"
    con_nota = await client.post(
        url,
        json={
            "test_codes": ["COL"],
            "precondition_checks": [{"key": key, "met": False, "note": "comio"}],
        },
    )
    assert con_nota.status_code == 200
    detail = (await client.get(f"/api/v1/orders/by-entry/{entry['id']}")).json()
    assert detail["preconditions"][0]["reception_met"] is False
    assert detail["preconditions"][0]["reception_note"] == "comio"


async def test_imprimir_crea_tubos_asigna_profesional_y_pasa_a_espera_de_toma(
    client, catalog
):
    entry_id, _ = await _printed(client, catalog)
    entry = (await client.get(f"/api/v1/queue/{entry_id}")).json()
    assert entry["status"] == "en_espera_toma_muestras"
    assert entry["assigned_professional_name"] == "Luis Perez"
    tubes = (await client.get(f"/api/v1/orders/by-entry/{entry_id}")).json()["samples"]
    assert [t["name"] for t in tubes] == ["Tapa lila", "Tapa roja"]
    assert tubes[1]["required_volume_ml"] == 5.0
    assert tubes[0]["area_route"] == ["HEM"]
    assert tubes[1]["area_route"] == ["QC"]
    assert all(t["labels_printed_at"] for t in tubes)


async def test_imprimir_exige_profesional(client, catalog):
    entry_id, _ = await _reception_closed(client, catalog)
    res = await client.post(
        f"/api/v1/orders/by-entry/{entry_id}/print-labels", json={"actor": "imp"}
    )
    assert res.status_code == 422


async def test_pdf_de_etiquetas_tiene_una_pagina_por_tubo(client, catalog):
    entry_id, _ = await _printed(client, catalog)
    res = await client.get(f"/api/v1/orders/by-entry/{entry_id}/labels.pdf")
    assert res.status_code == 200
    assert res.headers["content-type"] == "application/pdf"
    assert res.content.startswith(b"%PDF")
    assert res.content.count(b"/Type /Page\n") >= 2


async def test_solo_el_profesional_asignado_toma_al_paciente(client, catalog):
    entry_id, _ = await _printed(client, catalog)
    otro = await client.post(
        f"/api/v1/queue/{entry_id}/claim",
        json={"actor": "otro", "professional_id": "staff-2"},
    )
    assert otro.status_code == 409
    sin = await client.post(f"/api/v1/queue/{entry_id}/claim", json={"actor": "x"})
    assert sin.status_code == 409
    ok = await client.post(
        f"/api/v1/queue/{entry_id}/claim",
        json={"actor": "Luis Perez", "professional_id": "staff-1"},
    )
    assert ok.status_code == 200
    assert ok.json()["status"] == "en_atencion_toma_muestras"


async def test_cola_del_profesional_filtra_por_asignacion(client, catalog):
    entry_id, _ = await _printed(client, catalog)
    url = "/api/v1/queue?status=en_espera_toma_muestras&professional_id="
    mine = (await client.get(url + "staff-1")).json()
    other = (await client.get(url + "staff-2")).json()
    assert [e["id"] for e in mine] == [entry_id]
    assert other == []


async def test_finalizar_exige_tubos_y_segunda_verificacion(client, catalog):
    entry_id, _ = await _printed(client, catalog)
    await _claim(client, entry_id)
    detail = (await client.get(f"/api/v1/orders/by-entry/{entry_id}")).json()

    early = await client.post(
        f"/api/v1/queue/{entry_id}/finish-sampling", json={"actor": "luis"}
    )
    assert early.status_code == 422

    for tube in detail["samples"]:
        res = await client.post(
            f"/api/v1/orders/samples/{tube['id']}/collect", json={"actor": "luis"}
        )
        assert res.status_code == 200

    sin_check = await client.post(
        f"/api/v1/queue/{entry_id}/finish-sampling", json={"actor": "luis"}
    )
    assert sin_check.status_code == 422
    assert sin_check.json()["code"] == "unanswered_preconditions"

    keys = [p["key"] for p in detail["preconditions"]]
    checks = await client.post(
        f"/api/v1/orders/by-entry/{entry_id}/precondition-checks",
        json={
            "stage": "sampling",
            "actor": "luis",
            "checks": [
                {"key": k, "met": False, "note": "refiere desayuno"} for k in keys
            ],
        },
    )
    assert checks.status_code == 200
    after = (await client.get(f"/api/v1/orders/by-entry/{entry_id}")).json()
    assert after["preconditions"][0]["sampling_met"] is False
    assert after["preconditions"][0]["reception_met"] is True

    done = await client.post(
        f"/api/v1/queue/{entry_id}/finish-sampling", json={"actor": "luis"}
    )
    assert done.status_code == 200
    assert done.json()["status"] == "toma_finalizada"
    hist = (await client.get(f"/api/v1/queue/{entry_id}/history")).json()
    assert [h["to_status"] for h in hist][-4:] == [
        "en_espera_impresion",
        "en_espera_toma_muestras",
        "en_atencion_toma_muestras",
        "toma_finalizada",
    ]


async def test_devolver_y_volver_a_tomar_no_duplica_tubos(client, catalog):
    entry_id, _ = await _printed(client, catalog)
    await _claim(client, entry_id)
    ret = (await client.get("/api/v1/return-reasons")).json()[0]["id"]
    await client.post(f"/api/v1/queue/{entry_id}/return", json={"reason_id": ret})
    await _claim(client, entry_id)
    tubes = (await client.get(f"/api/v1/orders/by-entry/{entry_id}")).json()["samples"]
    assert len(tubes) == 2


async def test_destomar_un_tubo(client, catalog):
    entry_id, _ = await _printed(client, catalog)
    await _claim(client, entry_id)
    samples = (await client.get(f"/api/v1/orders/by-entry/{entry_id}")).json()[
        "samples"
    ]
    tube = samples[0]
    await client.post(f"/api/v1/orders/samples/{tube['id']}/collect", json={})
    back = await client.post(f"/api/v1/orders/samples/{tube['id']}/uncollect", json={})
    assert back.json()["collected_at"] is None


async def test_no_finaliza_si_no_esta_en_atencion_de_toma(client, catalog):
    entry_id, _ = await _printed(client, catalog)
    res = await client.post(f"/api/v1/queue/{entry_id}/finish-sampling", json={})
    assert res.status_code == 409


async def test_catalogo_de_personal(client, catalog):
    catalog.add_staff("staff-1", "Luis", "Perez", "Toma de muestras")
    res = (await client.get("/api/v1/catalog/staff")).json()
    assert res == [
        {"id": "staff-1", "name": "Luis Perez", "job_title": "Toma de muestras"}
    ]
