"""Armado de una orden hasta `toma_finalizada` para las pruebas de laboratorio."""

PATIENT = {
    "document_number": "7001002003",
    "first_name": "MARIA",
    "first_last_name": "RUIZ",
    "sex": "F",
    "birth_date": "1990-06-15",
}
DEMOGRAPHICS = {
    "birth_place": "Bogota",
    "blood_type": "O+",
    "email": "m@r.co",
    "phone": "3001112233",
    "address": "Calle 1",
    "insurer": "EPS",
}
PRO = {"professional_id": "staff-toma", "professional_name": "Luis Toma"}


def setup_catalog(catalog) -> None:
    catalog.add_sample_type("red", "Tapa roja", "#DC2626", draw_order=1)
    catalog.add_area("area-qc", "QUI", manager_staff_id="staff-qc")
    catalog.add_area("area-hem", "HEM", manager_staff_id="staff-hem")
    catalog.add_staff("staff-qc", "Paola", "Quimica", "Bacterióloga")
    catalog.add_staff("staff-hem", "Hugo", "Hemato", "Bacteriólogo")
    # Glucosa: numerico con rango; LDL calculado; examen cualitativo en otra area.
    catalog.add_test(
        "GLU",
        "Glucosa",
        [],
        sample_types=[("red", True, 3.0)],
        area_id="area-qc",
        template="ver-glu",
    )
    catalog.add_test(
        "LIP",
        "Perfil lipidico",
        [],
        sample_types=[("red", True, 3.0)],
        area_id="area-qc",
        template="ver-lip",
    )
    catalog.add_test(
        "VIH",
        "Prueba rapida",
        [],
        sample_types=[("red", True, 3.0)],
        area_id="area-hem",
        template="ver-vih",
    )
    catalog.add_template(
        "ver-glu",
        analytes=[
            {
                "code": "GLU",
                "name": "Glucosa",
                "section": "Glucosa",
                "result_type": "numeric",
                "unit": "mg/dL",
                "decimals": 0,
                "ranges": [
                    {
                        "sex": "any",
                        "low": 70,
                        "high": 100,
                        "critical_low": 40,
                        "critical_high": 400,
                    }
                ],
            }
        ],
    )
    catalog.add_template(
        "ver-lip",
        analytes=[
            {
                "code": "COL",
                "name": "Colesterol total",
                "section": "Lipidos",
                "result_type": "numeric",
                "unit": "mg/dL",
                "decimals": 0,
                "ranges": [{"sex": "any", "high": 200}],
            },
            {
                "code": "HDL",
                "name": "HDL",
                "section": "Lipidos",
                "result_type": "numeric",
                "unit": "mg/dL",
                "decimals": 0,
                "ranges": [],
            },
            {
                "code": "TG",
                "name": "Trigliceridos",
                "section": "Lipidos",
                "result_type": "numeric",
                "unit": "mg/dL",
                "decimals": 0,
                "ranges": [],
            },
            {
                "code": "LDL",
                "name": "LDL calculado",
                "section": "Lipidos",
                "result_type": "calculated",
                "unit": "mg/dL",
                "decimals": 0,
                "formula": "COL - HDL - TG / 5",
                "ranges": [{"sex": "any", "high": 130}],
            },
        ],
    )
    catalog.add_template(
        "ver-vih",
        analytes=[
            {
                "code": "VIH",
                "name": "VIH 1/2",
                "section": "Serologia",
                "result_type": "qualitative",
                "options": [
                    {"id": "neg", "label": "No reactivo"},
                    {"id": "pos", "label": "Reactivo"},
                ],
                "ranges": [{"sex": "any", "expected_option_id": "neg"}],
            }
        ],
    )


async def order_in_laboratory(client, catalog, test_codes=("GLU", "LIP", "VIH")):
    """Recorre recepcion -> impresion -> toma -> recepcion en laboratorio.

    Devuelve `(entry_id, order_number)` con la entrada en `en_laboratorio`.
    """
    setup_catalog(catalog)
    pr = {p["code"]: p["id"] for p in (await client.get("/api/v1/priorities")).json()}
    entry = (
        await client.post(
            "/api/v1/queue", json={"patient": PATIENT, "priority_id": pr["media"]}
        )
    ).json()
    eid = entry["id"]
    await client.post(f"/api/v1/queue/{eid}/claim", json={"actor": "r"})
    await client.patch(f"/api/v1/patients/{entry['patient']['id']}", json=DEMOGRAPHICS)
    close = await client.post(
        f"/api/v1/orders/close-reception/{eid}",
        json={"test_codes": list(test_codes), "actor": "r"},
    )
    assert close.status_code == 200, close.text
    number = close.json()["order_number"]
    r = await client.post(
        f"/api/v1/orders/by-entry/{eid}/print-labels", json={**PRO, "actor": "i"}
    )
    assert r.status_code == 200, r.text
    await client.post(
        f"/api/v1/queue/{eid}/claim",
        json={
            "actor": PRO["professional_name"],
            "professional_id": PRO["professional_id"],
        },
    )
    detail = (await client.get(f"/api/v1/orders/by-entry/{eid}")).json()
    for tube in detail["samples"]:
        await client.post(f"/api/v1/orders/samples/{tube['id']}/collect", json={})
    done = await client.post(f"/api/v1/queue/{eid}/finish-sampling", json={})
    assert done.status_code == 200, done.text
    for tube in detail["samples"]:
        res = await client.post(
            f"/api/v1/orders/samples/{tube['id']}/receive", json={"actor": "lab"}
        )
        assert res.status_code == 200, res.text
    state = (await client.get(f"/api/v1/queue/{eid}")).json()["status"]
    assert state == "en_laboratorio", state
    return eid, number
