"""GET /orders/{order_number}/tests/{test_id}/trace: eventos reales + derivados."""

from sqlalchemy import select, text

from app.conftest import FakeLeo
from app.core import permissions as p
from app.core.leo import catalog
from app.modules.orders.models import OrderTest
from app.modules.queue.tests.test_reception_owner import _as
from app.modules.results.tests.helpers import order_in_laboratory

ALL = set(catalog.tags)
RES = "/api/v1/results"
QC = "staff-qc"


async def _test_id(session, number, code):
    from app.modules.orders.models import Order

    return (
        await session.execute(
            select(OrderTest.id)
            .join(Order, Order.id == OrderTest.order_id)
            .where(Order.order_number == number, OrderTest.test_code == code)
        )
    ).scalar_one()


def _url(number, tid):
    return f"/api/v1/orders/{number}/tests/{tid}/trace"


def _steps(body):
    return [e["step"] for e in body["events"]]


async def test_trace_is_chronological_and_has_the_full_contract(
    client, catalog, session, leo: FakeLeo
):
    _, number = await order_in_laboratory(client, catalog, ("GLU",))
    tid = await _test_id(session, number, "GLU")
    _as(leo, "Analista A", ALL)
    body = {"professional_id": QC, "professional_name": "Resp", "values": {"GLU": "90"}}
    done = await client.post(f"{RES}/tests/{tid}/validate", json=body)
    assert done.status_code == 200, done.text

    res = await client.get(_url(number, tid))
    assert res.status_code == 200, res.text
    data = res.json()
    assert set(data) == {
        "order_number",
        "order_id",
        "test",
        "events",
        "page",
        "page_size",
        "total",
    }
    assert data["order_number"] == number
    assert set(data["test"]) == {
        "id",
        "code",
        "name",
        "area_code",
        "validation_status",
        "created_at",
    }
    assert (
        data["test"]["code"] == "GLU"
        and data["test"]["validation_status"] == "validated"
    )
    assert data["page"] == 1 and data["page_size"] == 50
    assert data["total"] == len(data["events"])
    ats = [e["at"] for e in data["events"]]
    assert ats == sorted(ats)
    for e in data["events"]:
        assert set(e) == {
            "at",
            "step",
            "scope",
            "actor",
            "summary",
            "details",
            "source",
        }
        assert set(e["actor"]) == {"id", "name", "staff_id"}
        assert e["scope"] in {"test", "order", "sample"}
    steps = _steps(data)
    for expected in (
        "queue.entered",
        "order.test_added",
        "queue.reception_closed",
        "labels.printed",
        "sample.collected",
        "lab.received",
        "result.entered",
        "test.validated",
        "order.finalized",
        "activation.issued",
    ):
        assert expected in steps, (expected, steps)
    # solo eventos reales para una orden creada despues de la 0011
    added = [e for e in data["events"] if e["step"] == "order.test_added"]
    assert [e["source"] for e in added] == ["event"]  # sin duplicado derivado
    assert added[0]["details"]["test_code"] == "GLU"
    # encadenado de cola: derivado; finalizada: real (sin duplicado)
    fin = [e for e in data["events"] if e["step"] == "order.finalized"]
    assert [e["source"] for e in fin] == ["event"] and fin[0]["scope"] == "order"
    queue = next(e for e in data["events"] if e["step"] == "queue.entered")
    assert queue["source"] == "derived" and queue["scope"] == "order"


async def test_trace_paginates(client, catalog, session):
    _, number = await order_in_laboratory(client, catalog, ("GLU",))
    tid = await _test_id(session, number, "GLU")
    full = (await client.get(_url(number, tid), params={"page_size": 200})).json()
    page2 = (
        await client.get(_url(number, tid), params={"page": 2, "page_size": 3})
    ).json()
    assert page2["total"] == full["total"] and page2["page"] == 2
    assert page2["events"] == full["events"][3:6]
    assert (
        await client.get(_url(number, tid), params={"page_size": 201})
    ).status_code == 422
    assert (await client.get(_url(number, tid), params={"page": 0})).status_code == 422


async def test_404_when_the_test_does_not_belong_to_the_order(client, catalog, session):
    _, number = await order_in_laboratory(client, catalog, ("GLU",))
    tid = await _test_id(session, number, "GLU")
    other = await client.get(_url("00000000", tid))
    assert other.status_code == 404
    unknown = await client.get(_url(number, "00000000-0000-0000-0000-000000000000"))
    assert unknown.status_code == 404


async def test_legacy_order_without_events_is_rebuilt_from_columns(
    client, catalog, session
):
    """Simula una orden anterior a la 0011: sin filas en order_test_events."""
    extra: dict = {}
    _, number = await order_in_laboratory(client, catalog, ("GLU",), extra)
    tid = await _test_id(session, number, "GLU")
    body = {"professional_id": QC, "professional_name": "Resp", "values": {"GLU": "90"}}
    await client.post(f"{RES}/tests/{tid}/validate", json=body)
    await session.execute(text("ALTER TABLE order_test_events DISABLE TRIGGER USER"))
    await session.execute(text("DELETE FROM order_test_events"))
    await session.execute(text("ALTER TABLE order_test_events ENABLE TRIGGER USER"))

    data = (await client.get(_url(number, tid))).json()
    assert {e["source"] for e in data["events"]} == {"derived"}
    steps = _steps(data)
    for expected in (
        "queue.entered",
        "queue.reception_claimed",
        "queue.reception_closed",
        "order.test_added",
        "labels.printed",
        "sample.collected",
        "lab.received",
        "result.entered",
        "test.validated",
        "order.finalized",
        "activation.issued",
    ):
        assert expected in steps, (expected, steps)
    entered = next(e for e in data["events"] if e["step"] == "result.entered")
    assert entered["details"]["after"] == 90 and entered["actor"]["id"]
    assert steps.count("sample.collected") == 1


async def test_derived_events_are_not_duplicated_by_real_ones(client, catalog, session):
    _, number = await order_in_laboratory(client, catalog, ("GLU",))
    tid = await _test_id(session, number, "GLU")
    data = (await client.get(_url(number, tid))).json()
    for step in (
        "sample.collected",
        "lab.received",
        "labels.printed",
        "order.test_added",
    ):
        sources = [e["source"] for e in data["events"] if e["step"] == step]
        assert sources == ["event"], (step, sources)


async def test_viewing_the_trace_is_audited(client, catalog, session, leo: FakeLeo):
    _, number = await order_in_laboratory(client, catalog, ("GLU",))
    tid = await _test_id(session, number, "GLU")
    leo.events.clear()
    assert (await client.get(_url(number, tid))).status_code == 200
    await _flush_audit()
    ev = [e for e in leo.events if e["action_tag"] == p.RES_TRACE]
    assert len(ev) == 1
    assert ev[0]["entity_type"] == "order_test" and ev[0]["entity_id"] == str(tid)


async def _flush_audit() -> None:
    from app.core.leo import auth

    flush = getattr(auth.audit, "flush", None)
    if flush is not None:
        await flush()


async def test_trace_excludes_other_tests_of_the_same_tube(client, catalog, session):
    _, number = await order_in_laboratory(client, catalog, ("GLU", "LIP"))
    tid = await _test_id(session, number, "GLU")
    data = (await client.get(_url(number, tid))).json()
    coded = [
        e["details"]["test_code"] for e in data["events"] if "test_code" in e["details"]
    ]
    assert coded and set(coded) == {"GLU"}


async def test_order_tests_list_contract_without_patient_data(
    client, catalog, session, leo: FakeLeo
):
    _, number = await order_in_laboratory(client, catalog, ("GLU",))
    tid = await _test_id(session, number, "GLU")
    _as(leo, "Analista A", ALL)
    res = await client.get(f"/api/v1/orders/{number}/tests")
    assert res.status_code == 200, res.text
    data = res.json()
    assert set(data) == {"order_number", "order_id", "tests"}
    assert data["order_number"] == number
    assert [set(t) for t in data["tests"]] == [
        {"id", "code", "name", "area_code", "validation_status"}
    ]
    assert data["tests"][0]["id"] == str(tid) and data["tests"][0]["code"] == "GLU"
    assert "patient" not in res.text


async def test_order_tests_list_404_and_403(client, catalog, leo: FakeLeo):
    _, number = await order_in_laboratory(client, catalog, ("GLU",))
    _as(leo, "Analista A", ALL)
    assert (await client.get("/api/v1/orders/00000000/tests")).status_code == 404
    _as(leo, "Sin traza", ALL - {p.RES_TRACE})
    assert (await client.get(f"/api/v1/orders/{number}/tests")).status_code == 403
