"""Quien actuo: cada accion deja el id del usuario de Leo junto al nombre, y el
turno de toma de muestras es de quien lo tomo (salvo un supervisor)."""

import json
from uuid import UUID

from sqlalchemy import select, text

from app.conftest import FakeLeo, make_leo_user
from app.core import permissions as p
from app.core.leo import auth, catalog
from app.modules.orders.models import OrderPrecondition, OrderResult, OrderTest
from app.modules.orders.tests.test_sampling import _claim, _printed
from app.modules.queue import events
from app.modules.results.tests.helpers import order_in_laboratory

API = "/api/v1"
ALL = set(catalog.tags)
NO_SUPERVISE = ALL - {p.SAM_SUPERVISE}


def _as(leo: FakeLeo, name: str, tags=NO_SUPERVISE):
    leo.user = make_leo_user(tags, name=name)
    return leo.user


async def _tubes(client, entry_id):
    return (await client.get(f"{API}/orders/by-entry/{entry_id}")).json()["samples"]


async def _taking(client, catalog_, leo: FakeLeo, owner_name="Tecnica A"):
    """Entrada en atencion de toma tomada por `owner_name` (sin supervise)."""
    entry_id, _ = await _printed(client, catalog_)
    owner = _as(leo, owner_name)
    await _claim(client, entry_id)
    return entry_id, owner


def _assert_not_owner(response, owner_name: str) -> None:
    assert response.status_code == 403, response.text
    body = response.json()
    assert body["code"] == "not_turn_owner"
    assert owner_name in body["message"]


def _denied(leo: FakeLeo) -> list[str]:
    return [e["action_tag"] for e in leo.events if e["result"] == "denied"]


# --- Catalogo ---------------------------------------------------------------------


def test_the_supervise_tag_is_in_the_catalog_with_a_readable_name() -> None:
    auth.check_catalog()
    assert p.SAM_SUPERVISE == "incubus.sampling.supervise"
    assert p.SAM_SUPERVISE in catalog.tags
    sampling = next(
        m for m in catalog.to_payload()["modules"] if m["slug"] == "sampling"
    )
    action = next(a for a in sampling["actions"] if a["verb"] == "supervise")
    assert action["name"] == "Gestionar turnos de otros técnicos"


# --- Historial y turno ----------------------------------------------------------------


async def test_history_and_claim_record_who_acted_by_id(client, leo: FakeLeo) -> None:
    prio = (await client.get(f"{API}/priorities")).json()[0]["id"]
    creator = _as(leo, "Ana Ingreso")
    entry = (
        await client.post(
            f"{API}/queue",
            json={
                "patient": {
                    "document_number": "7766554433",
                    "first_name": "Z",
                    "first_last_name": "Q",
                },
                "priority_id": prio,
            },
        )
    ).json()
    caller = _as(leo, "Maria Recepcion")
    claimed = (await client.post(f"{API}/queue/{entry['id']}/claim")).json()
    assert claimed["claimed_by"] == "Maria Recepcion"
    assert claimed["claimed_by_user_id"] == str(caller.id)
    history = (await client.get(f"{API}/queue/{entry['id']}/history")).json()
    assert [(h["actor"], h["actor_user_id"]) for h in history] == [
        ("Ana Ingreso", str(creator.id)),
        ("Maria Recepcion", str(caller.id)),
    ]
    reasons = (await client.get(f"{API}/return-reasons")).json()
    returned = await client.post(
        f"{API}/queue/{entry['id']}/return", json={"reason_id": reasons[0]["id"]}
    )
    assert returned.json()["claimed_by"] is None
    assert returned.json()["claimed_by_user_id"] is None  # junto con el nombre
    last = (await client.get(f"{API}/queue/{entry['id']}/history")).json()[-1]
    assert last["actor_user_id"] == str(caller.id)


async def test_call_next_records_the_caller_id(client, leo: FakeLeo) -> None:
    prio = (await client.get(f"{API}/priorities")).json()[0]["id"]
    await client.post(
        f"{API}/queue",
        json={
            "patient": {
                "document_number": "123123123",
                "first_name": "A",
                "first_last_name": "B",
            },
            "priority_id": prio,
        },
    )
    caller = _as(leo, "Maria Recepcion")
    called = (await client.post(f"{API}/queue/call-next")).json()
    assert called["claimed_by_user_id"] == str(caller.id)
    history = (await client.get(f"{API}/queue/{called['id']}/history")).json()
    assert history[-1]["actor_user_id"] == str(caller.id)


async def test_socket_events_carry_neither_names_nor_user_ids(
    client, catalog, leo: FakeLeo, monkeypatch
) -> None:
    sent: list[dict] = []

    async def capture(event, body, rooms):
        sent.append(body)

    monkeypatch.setattr(events, "emit_to_rooms", capture)
    entry_id, owner = await _taking(client, catalog, leo)
    for tube in await _tubes(client, entry_id):
        await client.post(f"{API}/orders/samples/{tube['id']}/collect")
    await events.drain()
    assert sent
    dump = json.dumps(sent)
    assert str(owner.id) not in dump and "Tecnica A" not in dump
    for body in sent:
        assert not any("user" in k or "actor" in k or "by" in k for k in body)


# --- Tubos -------------------------------------------------------------------------------


async def test_collect_and_uncollect_write_and_clear_the_user_id(
    client, catalog, leo: FakeLeo
) -> None:
    entry_id, owner = await _taking(client, catalog, leo)
    tube = (await _tubes(client, entry_id))[0]
    done = (await client.post(f"{API}/orders/samples/{tube['id']}/collect")).json()
    assert done["collected_by"] == "Tecnica A"
    assert done["collected_by_user_id"] == str(owner.id)
    undone = (await client.post(f"{API}/orders/samples/{tube['id']}/uncollect")).json()
    assert undone["collected_by"] is None
    assert undone["collected_by_user_id"] is None


async def test_receive_and_unreceive_write_and_clear_the_user_id(
    client, catalog, leo: FakeLeo
) -> None:
    entry_id, _ = await _taking(client, catalog, leo)
    tubes = await _tubes(client, entry_id)
    for tube in tubes:
        await client.post(f"{API}/orders/samples/{tube['id']}/collect")
    checks = (await client.get(f"{API}/orders/by-entry/{entry_id}")).json()
    await client.post(
        f"{API}/orders/by-entry/{entry_id}/precondition-checks",
        json={
            "stage": "sampling",
            "checks": [{"key": c["key"], "met": True} for c in checks["preconditions"]],
        },
    )
    assert (
        await client.post(f"{API}/queue/{entry_id}/finish-sampling")
    ).status_code == 200
    lab = _as(leo, "Laura Lab")
    received = (
        await client.post(f"{API}/orders/samples/{tubes[0]['id']}/receive")
    ).json()
    assert received["received_by"] == "Laura Lab"
    assert received["received_by_user_id"] == str(lab.id)
    lab_queue = (await client.get(f"{API}/lab/reception")).json()
    shown = next(
        s for o in lab_queue for s in o["samples"] if s["id"] == tubes[0]["id"]
    )
    assert shown["received_by_user_id"] == str(lab.id)
    undone = (
        await client.post(f"{API}/orders/samples/{tubes[0]['id']}/unreceive")
    ).json()
    assert undone["received_by"] is None and undone["received_by_user_id"] is None


async def test_precondition_checks_record_who_verified_each_stage(
    client, catalog, leo: FakeLeo, session
) -> None:
    entry_id, _ = await _printed(client, catalog)
    sampler = _as(leo, "Tecnica A")
    await _claim(client, entry_id)
    detail = (await client.get(f"{API}/orders/by-entry/{entry_id}")).json()
    await client.post(
        f"{API}/orders/by-entry/{entry_id}/precondition-checks",
        json={
            "stage": "sampling",
            "checks": [{"key": c["key"], "met": True} for c in detail["preconditions"]],
        },
    )
    rows = (
        (
            await session.execute(
                select(OrderPrecondition).where(
                    OrderPrecondition.key.in_(
                        [c["key"] for c in detail["preconditions"]]
                    )
                )
            )
        )
        .scalars()
        .all()
    )
    assert rows
    for row in rows:
        assert row.sampling_checked_by_user_id == sampler.id
        assert row.sampling_checked_by == "Tecnica A"
        assert row.reception_checked_by_user_id is not None  # quien cerro recepcion


# --- Resultados ---------------------------------------------------------------------------


async def test_results_record_who_typed_and_who_ran_the_validation(
    client, catalog, leo: FakeLeo, session
) -> None:
    await order_in_laboratory(client, catalog)
    analyst = _as(leo, "Quimico Uno", ALL)
    queue = (
        await client.get(f"{API}/results/queue", params={"professional_id": "staff-qc"})
    ).json()
    test_id = next(
        t["order_test_id"] for o in queue for t in o["tests"] if t["code"] == "GLU"
    )
    body = {
        "professional_id": "staff-qc",
        "professional_name": "Quimica Responsable",
        "values": {"GLU": "90"},
    }
    await client.put(f"{API}/results/tests/{test_id}/values", json=body)
    result = (
        await session.execute(
            select(OrderResult).where(OrderResult.analyte_code == "GLU")
        )
    ).scalar_one()
    assert result.entered_by_user_id == analyst.id
    validator = _as(leo, "Quimico Dos", ALL)
    done = await client.post(f"{API}/results/tests/{test_id}/validate", json=body)
    assert done.status_code == 200, done.text
    test = await session.get(OrderTest, UUID(test_id))
    await session.refresh(test)
    assert test.validated_by_user_id == validator.id
    assert test.validated_by_id == "staff-qc"  # el profesional que firma, intacto
    assert test.validated_by_name == "Quimica Responsable"


# --- Propiedad del turno -----------------------------------------------------------------------


async def test_the_owner_can_mark_finish_and_return_their_turn(
    client, catalog, leo: FakeLeo
) -> None:
    entry_id, _ = await _taking(client, catalog, leo)
    tubes = await _tubes(client, entry_id)
    for tube in tubes:
        assert (
            await client.post(f"{API}/orders/samples/{tube['id']}/collect")
        ).status_code == 200
    detail = (await client.get(f"{API}/orders/by-entry/{entry_id}")).json()
    await client.post(
        f"{API}/orders/by-entry/{entry_id}/precondition-checks",
        json={
            "stage": "sampling",
            "checks": [{"key": c["key"], "met": True} for c in detail["preconditions"]],
        },
    )
    assert (
        await client.post(f"{API}/queue/{entry_id}/finish-sampling")
    ).status_code == 200


async def test_the_owner_can_return_their_turn(client, catalog, leo: FakeLeo) -> None:
    entry_id, _ = await _taking(client, catalog, leo)
    reasons = (await client.get(f"{API}/return-reasons")).json()
    response = await client.post(
        f"{API}/queue/{entry_id}/return", json={"reason_id": reasons[0]["id"]}
    )
    assert response.status_code == 200, response.text


async def test_another_technician_cannot_mark_a_tube(
    client, catalog, leo: FakeLeo
) -> None:
    entry_id, _ = await _taking(client, catalog, leo)
    tube = (await _tubes(client, entry_id))[0]
    await client.post(f"{API}/orders/samples/{tube['id']}/collect")
    _as(leo, "Tecnica B")
    leo.events.clear()
    for action in ("collect", "uncollect"):
        response = await client.post(f"{API}/orders/samples/{tube['id']}/{action}")
        _assert_not_owner(response, "Tecnica A")
    assert _denied(leo) == [p.SAM_COLLECT, p.SAM_COLLECT]
    again = (await _tubes(client, entry_id))[0]
    assert again["collected_by"] == "Tecnica A"  # nada cambio


async def test_another_technician_cannot_finish_or_return_the_turn(
    client, catalog, leo: FakeLeo
) -> None:
    entry_id, _ = await _taking(client, catalog, leo)
    _as(leo, "Tecnica B")
    leo.events.clear()
    finish = await client.post(f"{API}/queue/{entry_id}/finish-sampling")
    _assert_not_owner(finish, "Tecnica A")
    reasons = (await client.get(f"{API}/return-reasons")).json()
    back = await client.post(
        f"{API}/queue/{entry_id}/return", json={"reason_id": reasons[0]["id"]}
    )
    _assert_not_owner(back, "Tecnica A")
    assert _denied(leo) == [p.SAM_FINISH, p.SAM_RETURN]
    entry = (await client.get(f"{API}/queue/{entry_id}")).json()
    assert entry["status"] == "en_atencion_toma_muestras"
    assert entry["claimed_by"] == "Tecnica A"


async def test_a_supervisor_can_act_on_other_technicians_turns(
    client, catalog, leo: FakeLeo
) -> None:
    entry_id, _ = await _taking(client, catalog, leo)
    _as(leo, "Supervisora", ALL)
    tubes = await _tubes(client, entry_id)
    for tube in tubes:
        assert (
            await client.post(f"{API}/orders/samples/{tube['id']}/collect")
        ).status_code == 200
    assert (
        await client.post(f"{API}/orders/samples/{tubes[0]['id']}/uncollect")
    ).status_code == 200
    reasons = (await client.get(f"{API}/return-reasons")).json()
    back = await client.post(
        f"{API}/queue/{entry_id}/return", json={"reason_id": reasons[0]["id"]}
    )
    assert back.status_code == 200, back.text


async def test_a_turn_taken_before_user_ids_has_an_unknown_owner_and_is_allowed(
    client, catalog, leo: FakeLeo, session
) -> None:
    entry_id, _ = await _taking(client, catalog, leo)
    await session.execute(
        text("UPDATE queue_entries SET claimed_by_user_id = NULL WHERE id = :i"),
        {"i": entry_id},
    )
    _as(leo, "Tecnica B")
    tube = (await _tubes(client, entry_id))[0]
    response = await client.post(f"{API}/orders/samples/{tube['id']}/collect")
    assert response.status_code == 200, response.text
    assert response.json()["collected_by_user_id"] is not None


async def test_two_people_cannot_take_the_same_sampling_turn(
    client, catalog, leo: FakeLeo
) -> None:
    entry_id, _ = await _printed(client, catalog)
    _as(leo, "Tecnica A")
    await _claim(client, entry_id)
    _as(leo, "Tecnica B")
    second = await client.post(
        f"{API}/queue/{entry_id}/claim", json={"professional_id": "staff-1"}
    )
    assert second.status_code == 409, second.text
    entry = await session_entry(client, entry_id)
    assert entry["claimed_by"] == "Tecnica A"


async def session_entry(client, entry_id):
    return (await client.get(f"{API}/queue/{entry_id}")).json()
