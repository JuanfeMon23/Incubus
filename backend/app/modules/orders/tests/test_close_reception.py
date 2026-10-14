import asyncio
from datetime import UTC, datetime

from sqlalchemy import text

from app.core.database import AsyncSessionLocal
from app.modules.orders.service import next_order_number

PATIENT = {
    "document_number": "1020304050",
    "first_name": "JUAN",
    "first_last_name": "GOMEZ",
    "sex": "M",
    "birth_date": "1985-03-12",
}


FULL_DEMOGRAPHICS = {
    "birth_place": "Bogota",
    "blood_type": "O+",
    "email": "a@b.co",
    "phone": "3001112233",
    "address": "Calle 1 # 2-3",
    "insurer": "EPS Salud",
}


async def _reception(client, catalog):
    catalog.add_test(
        "COL",
        "Colesterol",
        [{"category": "ayuno", "value": 8, "unit": "horas", "text": "Ayuno 8h"}],
    )
    catalog.add_test(
        "TRI",
        "Trigliceridos",
        [
            {"category": "ayuno", "value": 12, "unit": "horas", "text": "Ayuno 12h"},
            {"category": "tabaco", "value": 2, "unit": "horas", "text": "No fumar"},
        ],
    )
    pr = {p["code"]: p["id"] for p in (await client.get("/api/v1/priorities")).json()}
    entry = (
        await client.post(
            "/api/v1/queue", json={"patient": PATIENT, "priority_id": pr["alta"]}
        )
    ).json()
    await client.post(f"/api/v1/queue/{entry['id']}/claim", json={"actor": "ana"})
    return entry


async def test_preview_unifica_preanaliticos(client, catalog):
    await _reception(client, catalog)
    res = await client.post(
        "/api/v1/orders/preview", json={"test_codes": ["COL", "TRI"]}
    )
    pres = {p["category"]: p for p in res.json()["preconditions"]}
    assert pres["ayuno"]["duration_value"] == 12
    assert pres["ayuno"]["source_test_codes"] == ["COL", "TRI"]
    assert "tabaco" in pres and len(res.json()["preconditions"]) == 2


async def test_cierre_exige_datos_y_examenes(client, catalog):
    entry = await _reception(client, catalog)
    url = f"/api/v1/orders/close-reception/{entry['id']}"
    assert (await client.post(url, json={"test_codes": []})).status_code == 422
    falta = await client.post(url, json={"test_codes": ["COL"]})
    assert falta.status_code == 422
    assert falta.json()["details"]["missing_fields"] == [
        "birth_place",
        "blood_type",
        "email",
        "phone",
        "address",
        "insurer",
    ]
    inexistente = await client.post(url, json={"test_codes": ["NOPE"]})
    assert inexistente.status_code == 422


async def test_cierre_genera_orden_y_pasa_a_espera_de_impresion(client, catalog):
    entry = await _reception(client, catalog)
    await client.patch(
        f"/api/v1/patients/{entry['patient']['id']}",
        json=FULL_DEMOGRAPHICS,
    )
    preview = (
        await client.post("/api/v1/orders/preview", json={"test_codes": ["COL", "TRI"]})
    ).json()
    assert all(p["key"] for p in preview["preconditions"])
    res = await client.post(
        f"/api/v1/orders/close-reception/{entry['id']}",
        json={
            "test_codes": ["COL", "TRI"],
            "actor": "ana",
            "precondition_checks": [
                {"key": p["key"], "met": True} for p in preview["preconditions"]
            ],
        },
    )
    assert res.status_code == 200, res.text
    number = res.json()["order_number"]
    assert len(number) == 8 and number.isdigit()

    after = (await client.get(f"/api/v1/queue/{entry['id']}")).json()
    assert after["status"] == "en_espera_impresion"
    assert after["order_number"] == number

    order = (await client.get(f"/api/v1/orders/{number}")).json()
    assert {t["code"] for t in order["tests"]} == {"COL", "TRI"}


async def test_consecutivo_secuencial_y_reinicia_por_mes(session):
    oct_ = datetime(2097, 10, 15, 12, tzinfo=UTC)
    nov = datetime(2097, 11, 3, 12, tzinfo=UTC)
    assert await next_order_number(session, oct_) == "97100001"
    assert await next_order_number(session, oct_) == "97100002"
    assert await next_order_number(session, nov) == "97110001"
    assert await next_order_number(session, oct_) == "97100003"


async def test_consecutivo_bajo_concurrencia_sin_duplicados_ni_huecos():
    moment = datetime(2099, 1, 15, 12, tzinfo=UTC)

    async def one() -> str:
        async with AsyncSessionLocal() as s:
            number = await next_order_number(s, moment)
            await s.commit()
            return number

    try:
        numbers = await asyncio.gather(*(one() for _ in range(25)))
        assert sorted(numbers) == [f"9901{i:04d}" for i in range(1, 26)]
    finally:
        async with AsyncSessionLocal() as s:
            await s.execute(text("DELETE FROM order_counters WHERE year_month='9901'"))
            await s.commit()
