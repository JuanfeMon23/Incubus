import httpx

from app.modules.catalog_client.client import CatalogClient

BASE = {"first_name": "ANA", "first_last_name": "LOPEZ"}


async def _priority(client):
    prs = (await client.get("/api/v1/priorities")).json()
    return next(p["id"] for p in prs if p["code"] == "media")


async def test_tipos_de_documento_parametrizados(client):
    res = (await client.get("/api/v1/document-types")).json()
    codes = [d["code"] for d in res]
    assert {"CC", "TI", "CE", "PA", "RC"} <= set(codes)
    assert all(d["name"] for d in res)


async def test_ingreso_con_tipo_de_documento_que_no_existe(client):
    res = await client.post(
        "/api/v1/queue",
        json={
            "patient": {**BASE, "document_type": "XX", "document_number": "1234567"},
            "priority_id": await _priority(client),
        },
    )
    assert res.status_code == 422
    assert res.json()["details"]["document_type"] == "XX"


async def test_ingreso_con_tipo_no_cedula(client):
    res = await client.post(
        "/api/v1/queue",
        json={
            "patient": {**BASE, "document_type": "PA", "document_number": "AB123456"},
            "priority_id": await _priority(client),
        },
    )
    assert res.status_code == 201
    assert res.json()["patient"]["document_type"] == "PA"


async def test_rh_solo_valores_validos(client):
    pid = await _priority(client)
    ok = await client.post(
        "/api/v1/queue",
        json={
            "patient": {**BASE, "document_number": "5550001", "blood_type": "O+"},
            "priority_id": pid,
        },
    )
    assert ok.status_code == 201
    bad = await client.post(
        "/api/v1/queue",
        json={
            "patient": {**BASE, "document_number": "5550002", "blood_type": "Z9"},
            "priority_id": pid,
        },
    )
    assert bad.status_code == 422
    patient_id = ok.json()["patient"]["id"]
    bad_patch = await client.patch(
        f"/api/v1/patients/{patient_id}", json={"blood_type": "hola"}
    )
    assert bad_patch.status_code == 422


async def test_telefono_solo_numeros(client):
    pid = await _priority(client)
    ok = await client.post(
        "/api/v1/queue",
        json={"patient": {**BASE, "document_number": "5550003"}, "priority_id": pid},
    )
    patient_id = ok.json()["patient"]["id"]
    fine = await client.patch(
        f"/api/v1/patients/{patient_id}", json={"phone": "3001234567"}
    )
    assert fine.status_code == 200
    for bad in ("30012a4567", "300-123", "12"):
        res = await client.patch(f"/api/v1/patients/{patient_id}", json={"phone": bad})
        assert res.status_code == 422, bad


async def test_busqueda_de_paciente_existente_por_documento(client):
    pid = await _priority(client)
    created = await client.post(
        "/api/v1/queue",
        json={
            "patient": {
                **BASE,
                "document_number": "5550004",
                "blood_type": "A+",
                "sex": "F",
                "birth_date": "1990-01-02",
            },
            "priority_id": pid,
        },
    )
    patient_id = created.json()["patient"]["id"]
    await client.patch(
        f"/api/v1/patients/{patient_id}",
        json={"email": "a@b.co", "phone": "3001234567", "address": "Calle 1"},
    )
    found = await client.get(
        "/api/v1/patients/lookup",
        params={"document_type": "CC", "document_number": "5550004"},
    )
    assert found.status_code == 200
    body = found.json()
    assert body["first_name"] == "ANA" and body["email"] == "a@b.co"
    assert body["phone"] == "3001234567" and body["blood_type"] == "A+"

    missing = await client.get(
        "/api/v1/patients/lookup",
        params={"document_type": "CC", "document_number": "000"},
    )
    assert missing.status_code == 404


async def test_la_plantilla_publicada_se_consulta_una_sola_vez():
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        calls.append(path)
        if path.endswith("/result-template-versions/v1"):
            return httpx.Response(200, json={"id": "v1", "result_template_id": "t1"})
        if path.endswith("/sections"):
            return httpx.Response(200, json=[])
        if path.endswith("/analytes") and "result-templates" in path:
            return httpx.Response(
                200,
                json=[
                    {
                        "id": f"ta{i}",
                        "analyte_id": f"a{i}",
                        "section_id": None,
                        "sort_order": i,
                        "result_type": "numeric",
                        "unit": "mg/dL",
                        "decimals": 0,
                        "option_set_id": None,
                        "formula": None,
                        "is_required": True,
                        "is_reportable": True,
                        "is_active": True,
                    }
                    for i in range(3)
                ],
            )
        if path.endswith("/api/v1/analytes"):
            return httpx.Response(
                200,
                json={
                    "items": [
                        {"id": f"a{i}", "code": f"A{i}", "name": f"An {i}"}
                        for i in range(3)
                    ]
                },
            )
        if path.endswith("/reference-ranges"):
            return httpx.Response(200, json=[])
        return httpx.Response(404)

    client = CatalogClient("http://vladimir", transport=httpx.MockTransport(handler))
    first = await client.template_structure("v1")
    n = len(calls)
    second = await client.template_structure("v1")
    assert [a["code"] for a in first["analytes"]] == ["A0", "A1", "A2"]
    assert second == first
    assert len(calls) == n  # la segunda lectura sale de cache
