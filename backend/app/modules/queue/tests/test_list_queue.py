from sqlalchemy import event

from app.core.database import engine
from app.modules.orders.tests.test_sampling import _printed, _reception_closed


async def _statements(client, url):
    seen: list[str] = []

    def spy(conn, cursor, statement, *_):
        seen.append(statement)

    event.listen(engine.sync_engine, "before_cursor_execute", spy)
    try:
        res = await client.get(url)
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", spy)
    assert res.status_code == 200, res.text
    return res.json(), seen


async def test_cola_incluye_version_y_numero_de_orden(client, catalog):
    entry_id, number = await _reception_closed(client, catalog)
    rows = (await client.get("/api/v1/queue?status=en_espera_impresion")).json()
    assert [r["id"] for r in rows] == [entry_id]
    assert rows[0]["order_number"] == number
    assert isinstance(rows[0]["version"], int) and rows[0]["version"] >= 1
    one = (await client.get(f"/api/v1/queue/{entry_id}")).json()
    assert one["version"] == rows[0]["version"]


async def test_filtro_de_profesional_se_hace_en_sql_y_no_trae_ordenes_ajenas(
    client, catalog
):
    entry_id, _ = await _printed(client, catalog)
    url = "/api/v1/queue?status=en_espera_toma_muestras&professional_id="
    mine, seen = await _statements(client, url + "staff-1")
    other, _ = await _statements(client, url + "staff-2")
    assert [e["id"] for e in mine] == [entry_id]
    assert mine[0]["order_number"]
    assert other == []
    # ninguna consulta lee la tabla de ordenes completa (sin ligarla a la cola)
    for stmt in seen:
        if "FROM orders" in stmt or "JOIN orders" in stmt:
            assert "queue_entries" in stmt
    filtered = [s for s in seen if "assigned_professional_id =" in s]
    assert filtered, "el filtro de profesional debe ir en SQL"
