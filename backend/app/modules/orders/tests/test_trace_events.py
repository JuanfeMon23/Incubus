"""Instrumentacion de la traza: cada mutacion deja su evento en la misma
transaccion, con el actor autenticado y sin datos personales del paciente."""

from uuid import UUID, uuid4

from sqlalchemy import select

from app.conftest import FakeLeo
from app.core.leo import Actor, catalog
from app.core.trace import record_test_event
from app.modules.activation.models import ActivationCode
from app.modules.orders.models import (
    Order,
    OrderSample,
    OrderTest,
    OrderTestEvent,
)
from app.modules.orders.tests.test_sampling import _claim, _printed, _reception_closed
from app.modules.queue.tests.test_reception_owner import _as
from app.modules.results.tests.helpers import PATIENT, PRO, order_in_laboratory

ALL = set(catalog.tags)
RES = "/api/v1/results"
ORD = "/api/v1/orders"
QC = "staff-qc"


async def _events(session, step=None, order_number=None):
    stmt = select(OrderTestEvent).order_by(OrderTestEvent.occurred_at)
    if step:
        stmt = stmt.where(OrderTestEvent.step == step)
    if order_number:
        stmt = stmt.join(Order, Order.id == OrderTestEvent.order_id).where(
            Order.order_number == order_number
        )
    result = await session.execute(stmt.execution_options(populate_existing=True))
    return list(result.scalars())


async def _tid(client, code):
    queue = (await client.get(f"{RES}/queue", params={"professional_id": QC})).json()
    return next(
        t["order_test_id"] for o in queue for t in o["tests"] if t["code"] == code
    )


def _body(values):
    return {"professional_id": QC, "professional_name": "Resp", "values": values}


async def _put(client, tid, values):
    res = await client.put(f"{RES}/tests/{tid}/values", json=_body(values))
    assert res.status_code == 200, res.text


# ---------------------------------------------------------------- helper


async def test_helper_records_actor_staff_and_truncates_in_the_same_session(
    client, catalog, session
):
    _, number = await order_in_laboratory(client, catalog, ("GLU",))
    order = (
        await session.execute(select(Order).where(Order.order_number == number))
    ).scalar_one()
    staff = uuid4()
    uid = uuid4()
    ev = await record_test_event(
        session,
        "demo.step_one",
        Actor("Ana", uid),
        order.id,
        summary="x" * 500,
        details={"when": order.created_at, "id": uid},
        staff_id=str(staff),
    )
    assert (ev.actor_name, ev.actor_user_id, ev.staff_id) == ("Ana", uid, staff)
    assert len(ev.summary) == 300
    assert ev.details["id"] == str(uid) and isinstance(ev.details["when"], str)
    bad = await record_test_event(
        session, "demo.step_one", None, order.id, summary="s", staff_id="staff-qc"
    )
    assert bad.staff_id is None and bad.actor_name is None


async def test_request_id_header_is_stored_when_present(client, catalog, session):
    entry_id, _ = await _printed(client, catalog)
    await _claim(client, entry_id)
    tube = (await client.get(f"{ORD}/by-entry/{entry_id}")).json()["samples"][0]
    res = await client.post(
        f"{ORD}/samples/{tube['id']}/collect", headers={"x-request-id": "req-123"}
    )
    assert res.status_code == 200
    ev = (await _events(session, "sample.collected"))[0]
    assert ev.request_id == "req-123"


# ------------------------------------------------------------ recepcion


async def test_close_reception_one_event_per_test_and_created_by(
    client, catalog, session, leo: FakeLeo
):
    user = _as(leo, "Recepcion Uno", ALL)
    _, number = await _reception_closed(client, catalog)
    events = await _events(session, "order.test_added", number)
    assert sorted(e.details["test_code"] for e in events) == ["COL", "HEM", "TRI"]
    assert all(e.order_test_id and e.actor_user_id == user.id for e in events)
    tests = (await session.execute(select(OrderTest))).scalars().all()
    assert {t.created_by for t in tests} == {"Recepcion Uno"}
    assert {t.created_by_user_id for t in tests} == {user.id}
    # preanaliticos respondidos en el cierre: evento de la orden (sin prueba)
    pre = await _events(session, "precondition.checked", number)
    assert pre and all(e.order_test_id is None for e in pre)
    assert pre[0].details["stage"] == "reception"
    assert pre[0].details["before"] is None and pre[0].details["after"]["met"] is True
    # codigo de activacion: quien lo emitio, sin el codigo
    issued = (await _events(session, "activation.issued", number))[0]
    code = (await session.execute(select(ActivationCode))).scalar_one()
    assert code.created_by_user_id == user.id and issued.actor_user_id == user.id
    assert set(issued.details) == {"expires_at"}


async def test_no_patient_data_in_event_details(client, catalog, session):
    await order_in_laboratory(client, catalog, ("GLU",))
    blob = " ".join(str(e.details) + e.summary for e in await _events(session))
    assert PATIENT["document_number"] not in blob
    assert PATIENT["first_name"] not in blob and "RUIZ" not in blob


async def test_precondition_save_records_before_and_after_per_stage(
    client, catalog, session, leo: FakeLeo
):
    entry_id, number = await _printed(client, catalog)
    detail = (await client.get(f"{ORD}/by-entry/{entry_id}")).json()
    key = detail["preconditions"][0]["key"]
    user = _as(leo, "Toma Uno", ALL)
    await _claim(client, entry_id)
    res = await client.post(
        f"{ORD}/by-entry/{entry_id}/precondition-checks",
        json={
            "stage": "sampling",
            "checks": [{"key": key, "met": False, "note": "comió"}],
        },
    )
    assert res.status_code == 200, res.text
    ev = next(
        e
        for e in await _events(session, "precondition.checked", number)
        if e.details["stage"] == "sampling"
    )
    assert ev.details["key"] == key
    assert ev.details["before"] == {"met": None, "note": None}
    assert ev.details["after"] == {"met": False, "note": "comió"}
    assert ev.actor_user_id == user.id and ev.order_test_id is None


# --------------------------------------------------------- etiquetas/tubos


async def test_print_labels_fills_columns_and_events_and_downloads_are_logged(
    client, catalog, session, leo: FakeLeo
):
    entry_id, number = await _reception_closed(client, catalog)
    user = _as(leo, "Impresion Uno", ALL)
    res = await client.post(f"{ORD}/by-entry/{entry_id}/print-labels", json=PRO)
    assert res.status_code == 200, res.text
    tubes = (await session.execute(select(OrderSample))).scalars().all()
    assert {t.labels_printed_by_user_id for t in tubes} == {user.id}
    assert {t.labels_printed_by for t in tubes} == {"Impresion Uno"}
    printed = await _events(session, "labels.printed", number)
    assert len(printed) == 3  # un evento por prueba contenida en los tubos
    assert {e.details["test_code"] for e in printed} == {"COL", "TRI", "HEM"}
    assert all(e.order_sample_id and e.order_test_id for e in printed)

    pdf = await client.get(f"{ORD}/by-entry/{entry_id}/labels.pdf")
    zpl = await client.get(f"{ORD}/by-entry/{entry_id}/labels.zpl")
    assert pdf.status_code == zpl.status_code == 200
    down = await _events(session, "labels.downloaded", number)
    assert sorted({e.details["format"] for e in down}) == ["pdf", "zpl"]
    assert len(down) == 6


async def test_collect_uncollect_receive_unreceive_keep_who_did_each(
    client, catalog, session, leo: FakeLeo
):
    entry_id, number = await _printed(client, catalog)
    a = _as(leo, "Toma A", ALL)
    await _claim(client, entry_id)
    tubes = (await client.get(f"{ORD}/by-entry/{entry_id}")).json()["samples"]
    red = next(t for t in tubes if set(t["test_codes"]) == {"COL", "TRI"})
    await client.post(f"{ORD}/samples/{red['id']}/collect")
    b = _as(leo, "Toma B", ALL)
    res = await client.post(f"{ORD}/samples/{red['id']}/uncollect")
    assert res.status_code == 200, res.text
    collected = await _events(session, "sample.collected", number)
    uncollected = await _events(session, "sample.uncollected", number)
    assert len(collected) == len(uncollected) == 2  # COL y TRI
    assert {e.actor_user_id for e in collected} == {a.id}  # el previo se conserva
    assert {e.actor_user_id for e in uncollected} == {b.id}
    assert {e.details["sample_id"] for e in collected} == {red["id"]}
    assert {e.details["test_code"] for e in collected} == {"COL", "TRI"}


async def test_lab_receive_and_unreceive_events(client, catalog, session, leo: FakeLeo):
    entry_id, number = await _printed(client, catalog)
    await _claim(client, entry_id)
    detail = (await client.get(f"{ORD}/by-entry/{entry_id}")).json()
    tubes = detail["samples"]
    checks = [{"key": q["key"], "met": True} for q in detail["preconditions"]]
    await client.post(
        f"{ORD}/by-entry/{entry_id}/precondition-checks",
        json={"stage": "sampling", "checks": checks},
    )
    for t in tubes:
        await client.post(f"{ORD}/samples/{t['id']}/collect")
    assert (
        await client.post(f"/api/v1/queue/{entry_id}/finish-sampling", json={})
    ).status_code == 200
    a = _as(leo, "Lab A", ALL)
    red = next(t for t in tubes if set(t["test_codes"]) == {"COL", "TRI"})
    assert (await client.post(f"{ORD}/samples/{red['id']}/receive")).status_code == 200
    b = _as(leo, "Lab B", ALL)
    assert (
        await client.post(f"{ORD}/samples/{red['id']}/unreceive")
    ).status_code == 200
    received = await _events(session, "lab.received", number)
    unreceived = await _events(session, "lab.unreceived", number)
    assert len(received) == len(unreceived) == 2
    assert {e.actor_user_id for e in received} == {a.id}
    assert {e.actor_user_id for e in unreceived} == {b.id}
    assert {e.details["sample_id"] for e in unreceived} == {red["id"]}


# ------------------------------------------------------------- resultados


async def test_result_events_only_for_real_changes_incl_calculated(
    client, catalog, session, leo: FakeLeo
):
    _, number = await order_in_laboratory(client, catalog, ("LIP",))
    tid = await _tid(client, "LIP")
    a = _as(leo, "Analista A", ALL)
    await _put(client, tid, {"COL": "250", "HDL": "50", "TG": "100"})
    entered = await _events(session, "result.entered", number)
    by_code = {e.details["analyte_code"]: e for e in entered}
    assert set(by_code) == {"COL", "HDL", "TG", "LDL"}
    assert by_code["COL"].details["before"] is None
    assert by_code["COL"].details["after"] == 250
    assert by_code["COL"].details["flag"] == "high"
    assert by_code["COL"].actor_user_id == a.id
    assert by_code["LDL"].details["calculated"] is True
    assert "calculado" in by_code["LDL"].summary

    before = len(await _events(session))
    await _put(client, tid, {"COL": "250,0"})  # mismo valor: nada
    assert len(await _events(session)) == before

    await _put(client, tid, {"COL": "180"})
    changed = await _events(session, "result.changed", number)
    assert {e.details["analyte_code"] for e in changed} == {"COL", "LDL"}
    col = next(e for e in changed if e.details["analyte_code"] == "COL")
    assert (col.details["before"], col.details["after"]) == (250, 180)

    await _put(client, tid, {"HDL": None})
    cleared = await _events(session, "result.cleared", number)
    assert {e.details["analyte_code"] for e in cleared} == {"HDL", "LDL"}
    assert all(e.details["after"] is None for e in cleared)


async def test_validate_records_flags_validator_and_finalizes_the_order(
    client, catalog, session, leo: FakeLeo
):
    _, number = await order_in_laboratory(client, catalog, ("GLU",))
    tid = await _tid(client, "GLU")
    _as(leo, "Analista A", ALL)
    b = _as(leo, "Validador B", ALL)
    res = await client.post(f"{RES}/tests/{tid}/validate", json=_body({"GLU": "500"}))
    assert res.status_code == 200, res.text
    ev = (await _events(session, "test.validated", number))[0]
    assert ev.order_test_id == UUID(tid) and ev.actor_user_id == b.id
    assert ev.details["abnormal_flags"] == [
        {"analyte_code": "GLU", "flag": "critical_high"}
    ]
    assert ev.details["validated_by"] == "Resp"
    final = await _events(session, "order.finalized", number)
    assert len(final) == 1 and final[0].order_test_id is None
    # la captura al validar tambien queda
    assert len(await _events(session, "result.entered", number)) == 1


# ------------------------------------------------------ activacion/entrega


async def test_activation_used_and_delivery_events_carry_client_not_health_data(
    client, catalog, session, leo: FakeLeo
):
    extra: dict = {}
    _, number = await order_in_laboratory(client, catalog, ("GLU",), extra)
    tid = await _tid(client, "GLU")
    await client.post(f"{RES}/tests/{tid}/validate", json=_body({"GLU": "90"}))
    svc = _as(leo, "Acuarius", ALL)
    verify = await client.post(
        "/api/v1/delivery/activation/verify",
        json={
            "code": extra["activation_code"],
            "document_type": "CC",
            "document_number": PATIENT["document_number"],
            "birth_date": PATIENT["birth_date"],
        },
    )
    assert verify.status_code == 200, verify.text
    used = (await _events(session, "activation.used", number))[0]
    code = (await session.execute(select(ActivationCode))).scalar_one()
    assert code.used_by_client == svc.username == used.details["client"]
    assert extra["activation_code"] not in str(used.details) + used.summary

    base = "/api/v1/delivery"
    assert (await client.get(f"{base}/orders/{number}")).status_code == 200
    assert (await client.get(f"{base}/orders/{number}/report.pdf")).status_code == 200
    listed = await client.get(f"{base}/patients/CC/{PATIENT['document_number']}/orders")
    assert listed.status_code == 200
    for step in (
        "delivery.order_viewed",
        "delivery.report_downloaded",
        "delivery.patient_orders_listed",
    ):
        evs = await _events(session, step, number)
        assert len(evs) == 1 and evs[0].details == {"client": svc.username}
        assert evs[0].order_test_id is None
