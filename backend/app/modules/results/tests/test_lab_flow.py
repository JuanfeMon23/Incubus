from app.modules.results.tests.helpers import PRO, order_in_laboratory, setup_catalog

QC = "staff-qc"
HEM = "staff-hem"


async def _queue(client, professional_id, q=None):
    params = {"professional_id": professional_id}
    if q:
        params["q"] = q
    res = await client.get("/api/v1/results/queue", params=params)
    assert res.status_code == 200, res.text
    return res.json()


async def _test_id(client, professional_id, code):
    for order in await _queue(client, professional_id):
        for t in order["tests"]:
            if t["code"] == code:
                return t["order_test_id"]
    raise AssertionError(f"no hay {code} en la cola de {professional_id}")


# ------------------------------------------------------- recepcion en laboratorio


async def test_cola_de_recepcion_en_laboratorio_con_busqueda(client, catalog):
    entry_id, _number = await order_in_laboratory(client, catalog)
    # ya recibida: no aparece en la cola de recepcion
    assert (await client.get("/api/v1/lab/reception")).json() == []
    assert entry_id


async def test_recepcion_exige_todos_los_tubos_para_pasar_a_laboratorio(
    client, catalog
):
    setup_catalog(catalog)
    from app.modules.results.tests.helpers import DEMOGRAPHICS, PATIENT

    pr = {p["code"]: p["id"] for p in (await client.get("/api/v1/priorities")).json()}
    catalog.add_sample_type("lila", "Tapa lila", "#7C3AED", draw_order=2)
    catalog.tests["VIH"]["sample_types"] = [
        {
            "sample_type_id": "lila",
            "is_preferred": True,
            "required_volume_ml": 2,
            "is_active": True,
        }
    ]
    e = (
        await client.post(
            "/api/v1/queue", json={"patient": PATIENT, "priority_id": pr["media"]}
        )
    ).json()
    eid = e["id"]
    await client.post(f"/api/v1/queue/{eid}/claim", json={"actor": "r"})
    await client.patch(f"/api/v1/patients/{e['patient']['id']}", json=DEMOGRAPHICS)
    await client.post(
        f"/api/v1/orders/close-reception/{eid}", json={"test_codes": ["GLU", "VIH"]}
    )
    await client.post(
        f"/api/v1/orders/by-entry/{eid}/print-labels", json={**PRO, "actor": "i"}
    )
    await client.post(
        f"/api/v1/queue/{eid}/claim",
        json={"actor": "x", "professional_id": PRO["professional_id"]},
    )
    tubes = (await client.get(f"/api/v1/orders/by-entry/{eid}")).json()["samples"]
    assert len(tubes) == 2
    for t in tubes:
        await client.post(f"/api/v1/orders/samples/{t['id']}/collect", json={})
    await client.post(f"/api/v1/queue/{eid}/finish-sampling", json={})

    waiting = (await client.get("/api/v1/lab/reception")).json()
    assert [w["entry_id"] for w in waiting] == [eid]
    assert waiting[0]["pending"] == 2

    first = await client.post(
        f"/api/v1/orders/samples/{tubes[0]['id']}/receive", json={"actor": "lab"}
    )
    assert first.status_code == 200
    assert (await client.get(f"/api/v1/queue/{eid}")).json()[
        "status"
    ] == "toma_finalizada"
    assert (await client.get("/api/v1/lab/reception")).json()[0]["pending"] == 1

    # se puede deshacer mientras no pase a laboratorio
    undo = await client.post(
        f"/api/v1/orders/samples/{tubes[0]['id']}/unreceive", json={}
    )
    assert undo.json()["received_at"] is None

    for t in tubes:
        await client.post(
            f"/api/v1/orders/samples/{t['id']}/receive", json={"actor": "lab"}
        )
    assert (await client.get(f"/api/v1/queue/{eid}")).json()[
        "status"
    ] == "en_laboratorio"
    assert (await client.get("/api/v1/lab/reception")).json() == []


async def test_busqueda_en_recepcion_por_orden_o_documento(client, catalog):
    # una orden sin recibir
    setup_catalog(catalog)
    from app.modules.results.tests.helpers import DEMOGRAPHICS, PATIENT

    pr = {p["code"]: p["id"] for p in (await client.get("/api/v1/priorities")).json()}
    e = (
        await client.post(
            "/api/v1/queue", json={"patient": PATIENT, "priority_id": pr["alta"]}
        )
    ).json()
    eid = e["id"]
    await client.post(f"/api/v1/queue/{eid}/claim", json={"actor": "r"})
    await client.patch(f"/api/v1/patients/{e['patient']['id']}", json=DEMOGRAPHICS)
    number = (
        await client.post(
            f"/api/v1/orders/close-reception/{eid}", json={"test_codes": ["GLU"]}
        )
    ).json()["order_number"]
    await client.post(
        f"/api/v1/orders/by-entry/{eid}/print-labels", json={**PRO, "actor": "i"}
    )
    await client.post(
        f"/api/v1/queue/{eid}/claim",
        json={"actor": "x", "professional_id": PRO["professional_id"]},
    )
    for t in (await client.get(f"/api/v1/orders/by-entry/{eid}")).json()["samples"]:
        await client.post(f"/api/v1/orders/samples/{t['id']}/collect", json={})
    await client.post(f"/api/v1/queue/{eid}/finish-sampling", json={})

    assert (
        len((await client.get("/api/v1/lab/reception", params={"q": number})).json())
        == 1
    )
    assert (
        len(
            (
                await client.get("/api/v1/lab/reception", params={"q": "7001002003"})
            ).json()
        )
        == 1
    )
    assert (
        await client.get("/api/v1/lab/reception", params={"q": "99999999"})
    ).json() == []


# ------------------------------------------------------------ cola por area


async def test_cada_profesional_solo_ve_su_area(client, catalog):
    await order_in_laboratory(client, catalog)
    qc = await _queue(client, QC)
    hem = await _queue(client, HEM)
    assert {t["code"] for o in qc for t in o["tests"]} == {"GLU", "LIP"}
    assert {t["code"] for o in hem for t in o["tests"]} == {"VIH"}
    assert all(t["area_code"] == "QUI" for o in qc for t in o["tests"])


async def test_validadores_son_quienes_encargan_un_area(client, catalog):
    setup_catalog(catalog)
    res = (await client.get("/api/v1/catalog/validators")).json()
    by_id = {v["id"]: v for v in res}
    assert set(by_id) == {QC, HEM}
    assert [a["code"] for a in by_id[QC]["areas"]] == ["QUI"]


async def test_buscador_de_ordenes_del_area(client, catalog):
    _, number = await order_in_laboratory(client, catalog)
    assert len(await _queue(client, QC, q=number)) == 1
    assert len(await _queue(client, QC, q="7001002003")) == 1
    assert len(await _queue(client, QC, q="RUIZ")) == 1
    assert len(await _queue(client, QC, q="glu")) == 1
    assert await _queue(client, QC, q="00000000") == []


# --------------------------------------------------------------- resultados


async def test_estructura_valores_y_banderas(client, catalog):
    await order_in_laboratory(client, catalog)
    tid = await _test_id(client, QC, "GLU")
    detail = (
        await client.get(f"/api/v1/results/tests/{tid}", params={"professional_id": QC})
    ).json()
    assert detail["code"] == "GLU"
    assert detail["patient"]["sex"] == "F"
    row = detail["results"][0]
    assert row["code"] == "GLU" and row["unit"] == "mg/dL"
    assert row["value"] is None

    saved = await client.put(
        f"/api/v1/results/tests/{tid}/values",
        json={
            "professional_id": QC,
            "professional_name": "Paola",
            "values": {"GLU": "126"},
        },
    )
    assert saved.status_code == 200, saved.text
    row = saved.json()["results"][0]
    assert row["value"] == 126
    assert row["flag"] == "high"
    assert saved.json()["validation_status"] == "draft"

    crit = await client.put(
        f"/api/v1/results/tests/{tid}/values",
        json={
            "professional_id": QC,
            "professional_name": "Paola",
            "values": {"GLU": "30"},
        },
    )
    assert crit.json()["results"][0]["flag"] == "critical_low"


async def test_analito_calculado_se_obtiene_de_la_formula(client, catalog):
    await order_in_laboratory(client, catalog)
    tid = await _test_id(client, QC, "LIP")
    saved = await client.put(
        f"/api/v1/results/tests/{tid}/values",
        json={
            "professional_id": QC,
            "professional_name": "Paola",
            "values": {"COL": "250", "HDL": "50", "TG": "100"},
        },
    )
    rows = {r["code"]: r for r in saved.json()["results"]}
    assert rows["LDL"]["value"] == 180  # 250 - 50 - 100/5
    assert rows["LDL"]["flag"] == "high"
    assert rows["COL"]["flag"] == "high"
    # el calculado no se puede digitar
    bad = await client.put(
        f"/api/v1/results/tests/{tid}/values",
        json={"professional_id": QC, "professional_name": "P", "values": {"LDL": "10"}},
    )
    assert bad.status_code == 422


async def test_valor_invalido_y_opcion_fuera_del_conjunto(client, catalog):
    await order_in_laboratory(client, catalog)
    glu = await _test_id(client, QC, "GLU")
    res = await client.put(
        f"/api/v1/results/tests/{glu}/values",
        json={
            "professional_id": QC,
            "professional_name": "P",
            "values": {"GLU": "abc"},
        },
    )
    assert res.status_code == 422
    assert res.json()["details"]["field"] == "GLU"
    vih = await _test_id(client, HEM, "VIH")
    res = await client.put(
        f"/api/v1/results/tests/{vih}/values",
        json={
            "professional_id": HEM,
            "professional_name": "H",
            "values": {"VIH": "zzz"},
        },
    )
    assert res.status_code == 422
    ok = await client.put(
        f"/api/v1/results/tests/{vih}/values",
        json={
            "professional_id": HEM,
            "professional_name": "H",
            "values": {"VIH": "pos"},
        },
    )
    assert ok.json()["results"][0]["flag"] == "abnormal"


async def test_no_se_accede_a_examenes_de_otra_area(client, catalog):
    await order_in_laboratory(client, catalog)
    tid = await _test_id(client, QC, "GLU")
    res = await client.get(
        f"/api/v1/results/tests/{tid}", params={"professional_id": HEM}
    )
    assert res.status_code == 403
    res = await client.put(
        f"/api/v1/results/tests/{tid}/values",
        json={
            "professional_id": HEM,
            "professional_name": "H",
            "values": {"GLU": "90"},
        },
    )
    assert res.status_code == 403


async def test_validar_exige_los_obligatorios(client, catalog):
    await order_in_laboratory(client, catalog)
    tid = await _test_id(client, QC, "LIP")
    res = await client.post(
        f"/api/v1/results/tests/{tid}/validate",
        json={
            "professional_id": QC,
            "professional_name": "Paola",
            "values": {"COL": "180"},
        },
    )
    assert res.status_code == 422
    assert res.json()["code"] == "missing_results"
    assert set(res.json()["details"]["codes"]) == {"HDL", "TG"}


async def test_orden_finaliza_cuando_todas_las_areas_validan(client, catalog):
    entry_id, number = await order_in_laboratory(client, catalog)
    glu = await _test_id(client, QC, "GLU")
    lip = await _test_id(client, QC, "LIP")
    vih = await _test_id(client, HEM, "VIH")
    body = {"professional_name": "P"}

    r1 = await client.post(
        f"/api/v1/results/tests/{glu}/validate",
        json={**body, "professional_id": QC, "values": {"GLU": "90"}},
    )
    assert r1.status_code == 200 and r1.json()["order_finalized"] is False
    r2 = await client.post(
        f"/api/v1/results/tests/{lip}/validate",
        json={
            **body,
            "professional_id": QC,
            "values": {"COL": "180", "HDL": "50", "TG": "100"},
        },
    )
    assert r2.json()["order_finalized"] is False
    # lo validado sale de la cola del area
    assert await _queue(client, QC) == []
    # aun no se entrega
    assert (await client.get(f"/api/v1/delivery/orders/{number}")).status_code == 404

    r3 = await client.post(
        f"/api/v1/results/tests/{vih}/validate",
        json={**body, "professional_id": HEM, "values": {"VIH": "neg"}},
    )
    assert r3.json()["order_finalized"] is True
    assert (await client.get(f"/api/v1/queue/{entry_id}")).json()[
        "status"
    ] == "finalizada"

    # un examen validado ya no se modifica
    again = await client.put(
        f"/api/v1/results/tests/{glu}/values",
        json={**body, "professional_id": QC, "values": {"GLU": "10"}},
    )
    assert again.status_code == 409


async def test_entrega_json_y_pdf_de_la_orden_finalizada(client, catalog):
    _, number = await order_in_laboratory(client, catalog, test_codes=("GLU",))
    glu = await _test_id(client, QC, "GLU")
    await client.post(
        f"/api/v1/results/tests/{glu}/validate",
        json={
            "professional_id": QC,
            "professional_name": "Paola",
            "values": {"GLU": "95"},
        },
    )
    data = (await client.get(f"/api/v1/delivery/orders/{number}")).json()
    assert data["order_number"] == number
    assert data["patient"]["document_number"] == "7001002003"
    result = data["tests"][0]["results"][0]
    assert (
        result["name"] == "Glucosa"
        and result["value"] == 95
        and result["flag"] == "normal"
    )
    assert data["tests"][0]["validated_by"] == "Paola"
    pdf = await client.get(f"/api/v1/delivery/orders/{number}/report.pdf")
    assert pdf.status_code == 200
    assert pdf.headers["content-type"] == "application/pdf"
    assert pdf.content.startswith(b"%PDF")


async def test_orden_con_todos_sus_examenes_del_area_incluye_los_validados(
    client, catalog
):
    entry_id, number = await order_in_laboratory(client, catalog)
    glu = await _test_id(client, QC, "GLU")

    before = await client.get(
        f"/api/v1/results/orders/{entry_id}", params={"professional_id": QC}
    )
    assert before.status_code == 200
    data = before.json()
    assert data["order_number"] == number
    assert {t["code"] for t in data["tests"]} == {"GLU", "LIP"}  # solo su area
    assert all(t["validation_status"] == "pending" for t in data["tests"])

    await client.post(
        f"/api/v1/results/tests/{glu}/validate",
        json={
            "professional_id": QC,
            "professional_name": "Paola",
            "values": {"GLU": "90"},
        },
    )
    after = (
        await client.get(
            f"/api/v1/results/orders/{entry_id}", params={"professional_id": QC}
        )
    ).json()
    by_code = {t["code"]: t for t in after["tests"]}
    assert by_code["GLU"]["validation_status"] == "validated"
    assert by_code["GLU"]["validated_by"] == "Paola"
    assert by_code["GLU"]["validated_at"]
    assert by_code["LIP"]["validation_status"] == "pending"
    # el listado general ya no ofrece el validado
    queue = await _queue(client, QC)
    assert [t["code"] for t in queue[0]["tests"]] == ["LIP"]


async def test_orden_sin_examenes_en_el_area_del_profesional(client, catalog):
    entry_id, _ = await order_in_laboratory(client, catalog, test_codes=("GLU",))
    res = await client.get(
        f"/api/v1/results/orders/{entry_id}", params={"professional_id": HEM}
    )
    assert res.status_code == 403
