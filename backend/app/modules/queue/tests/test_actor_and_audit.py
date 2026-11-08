"""El actor sale de la sesion de Leo y las mutaciones se auditan sin PII."""

import json

from sqlalchemy import select

from app.conftest import FakeLeo, make_leo_user
from app.core import permissions
from app.modules.orders.models import OrderResult
from app.modules.orders.tests.test_sampling import (
    PATIENT,
    _claim,
    _printed,
)
from app.modules.results.tests.helpers import order_in_laboratory

API = "/api/v1"
# Datos personales de los pacientes de estas pruebas: jamas deben llegar a Leo.
PII = ("ANA", "LOPEZ", PATIENT["document_number"], "ZULEMA", "QUINTERO", "7766554433")


def _tags(leo: FakeLeo) -> list[str]:
    return [event["action_tag"] for event in leo.events if event["result"] == "ok"]


def _assert_no_pii(leo: FakeLeo) -> None:
    dump = json.dumps(leo.events, ensure_ascii=False).upper()
    for word in PII:
        assert word.upper() not in dump, word


async def _tubes(client, entry_id):
    detail = (await client.get(f"{API}/orders/by-entry/{entry_id}")).json()
    return detail["samples"]


async def _enter(client, document="7766554433"):
    prio = (await client.get(f"{API}/priorities")).json()[0]["id"]
    response = await client.post(
        f"{API}/queue",
        json={
            "patient": {
                "document_number": document,
                "first_name": "ZULEMA",
                "first_last_name": "QUINTERO",
            },
            "priority_id": prio,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


# --- Actor ------------------------------------------------------------------------


async def test_the_actor_is_the_authenticated_person_not_the_body(
    client, leo: FakeLeo
) -> None:
    entry = await _enter(client)
    claimed = await client.post(
        f"{API}/queue/{entry['id']}/claim", json={"actor": "alguien-mas"}
    )
    assert claimed.json()["claimed_by"] == "Tester Uno"
    history = (await client.get(f"{API}/queue/{entry['id']}/history")).json()
    assert [history_entry["actor"] for history_entry in history] == [
        "Tester Uno",
        "Tester Uno",
    ]


async def test_each_person_leaves_their_own_name_in_the_history(
    client, leo: FakeLeo
) -> None:
    entry = await _enter(client)
    leo.user = make_leo_user(leo.user.permissions, name="Maria Ruiz")
    await client.post(f"{API}/queue/{entry['id']}/claim")
    history = (await client.get(f"{API}/queue/{entry['id']}/history")).json()
    assert [history_entry["actor"] for history_entry in history] == [
        "Tester Uno",
        "Maria Ruiz",
    ]


async def test_sampling_and_lab_actors_come_from_the_session(
    client, catalog, leo
) -> None:
    entry_id, _ = await _printed(client, catalog)
    await _claim(client, entry_id)
    tube = (await _tubes(client, entry_id))[0]
    collected = await client.post(
        f"{API}/orders/samples/{tube['id']}/collect", json={"actor": "falso"}
    )
    assert collected.json()["collected_by"] == "Tester Uno"
    history = (await client.get(f"{API}/queue/{entry_id}/history")).json()
    assert {history_entry["actor"] for history_entry in history} == {"Tester Uno"}


async def test_entering_results_records_the_session_user_as_who_typed(
    client, catalog, leo, session
) -> None:
    await order_in_laboratory(client, catalog)
    queue = (
        await client.get(f"{API}/results/queue", params={"professional_id": "staff-qc"})
    ).json()
    test_id = next(
        test["order_test_id"]
        for queue_entry in queue
        for test in queue_entry["tests"]
        if test["code"] == "GLU"
    )
    saved = await client.put(
        f"{API}/results/tests/{test_id}/values",
        json={
            "professional_id": "staff-qc",
            "professional_name": "Quimica Responsable",
            "values": {"GLU": "90"},
        },
    )
    assert saved.status_code == 200, saved.text
    typed = (
        await session.execute(
            select(OrderResult.entered_by).where(OrderResult.analyte_code == "GLU")
        )
    ).scalar_one()
    assert typed == "Tester Uno"  # no el `professional_name` del cuerpo


# --- Auditoria -----------------------------------------------------------------------


async def test_enqueue_is_audited_without_personal_data(client, leo: FakeLeo) -> None:
    entry = await _enter(client)
    (event,) = leo.events
    assert event["action_tag"] == permissions.PRE_ENQUEUE
    assert event["entity_type"] == "queue_entry"
    assert event["entity_id"] == entry["id"]
    assert event["changes"]["status"] == {"before": None, "after": "pre_recepcion"}
    assert event["actor"]["jkt"] == "jkt-falso"
    _assert_no_pii(leo)


async def test_state_changes_are_audited_with_the_stage_diff(
    client, leo: FakeLeo
) -> None:
    entry = await _enter(client)
    await client.post(f"{API}/queue/{entry['id']}/claim")
    reasons = (await client.get(f"{API}/return-reasons")).json()
    await client.post(
        f"{API}/queue/{entry['id']}/return", json={"reason_id": reasons[0]["id"]}
    )
    removal = (await client.get(f"{API}/removal-reasons")).json()
    await client.post(
        f"{API}/queue/{entry['id']}/remove",
        json={"reason_id": removal[0]["id"], "note": "ZULEMA se fue"},
    )
    claim, ret, rem = leo.events[1:]
    assert claim["action_tag"] == permissions.REC_CALL_NEXT
    assert claim["changes"]["status"] == {
        "before": "pre_recepcion",
        "after": "en_atencion_recepcion",
    }
    assert ret["action_tag"] == permissions.REC_RETURN
    assert ret["changes"]["return_reason_id"]["after"] == reasons[0]["id"]
    assert rem["action_tag"] == permissions.PRE_REMOVE
    assert rem["changes"]["status"]["after"] == "retirado"
    assert rem["changes"]["removal_reason_id"]["after"] == removal[0]["id"]
    _assert_no_pii(leo)  # ni siquiera la nota libre del retiro


async def test_patient_edit_audits_field_names_only(client, leo: FakeLeo) -> None:
    entry = await _enter(client)
    await client.post(f"{API}/queue/{entry['id']}/claim")
    leo.events.clear()
    response = await client.patch(
        f"{API}/patients/{entry['patient']['id']}",
        json={"address": "Calle 99 # 1-2", "phone": "3009998877"},
    )
    assert response.status_code == 200
    (event,) = leo.events
    assert event["action_tag"] == permissions.REC_EDIT_PATIENT
    assert event["entity_type"] == "patient"
    assert event["changes"]["changed_fields"]["after"] == ["address", "phone"]
    dump = json.dumps(leo.events)
    assert "Calle 99" not in dump and "3009998877" not in dump


async def test_the_whole_flow_is_audited_without_personal_data(
    client, catalog, leo: FakeLeo
) -> None:
    entry_id, _ = await _printed(client, catalog)
    await _claim(client, entry_id)
    tubes = await _tubes(client, entry_id)
    for tube in tubes:
        await client.post(f"{API}/orders/samples/{tube['id']}/collect")
    checks = (await client.get(f"{API}/orders/by-entry/{entry_id}")).json()
    await client.post(
        f"{API}/orders/by-entry/{entry_id}/precondition-checks",
        json={
            "stage": "sampling",
            "checks": [
                {"key": precondition["key"], "met": True}
                for precondition in checks["preconditions"]
            ],
        },
    )
    done = await client.post(f"{API}/queue/{entry_id}/finish-sampling")
    assert done.status_code == 200, done.text
    for tube in tubes:
        await client.post(f"{API}/orders/samples/{tube['id']}/receive")
    tags = _tags(leo)
    for tag in (
        permissions.PRE_ENQUEUE,
        permissions.REC_CALL_NEXT,
        permissions.REC_EDIT_PATIENT,
        permissions.REC_CLOSE,
        permissions.LBL_PRINT,
        permissions.SAM_CLAIM,
        permissions.SAM_COLLECT,
        permissions.SAM_FINISH,
        permissions.LAB_RECEIVE,
    ):
        assert tag in tags, tag
    close = next(
        event for event in leo.events if event["action_tag"] == permissions.REC_CLOSE
    )
    assert close["changes"]["status"]["after"] == "en_espera_impresion"
    assert close["changes"]["order_number"]["after"]
    _assert_no_pii(leo)


async def test_result_entry_and_validation_are_audited(client, catalog, leo) -> None:
    await order_in_laboratory(client, catalog)
    leo.events.clear()
    queue = (
        await client.get(f"{API}/results/queue", params={"professional_id": "staff-qc"})
    ).json()
    test_id = next(
        test["order_test_id"]
        for queue_entry in queue
        for test in queue_entry["tests"]
        if test["code"] == "GLU"
    )
    body = {
        "professional_id": "staff-qc",
        "professional_name": "Quimica Responsable",
        "values": {"GLU": "90"},
    }
    assert (
        await client.put(f"{API}/results/tests/{test_id}/values", json=body)
    ).status_code == 200
    validated = await client.post(f"{API}/results/tests/{test_id}/validate", json=body)
    assert validated.status_code == 200, validated.text
    enter, validate = leo.events
    assert enter["action_tag"] == permissions.RES_ENTER
    assert enter["entity_type"] == "order_test" and enter["entity_id"] == test_id
    assert enter["changes"]["analytes_with_value"]["after"] == 1
    assert validate["action_tag"] == permissions.RES_VALIDATE
    assert validate["changes"]["validation_status"]["after"] == "validated"
    # solo estados y contadores: ni valores de resultados ni nombres
    assert set(enter["changes"]) == {"validation_status", "analytes_with_value"}
    assert set(validate["changes"]) == {"validation_status", "order_finalized"}
    assert "RUIZ" not in json.dumps(leo.events).upper()
