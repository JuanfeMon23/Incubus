"""El sello de captura (quien/cuando) solo cambia cuando el valor cambia."""

from app.conftest import FakeLeo
from app.core.leo import catalog
from app.modules.queue.tests.test_reception_owner import _as
from app.modules.results.tests.helpers import order_in_laboratory

API = "/api/v1/results"
QC = "staff-qc"
ALL = set(catalog.tags)


async def _tid(client, code):
    queue = (await client.get(f"{API}/queue", params={"professional_id": QC})).json()
    return next(
        t["order_test_id"] for o in queue for t in o["tests"] if t["code"] == code
    )


def _body(values):
    return {"professional_id": QC, "professional_name": "Resp", "values": values}


async def _rows(client, tid):
    res = await client.get(f"{API}/tests/{tid}", params={"professional_id": QC})
    return {r["code"]: r for r in res.json()["results"]}


async def _put(client, tid, values):
    res = await client.put(f"{API}/tests/{tid}/values", json=_body(values))
    assert res.status_code == 200, res.text


async def test_validar_con_el_mismo_valor_conserva_a_quien_capturo(
    client, catalog, leo: FakeLeo
):
    await order_in_laboratory(client, catalog)
    tid = await _tid(client, "GLU")
    a = _as(leo, "Analista A", ALL)
    await _put(client, tid, {"GLU": "90"})
    b = _as(leo, "Validador B", ALL)
    done = await client.post(f"{API}/tests/{tid}/validate", json=_body({"GLU": "90"}))
    assert done.status_code == 200, done.text
    glu = (await _rows(client, tid))["GLU"]
    assert glu["entered_by_user_id"] == str(a.id)
    assert glu["entered_by"] == "Analista A"
    detail = (
        await client.get(f"{API}/tests/{tid}", params={"professional_id": QC})
    ).json()
    assert detail["validated_by_user_id"] == str(b.id)


async def test_reenviar_igual_no_cambia_la_hora_y_cambiar_si_cambia_el_autor(
    client, catalog, leo: FakeLeo, session
):
    from sqlalchemy import select

    from app.modules.orders.models import OrderResult

    await order_in_laboratory(client, catalog)
    tid = await _tid(client, "GLU")
    _as(leo, "Analista A", ALL)
    await _put(client, tid, {"GLU": "90"})
    stamp = (
        await session.execute(
            select(OrderResult.entered_at).where(OrderResult.analyte_code == "GLU")
        )
    ).scalar_one()
    b = _as(leo, "Analista B", ALL)
    await _put(client, tid, {"GLU": "90,0"})  # mismo valor normalizado
    session.expire_all()
    same = (
        await session.execute(
            select(OrderResult.entered_at).where(OrderResult.analyte_code == "GLU")
        )
    ).scalar_one()
    assert same == stamp
    await _put(client, tid, {"GLU": "95"})
    glu = (await _rows(client, tid))["GLU"]
    assert glu["entered_by_user_id"] == str(b.id)
    assert glu["entered_by"] == "Analista B"


async def test_borrar_el_valor_limpia_el_sello(client, catalog, leo: FakeLeo):
    await order_in_laboratory(client, catalog)
    tid = await _tid(client, "GLU")
    _as(leo, "Analista A", ALL)
    await _put(client, tid, {"GLU": "90"})
    _as(leo, "Analista B", ALL)
    await _put(client, tid, {"GLU": ""})
    glu = (await _rows(client, tid))["GLU"]
    assert glu["value"] is None
    assert glu["entered_by"] is None and glu["entered_by_user_id"] is None


async def test_calculado_conserva_su_sello_si_el_resultado_no_cambia(
    client, catalog, leo: FakeLeo
):
    await order_in_laboratory(client, catalog)
    tid = await _tid(client, "LIP")
    a = _as(leo, "Analista A", ALL)
    await _put(client, tid, {"COL": "250", "HDL": "50", "TG": "100"})
    b = _as(leo, "Analista B", ALL)
    await _put(client, tid, {"COL": "250", "HDL": "50", "TG": "100"})
    rows = await _rows(client, tid)
    assert rows["LDL"]["entered_by_user_id"] == str(a.id)
    # cambia un insumo: el calculado cambia y pasa a B junto con el insumo
    await _put(client, tid, {"HDL": "40"})
    rows = await _rows(client, tid)
    assert rows["HDL"]["entered_by_user_id"] == str(b.id)
    assert rows["COL"]["entered_by_user_id"] == str(a.id)
    assert rows["LDL"]["value"] == 190
    assert rows["LDL"]["entered_by_user_id"] == str(b.id)
