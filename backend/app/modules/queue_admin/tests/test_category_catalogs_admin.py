"""Administracion de los catalogos de categoria (tipos de sangre, estados de la
cola, marcas de resultado...): se editan nombre y presentacion; sus codigos son de
sistema, asi que no hay altas ni desactivacion."""

import pytest

from app.conftest import FakeLeo
from app.core import permissions

API = "/api/v1/queue-admin"
CLOSED = [
    "blood-types",
    "queue-statuses",
    "queue-transition-kinds",
    "validation-statuses",
    "result-flags",
    "trace-steps",
]


async def _by_code(client, kind, code):
    page = (await client.get(f"{API}/{kind}?q={code}&page_size=100")).json()
    return next(item for item in page["items"] if item["code"] == code)


@pytest.mark.parametrize("kind", CLOSED)
async def test_lists_in_presentation_order(client, kind) -> None:
    page = (await client.get(f"{API}/{kind}?page_size=100")).json()
    orders = [item["sort_order"] for item in page["items"]]
    assert page["total"] > 0 and orders == sorted(orders)


async def test_flags_expose_their_behaviour_columns(client) -> None:
    flag = await _by_code(client, "result-flags", "critical_low")
    assert flag["variant"] == "danger" and flag["show_in_report"] is True
    status = await _by_code(client, "queue-statuses", "finalizada")
    assert status["is_terminal"] is True
    step = await _by_code(client, "trace-steps", "queue.entered")
    assert step["category"] == "queue"


async def test_update_name_and_order_with_audit(client, leo: FakeLeo) -> None:
    status = await _by_code(client, "queue-statuses", "en_laboratorio")
    res = await client.patch(
        f"{API}/queue-statuses/{status['id']}",
        json={"name": "En el laboratorio", "sort_order": 70, "reason": "texto"},
    )
    assert res.status_code == 200, res.text
    assert (res.json()["name"], res.json()["sort_order"]) == ("En el laboratorio", 70)
    [event] = [
        e
        for e in leo.events
        if e["action_tag"] == permissions.QAD_UPDATE and e["result"] == "ok"
    ]
    assert event["entity_type"] == "queue_status"
    assert event["changes"]["sort_order"]["after"] == 70


async def test_update_flag_presentation(client) -> None:
    flag = await _by_code(client, "result-flags", "abnormal")
    res = await client.patch(
        f"{API}/result-flags/{flag['id']}",
        json={"variant": "danger", "show_in_report": False},
    )
    assert res.status_code == 200, res.text
    assert res.json()["variant"] == "danger" and res.json()["show_in_report"] is False
    # y el informe lo refleja
    labels = (await client.get("/api/v1/catalogs/result-flags")).json()
    assert next(i for i in labels if i["code"] == "abnormal")["show_in_report"] is False


@pytest.mark.parametrize(
    ("body", "field"),
    [
        ({"variant": "rojo"}, "variant"),
        ({"sort_order": -1}, "sort_order"),
        ({"show_in_report": None}, "show_in_report"),
        ({"name": "  "}, "name"),
    ],
)
async def test_update_validations_422(client, body, field) -> None:
    flag = await _by_code(client, "result-flags", "low")
    res = await client.patch(f"{API}/result-flags/{flag['id']}", json=body)
    assert res.status_code == 422
    assert res.json()["details"]["field"] == field


async def test_fields_the_catalog_does_not_allow_are_rejected(client) -> None:
    status = await _by_code(client, "queue-statuses", "retirado")
    res = await client.patch(
        f"{API}/queue-statuses/{status['id']}", json={"variant": "danger"}
    )
    assert res.status_code == 422
    blood = await _by_code(client, "blood-types", "O+")
    res = await client.patch(f"{API}/blood-types/{blood['id']}", json={"rank": 3})
    assert res.status_code == 422


async def test_priorities_do_not_take_category_fields(client) -> None:
    baja = (await client.get(f"{API}/priorities?q=baja")).json()["items"][0]
    res = await client.patch(f"{API}/priorities/{baja['id']}", json={"sort_order": 1})
    assert res.status_code == 422


@pytest.mark.parametrize("kind", CLOSED)
async def test_no_creation_and_no_deactivation(client, kind) -> None:
    created = await client.post(
        f"{API}/{kind}", json={"code": "nuevo", "name": "Nuevo"}
    )
    assert created.status_code == 409
    item = (await client.get(f"{API}/{kind}?page_size=1")).json()["items"][0]
    off = await client.post(
        f"{API}/{kind}/{item['id']}/deactivate", json={"reason": "x"}
    )
    assert off.status_code == 409
