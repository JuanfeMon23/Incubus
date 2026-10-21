"""Propiedad del turno de RECEPCION y de las verificaciones de toma, nombre del
motivo en el historial y autor de cada resultado."""

from sqlalchemy import text

from app.conftest import FakeLeo, make_leo_user
from app.core import permissions as p
from app.core.leo import auth, catalog
from app.modules.orders.tests.test_sampling import (
    FULL_DEMOGRAPHICS,
    PATIENT,
    _claim,
    _printed,
    _reception_closed,
)
from app.modules.results.tests.helpers import order_in_laboratory

API = "/api/v1"
ALL = set(catalog.tags)
NO_SUPERVISE = ALL - {p.REC_SUPERVISE, p.SAM_SUPERVISE}
REC_SUPERVISOR = NO_SUPERVISE | {p.REC_SUPERVISE}


def _as(leo: FakeLeo, name: str, tags=NO_SUPERVISE):
    leo.user = make_leo_user(tags, name=name)
    return leo.user


def _denied(leo: FakeLeo) -> list[str]:
    return [e["action_tag"] for e in leo.events if e["result"] == "denied"]


def _assert_not_owner(response, owner_name: str) -> None:
    assert response.status_code == 403, response.text
    body = response.json()
    assert body["code"] == "not_turn_owner"
    assert body["message"].startswith(f"Este turno lo tomó {owner_name}.")
    assert body["details"]["claimed_by"] == owner_name


async def _called(client, leo: FakeLeo, owner="Recepcion A", document="9900112233"):
    """Entrada en atencion de recepcion llamada por `owner` (sin supervise)."""
    prio = (await client.get(f"{API}/priorities")).json()[0]["id"]
    entry = (
        await client.post(
            f"{API}/queue",
            json={
                "patient": {**PATIENT, "document_number": document},
                "priority_id": prio,
            },
        )
    ).json()
    _as(leo, owner)
    called = await client.post(f"{API}/queue/call-next")
    assert called.status_code == 200, called.text
    assert called.json()["id"] == entry["id"]
    return entry


async def _reasons(client):
    return (await client.get(f"{API}/return-reasons")).json()


# --- Catalogo ------------------------------------------------------------------------


def test_the_reception_supervise_tag_is_in_the_catalog() -> None:
    auth.check_catalog()
    assert p.REC_SUPERVISE == "incubus.reception.supervise"
    assert p.REC_SUPERVISE in catalog.tags
    module = next(
        m for m in catalog.to_payload()["modules"] if m["slug"] == "reception"
    )
    action = next(a for a in module["actions"] if a["verb"] == "supervise")
    assert action["name"] == "Gestionar turnos de otros recepcionistas"


# --- Recepcion: dueno ------------------------------------------------------------------


async def test_the_reception_owner_can_edit_and_return(
    client, catalog, leo: FakeLeo
) -> None:
    entry = await _called(client, leo)
    edit = await client.put(
        f"{API}/queue/{entry['id']}/draft", json={"test_codes": ["X"]}
    )
    assert edit.status_code == 200, edit.text
    patch = await client.patch(
        f"{API}/patients/{entry['patient']['id']}", json=FULL_DEMOGRAPHICS
    )
    assert patch.status_code == 200, patch.text
    back = await client.post(
        f"{API}/queue/{entry['id']}/return",
        json={"reason_id": (await _reasons(client))[0]["id"]},
    )
    assert back.status_code == 200, back.text
    assert back.json()["status"] == "pre_recepcion"


async def test_the_reception_owner_can_close(client, catalog, leo: FakeLeo) -> None:
    _as(leo, "Recepcion A")
    _entry_id, number = await _reception_closed(client, catalog)
    assert number


async def test_another_receptionist_is_denied_and_nothing_changes(
    client, catalog, leo: FakeLeo
) -> None:
    catalog.add_test("COL", "Colesterol", [])
    entry = await _called(client, leo)
    _as(leo, "Recepcion B")
    leo.events.clear()
    pid, eid = entry["patient"]["id"], entry["id"]
    reason = (await _reasons(client))[0]["id"]
    attempts = [
        await client.put(f"{API}/queue/{eid}/draft", json={"test_codes": ["COL"]}),
        await client.patch(f"{API}/patients/{pid}", json={"email": "x@y.co"}),
        await client.post(f"{API}/queue/{eid}/return", json={"reason_id": reason}),
        await client.post(
            f"{API}/orders/close-reception/{eid}", json={"test_codes": ["COL"]}
        ),
    ]
    for attempt in attempts:
        _assert_not_owner(attempt, "Recepcion A")
    assert _denied(leo) == [
        p.REC_EDIT_PATIENT,
        p.REC_EDIT_PATIENT,
        p.REC_RETURN,
        p.REC_CLOSE,
    ]
    after = (await client.get(f"{API}/queue/{eid}")).json()
    assert after["status"] == "en_atencion_recepcion"
    assert after["claimed_by"] == "Recepcion A"
    assert after["draft"] == {}
    assert after["patient"]["email"] is None


async def test_a_reception_supervisor_can_act_on_others_turns(
    client, catalog, leo: FakeLeo
) -> None:
    entry = await _called(client, leo)
    _as(leo, "Jefa", REC_SUPERVISOR)
    eid = entry["id"]
    assert (
        await client.put(f"{API}/queue/{eid}/draft", json={"test_codes": []})
    ).status_code == 200
    assert (
        await client.patch(
            f"{API}/patients/{entry['patient']['id']}", json={"email": "x@y.co"}
        )
    ).status_code == 200
    back = await client.post(
        f"{API}/queue/{eid}/return",
        json={"reason_id": (await _reasons(client))[0]["id"]},
    )
    assert back.status_code == 200, back.text


async def test_sampling_supervise_does_not_grant_reception_supervision(
    client, catalog, leo: FakeLeo
) -> None:
    entry = await _called(client, leo)
    _as(leo, "Jefa de toma", NO_SUPERVISE | {p.SAM_SUPERVISE})
    response = await client.put(
        f"{API}/queue/{entry['id']}/draft", json={"test_codes": []}
    )
    _assert_not_owner(response, "Recepcion A")


async def test_a_legacy_reception_turn_is_allowed(
    client, catalog, leo: FakeLeo, session
) -> None:
    entry = await _called(client, leo)
    await session.execute(
        text("UPDATE queue_entries SET claimed_by_user_id = NULL WHERE id = :i"),
        {"i": entry["id"]},
    )
    _as(leo, "Recepcion B")
    response = await client.put(
        f"{API}/queue/{entry['id']}/draft", json={"test_codes": []}
    )
    assert response.status_code == 200, response.text


async def test_removing_does_not_require_owning_the_reception_turn(
    client, catalog, leo: FakeLeo
) -> None:
    entry = await _called(client, leo)
    _as(leo, "Recepcion B")
    reason = (await client.get(f"{API}/removal-reasons")).json()[0]["id"]
    response = await client.post(
        f"{API}/queue/{entry['id']}/remove", json={"reason_id": reason}
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "retirado"


async def test_patching_a_patient_without_a_turn_needs_no_ownership(
    client, catalog, leo: FakeLeo
) -> None:
    prio = (await client.get(f"{API}/priorities")).json()[0]["id"]
    entry = (
        await client.post(
            f"{API}/queue", json={"patient": PATIENT, "priority_id": prio}
        )
    ).json()
    _as(leo, "Recepcion B")
    response = await client.patch(
        f"{API}/patients/{entry['patient']['id']}", json={"email": "x@y.co"}
    )
    assert response.status_code == 200, response.text


async def test_reception_precondition_checks_require_the_reception_turn(
    client, catalog, leo: FakeLeo, session
) -> None:
    owner = _as(leo, "Recepcion A")
    entry_id, _ = await _reception_closed(client, catalog)
    # Estado forzado: la entrada con orden vuelve a atencion de recepcion.
    await session.execute(
        text(
            "UPDATE queue_entries SET status = 'en_atencion_recepcion', "
            "claimed_by = 'Recepcion A', claimed_by_user_id = :u WHERE id = :i"
        ),
        {"i": entry_id, "u": owner.id},
    )
    detail = (await client.get(f"{API}/orders/by-entry/{entry_id}")).json()
    body = {
        "stage": "reception",
        "checks": [{"key": c["key"], "met": True} for c in detail["preconditions"]],
    }
    url = f"{API}/orders/by-entry/{entry_id}/precondition-checks"
    assert (await client.post(url, json=body)).status_code == 200
    _as(leo, "Recepcion B")
    leo.events.clear()
    _assert_not_owner(await client.post(url, json=body), "Recepcion A")
    assert _denied(leo) == [p.REC_EDIT_PATIENT]
    _as(leo, "Jefa", REC_SUPERVISOR)
    assert (await client.post(url, json=body)).status_code == 200


# --- Toma: verificaciones de precondiciones ------------------------------------------------


async def test_sampling_precondition_checks_require_the_sampling_turn(
    client, catalog, leo: FakeLeo
) -> None:
    entry_id, _ = await _printed(client, catalog)
    _as(leo, "Tecnica A")
    await _claim(client, entry_id)
    detail = (await client.get(f"{API}/orders/by-entry/{entry_id}")).json()
    body = {
        "stage": "sampling",
        "checks": [{"key": c["key"], "met": True} for c in detail["preconditions"]],
    }
    url = f"{API}/orders/by-entry/{entry_id}/precondition-checks"
    assert (await client.post(url, json=body)).status_code == 200
    _as(leo, "Tecnica B")
    leo.events.clear()
    _assert_not_owner(await client.post(url, json=body), "Tecnica A")
    assert _denied(leo) == [p.SAM_COLLECT]
    _as(leo, "Supervisora", NO_SUPERVISE | {p.SAM_SUPERVISE})
    assert (await client.post(url, json=body)).status_code == 200


# --- Historial: nombre del motivo -------------------------------------------------------------


async def test_history_includes_the_reason_names(client, catalog, leo: FakeLeo) -> None:
    entry = await _called(client, leo)
    reason = (await _reasons(client))[0]
    await client.post(
        f"{API}/queue/{entry['id']}/return", json={"reason_id": reason["id"]}
    )
    await client.post(f"{API}/queue/{entry['id']}/claim")
    removal = (await client.get(f"{API}/removal-reasons")).json()[0]
    await client.post(
        f"{API}/queue/{entry['id']}/remove", json={"reason_id": removal["id"]}
    )
    history = (await client.get(f"{API}/queue/{entry['id']}/history")).json()
    returned = next(h for h in history if h["kind"] == "return")
    removed = next(h for h in history if h["kind"] == "remove")
    assert returned["return_reason_id"] == reason["id"]
    assert returned["return_reason_name"] == reason["name"]
    assert returned["removal_reason_name"] is None
    assert removed["removal_reason_name"] == removal["name"]
    assert history[0]["return_reason_name"] is None


# --- Resultados: quien capturo y quien valido ------------------------------------------------------


async def test_result_detail_exposes_who_entered_and_who_validated(
    client, catalog, leo: FakeLeo
) -> None:
    await order_in_laboratory(client, catalog)
    analyst = _as(leo, "Quimico Uno", ALL)
    queue = (
        await client.get(f"{API}/results/queue", params={"professional_id": "staff-qc"})
    ).json()
    order = next(o for o in queue if any(t["code"] == "GLU" for t in o["tests"]))
    test_id = next(t["order_test_id"] for t in order["tests"] if t["code"] == "GLU")
    body = {
        "professional_id": "staff-qc",
        "professional_name": "Quimica Responsable",
        "values": {"GLU": "90"},
    }
    params = {"professional_id": "staff-qc"}
    before = (await client.get(f"{API}/results/tests/{test_id}", params=params)).json()
    assert before["validated_by_user_id"] is None
    assert before["results"][0]["entered_by"] is None
    assert before["results"][0]["entered_by_user_id"] is None
    await client.put(f"{API}/results/tests/{test_id}/values", json=body)
    typed = (await client.get(f"{API}/results/tests/{test_id}", params=params)).json()
    glu = next(r for r in typed["results"] if r["code"] == "GLU")
    assert glu["entered_by"] == "Quimico Uno"
    assert glu["entered_by_user_id"] == str(analyst.id)
    validator = _as(leo, "Quimico Dos", ALL)
    done = await client.post(f"{API}/results/tests/{test_id}/validate", json=body)
    assert done.status_code == 200, done.text
    detail = (await client.get(f"{API}/results/tests/{test_id}", params=params)).json()
    glu = next(r for r in detail["results"] if r["code"] == "GLU")
    # validar reenvia los mismos valores: siguen a nombre de quien los capturo
    assert glu["entered_by_user_id"] == str(analyst.id)
    assert detail["validated_by"] == "Quimica Responsable"
    assert detail["validated_by_user_id"] == str(validator.id)
    summary = (
        await client.get(f"{API}/results/orders/{order['entry_id']}", params=params)
    ).json()
    item = next(t for t in summary["tests"] if t["order_test_id"] == test_id)
    assert item["validated_by_user_id"] == str(validator.id)
