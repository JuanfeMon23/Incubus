"""Administracion de catalogos de la cola: CRUD, reglas y selectores."""

import pytest

from app.conftest import FakeLeo
from app.core import permissions as p

A = "/api/v1/queue-admin"
PRIO = {"code": "urgente-vital", "name": "Urgencia vital", "color_hex": "#112233"}


async def _by_code(client, kind, code):
    page = (await client.get(f"{A}/{kind}?q={code}&page_size=100")).json()
    return next(i for i in page["items"] if i["code"] == code)


def _audit(leo: FakeLeo, tag: str) -> list[dict]:
    return [e for e in leo.events if e["action_tag"] == tag and e["result"] == "ok"]


# --- Listado -----------------------------------------------------------------------


async def test_list_is_paginated_searchable_and_filters_active(client) -> None:
    page = (await client.get(f"{A}/priorities?page_size=2")).json()
    assert page["total"] == 4 and page["page"] == 1 and page["page_size"] == 2
    assert [i["rank"] for i in page["items"]] == [1, 2]
    assert page["items"][0]["color_hex"] == "#DC2626"
    page2 = (await client.get(f"{A}/priorities?page_size=2&page=2")).json()
    assert [i["rank"] for i in page2["items"]] == [3, 4]
    found = (await client.get(f"{A}/priorities?q=ALT")).json()
    assert [i["code"] for i in found["items"]] == ["alta"]
    assert (await client.get(f"{A}/priorities?q=%25")).json()["total"] == 0
    otro = await _by_code(client, "removal-reasons", "otro")
    assert otro["color_hex"] is None and otro["rank"] is None
    await client.post(
        f"{A}/removal-reasons/{otro['id']}/deactivate", json={"reason": "x"}
    )
    inactive = (await client.get(f"{A}/removal-reasons?is_active=false")).json()
    assert [i["code"] for i in inactive["items"]] == ["otro"]
    active = (await client.get(f"{A}/removal-reasons?is_active=true")).json()
    assert active["total"] == 4


async def test_get_one_and_404(client) -> None:
    media = await _by_code(client, "priorities", "media")
    assert (await client.get(f"{A}/priorities/{media['id']}")).json()["code"] == "media"
    r = await client.get(f"{A}/priorities/00000000-0000-0000-0000-000000000000")
    assert r.status_code == 404 and set(r.json()) == {"code", "message", "details"}


# --- Crear ---------------------------------------------------------------------------


async def test_create_priority_and_audit(client, leo: FakeLeo) -> None:
    r = await client.post(f"{A}/priorities", json={**PRIO, "rank": 10})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["is_active"] is True and body["rank"] == 10
    [event] = _audit(leo, p.QAD_CREATE)
    assert event["entity_type"] == "priority" and event["entity_id"] == body["id"]


async def test_create_reason(client) -> None:
    r = await client.post(
        f"{A}/return-reasons", json={"code": "firma-faltante", "name": "Falta firma"}
    )
    assert r.status_code == 201 and r.json()["rank"] is None


@pytest.mark.parametrize(
    ("patch", "field"),
    [
        ({"code": "Mayus"}, "code"),
        ({"code": "con espacio"}, "code"),
        ({"code": "-x"}, "code"),
        ({"name": "   "}, "name"),
        ({"color_hex": "red"}, "color_hex"),
        ({"color_hex": "#12345"}, "color_hex"),
        ({"color_hex": None}, "color_hex"),
        ({"rank": 0}, "rank"),
        ({"rank": None}, "rank"),
    ],
)
async def test_create_priority_validations_422(client, patch, field) -> None:
    r = await client.post(f"{A}/priorities", json={**PRIO, "rank": 10, **patch})
    assert r.status_code == 422, r.text
    assert r.json()["details"]["field"] == field
    assert r.json()["code"] == "validation_error"


async def test_create_reason_rejects_style_fields(client) -> None:
    r = await client.post(
        f"{A}/removal-reasons", json={"code": "x1", "name": "X", "rank": 1}
    )
    assert r.status_code == 422


@pytest.mark.parametrize(
    ("patch", "field"),
    [
        ({"code": "alta"}, "code"),
        ({"name": "  prioridad ALTA "}, "name"),  # sin distinguir mayusculas
        ({"rank": 2}, "rank"),
    ],
)
async def test_create_priority_uniqueness_409(client, patch, field) -> None:
    r = await client.post(f"{A}/priorities", json={**PRIO, "rank": 10, **patch})
    assert r.status_code == 409, r.text
    assert r.json()["details"]["field"] == field


async def test_unique_also_against_inactive_rows(client) -> None:
    otro = await _by_code(client, "removal-reasons", "otro")
    await client.post(
        f"{A}/removal-reasons/{otro['id']}/deactivate", json={"reason": "x"}
    )
    r = await client.post(
        f"{A}/removal-reasons", json={"code": "otro", "name": "Nuevo"}
    )
    assert r.status_code == 409


# --- Editar ----------------------------------------------------------------------------


async def test_update_priority_with_before_after_audit(client, leo: FakeLeo) -> None:
    baja = await _by_code(client, "priorities", "baja")
    r = await client.patch(
        f"{A}/priorities/{baja['id']}",
        json={
            "name": "Baja demora",
            "color_hex": "#00ff00",
            "rank": 9,
            "reason": "ajuste",
        },
    )
    assert r.status_code == 200, r.text
    assert (r.json()["name"], r.json()["color_hex"], r.json()["rank"]) == (
        "Baja demora",
        "#00FF00",
        9,
    )
    [event] = _audit(leo, p.QAD_UPDATE)
    assert event["reason"] == "ajuste"
    assert event["changes"]["rank"] == {"before": 4, "after": 9}


async def test_update_conflicts_and_validations(client) -> None:
    baja = await _by_code(client, "priorities", "baja")
    url = f"{A}/priorities/{baja['id']}"
    assert (await client.patch(url, json={"rank": 1})).status_code == 409
    assert (await client.patch(url, json={"name": "Prioridad alta"})).status_code == 409
    assert (await client.patch(url, json={"rank": 0})).status_code == 422
    assert (await client.patch(url, json={})).status_code == 422
    assert (await client.patch(url, json={"code": "nueva"})).status_code == 422
    same = await client.patch(url, json={"rank": 4})  # sin cambios reales: ok
    assert same.status_code == 200


async def test_reorder_by_changing_rank(client) -> None:
    baja = await _by_code(client, "priorities", "baja")
    assert (
        await client.patch(f"{A}/priorities/{baja['id']}", json={"rank": 5})
    ).status_code == 200
    extrema = await _by_code(client, "priorities", "extrema")
    assert (
        await client.patch(f"{A}/priorities/{extrema['id']}", json={"rank": 4})
    ).status_code == 200
    ranks = [i["rank"] for i in (await client.get(f"{A}/priorities")).json()["items"]]
    assert ranks == sorted(ranks)


async def test_update_reason_name_and_reject_color(client) -> None:
    otro = await _by_code(client, "return-reasons", "otro")
    url = f"{A}/return-reasons/{otro['id']}"
    assert (await client.patch(url, json={"name": "Otro motivo"})).json()[
        "name"
    ] == "Otro motivo"
    assert (await client.patch(url, json={"color_hex": "#000000"})).status_code == 422


# --- Activar / desactivar -------------------------------------------------------------


async def test_toggle_audit_and_requires_reason_to_deactivate(client, leo) -> None:
    alta = await _by_code(client, "priorities", "alta")
    url = f"{A}/priorities/{alta['id']}"
    assert (await client.post(f"{url}/deactivate", json={})).status_code == 422
    r = await client.post(f"{url}/deactivate", json={"reason": "ya no se usa"})
    assert r.status_code == 200 and r.json()["is_active"] is False
    [event] = _audit(leo, p.QAD_TOGGLE)
    assert event["reason"] == "ya no se usa"
    assert event["changes"]["is_active"] == {"before": True, "after": False}
    assert (
        await client.post(f"{url}/deactivate", json={"reason": "x"})
    ).status_code == 409
    back = await client.post(f"{url}/activate")  # sin cuerpo
    assert back.status_code == 200 and back.json()["is_active"] is True
    assert (await client.post(f"{url}/activate")).status_code == 409


async def test_default_priority_cannot_be_deactivated(client) -> None:
    media = await _by_code(client, "priorities", "media")
    r = await client.post(
        f"{A}/priorities/{media['id']}/deactivate", json={"reason": "x"}
    )
    assert r.status_code == 409
    assert "por defecto" in r.json()["message"]


async def test_last_active_priority_cannot_be_deactivated(client, session) -> None:
    from sqlalchemy import update

    from app.modules.queue.models import Priority

    await session.execute(
        update(Priority).where(Priority.code != "baja").values(is_active=False)
    )
    baja = await _by_code(client, "priorities", "baja")
    r = await client.post(
        f"{A}/priorities/{baja['id']}/deactivate", json={"reason": "x"}
    )
    assert r.status_code == 409
    assert "al menos una" in r.json()["message"]


# --- Selectores y turnos existentes ------------------------------------------------


async def test_selectors_list_only_active_and_new_items_show_up(client) -> None:
    alta = await _by_code(client, "priorities", "alta")
    otro = await _by_code(client, "removal-reasons", "otro")
    devol = await _by_code(client, "return-reasons", "otro")
    await client.post(f"{A}/priorities/{alta['id']}/deactivate", json={"reason": "x"})
    await client.post(
        f"{A}/removal-reasons/{otro['id']}/deactivate", json={"reason": "x"}
    )
    await client.post(
        f"{A}/return-reasons/{devol['id']}/deactivate", json={"reason": "x"}
    )
    created = await client.post(f"{A}/priorities", json={**PRIO, "rank": 10})
    prios = (await client.get("/api/v1/priorities")).json()
    codes = [i["code"] for i in prios]
    assert "alta" not in codes and PRIO["code"] in codes
    assert "otro" not in [
        i["code"] for i in (await client.get("/api/v1/removal-reasons")).json()
    ]
    assert "otro" not in [
        i["code"] for i in (await client.get("/api/v1/return-reasons")).json()
    ]
    # y no se puede ingresar con una prioridad inactiva
    r = await client.post(
        "/api/v1/queue",
        json={
            "patient": {
                "document_number": "5550001",
                "first_name": "A",
                "first_last_name": "B",
            },
            "priority_id": alta["id"],
        },
    )
    assert r.status_code == 422
    assert created.status_code == 201


async def test_existing_turns_keep_showing_an_inactive_priority(client) -> None:
    alta = await _by_code(client, "priorities", "alta")
    entry = await client.post(
        "/api/v1/queue",
        json={
            "patient": {
                "document_number": "5550002",
                "first_name": "A",
                "first_last_name": "B",
            },
            "priority_id": alta["id"],
        },
    )
    assert entry.status_code == 201, entry.text
    await client.post(f"{A}/priorities/{alta['id']}/deactivate", json={"reason": "x"})
    shown = (await client.get(f"/api/v1/queue/{entry.json()['id']}")).json()["priority"]
    assert shown["code"] == "alta"
