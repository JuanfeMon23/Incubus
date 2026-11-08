"""Administracion de catalogos de la cola: CRUD, reglas y selectores."""

import pytest
from sqlalchemy import select

from app.conftest import FakeLeo
from app.core import permissions

QUEUE_ADMIN_API = "/api/v1/queue-admin"
PRIO = {"code": "urgente-vital", "name": "Urgencia vital", "color_hex": "#112233"}


async def _by_code(client, kind, code):
    page = (await client.get(f"{QUEUE_ADMIN_API}/{kind}?q={code}&page_size=100")).json()
    return next(i for i in page["items"] if i["code"] == code)


def _audit(leo: FakeLeo, tag: str) -> list[dict]:
    return [
        event
        for event in leo.events
        if event["action_tag"] == tag and event["result"] == "ok"
    ]


# --- Listado -----------------------------------------------------------------------


async def test_list_is_paginated_searchable_and_filters_active(client) -> None:
    page = (await client.get(f"{QUEUE_ADMIN_API}/priorities?page_size=2")).json()
    assert page["total"] == 4 and page["page"] == 1 and page["page_size"] == 2
    assert [i["rank"] for i in page["items"]] == [1, 2]
    assert page["items"][0]["color_hex"] == "#DC2626"
    page2 = (
        await client.get(f"{QUEUE_ADMIN_API}/priorities?page_size=2&page=2")
    ).json()
    assert [i["rank"] for i in page2["items"]] == [3, 4]
    found = (await client.get(f"{QUEUE_ADMIN_API}/priorities?q=ALT")).json()
    assert [i["code"] for i in found["items"]] == ["alta"]
    assert (await client.get(f"{QUEUE_ADMIN_API}/priorities?q=%25")).json()[
        "total"
    ] == 0
    otro = await _by_code(client, "removal-reasons", "otro")
    assert otro["color_hex"] is None and otro["rank"] is None
    await client.post(
        f"{QUEUE_ADMIN_API}/removal-reasons/{otro['id']}/deactivate",
        json={"reason": "x"},
    )
    inactive = (
        await client.get(f"{QUEUE_ADMIN_API}/removal-reasons?is_active=false")
    ).json()
    assert [i["code"] for i in inactive["items"]] == ["otro"]
    active = (
        await client.get(f"{QUEUE_ADMIN_API}/removal-reasons?is_active=true")
    ).json()
    assert active["total"] == 4


async def test_get_one_and_404(client) -> None:
    media = await _by_code(client, "priorities", "media")
    assert (await client.get(f"{QUEUE_ADMIN_API}/priorities/{media['id']}")).json()[
        "code"
    ] == "media"
    response = await client.get(
        f"{QUEUE_ADMIN_API}/priorities/00000000-0000-0000-0000-000000000000"
    )
    assert response.status_code == 404 and set(response.json()) == {
        "code",
        "message",
        "details",
    }


# --- Crear ---------------------------------------------------------------------------


async def test_create_priority_and_audit(client, leo: FakeLeo) -> None:
    response = await client.post(
        f"{QUEUE_ADMIN_API}/priorities", json={**PRIO, "rank": 10}
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["is_active"] is True and body["rank"] == 10
    [event] = _audit(leo, permissions.QAD_CREATE)
    assert event["entity_type"] == "priority" and event["entity_id"] == body["id"]


async def test_create_reason(client) -> None:
    response = await client.post(
        f"{QUEUE_ADMIN_API}/return-reasons",
        json={"code": "firma-faltante", "name": "Falta firma"},
    )
    assert response.status_code == 201 and response.json()["rank"] is None


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
    response = await client.post(
        f"{QUEUE_ADMIN_API}/priorities", json={**PRIO, "rank": 10, **patch}
    )
    assert response.status_code == 422, response.text
    assert response.json()["details"]["field"] == field
    assert response.json()["code"] == "validation_error"


async def test_create_reason_rejects_style_fields(client) -> None:
    response = await client.post(
        f"{QUEUE_ADMIN_API}/removal-reasons",
        json={"code": "x1", "name": "X", "rank": 1},
    )
    assert response.status_code == 422


@pytest.mark.parametrize(
    ("patch", "field"),
    [
        ({"code": "alta"}, "code"),
        ({"name": "  prioridad ALTA "}, "name"),  # sin distinguir mayusculas
        ({"rank": 2}, "rank"),
    ],
)
async def test_create_priority_uniqueness_409(client, patch, field) -> None:
    response = await client.post(
        f"{QUEUE_ADMIN_API}/priorities", json={**PRIO, "rank": 10, **patch}
    )
    assert response.status_code == 409, response.text
    assert response.json()["details"]["field"] == field


async def test_unique_also_against_inactive_rows(client) -> None:
    otro = await _by_code(client, "removal-reasons", "otro")
    await client.post(
        f"{QUEUE_ADMIN_API}/removal-reasons/{otro['id']}/deactivate",
        json={"reason": "x"},
    )
    response = await client.post(
        f"{QUEUE_ADMIN_API}/removal-reasons", json={"code": "otro", "name": "Nuevo"}
    )
    assert response.status_code == 409


# --- Editar ----------------------------------------------------------------------------


async def test_update_priority_with_before_after_audit(client, leo: FakeLeo) -> None:
    baja = await _by_code(client, "priorities", "baja")
    response = await client.patch(
        f"{QUEUE_ADMIN_API}/priorities/{baja['id']}",
        json={
            "name": "Baja demora",
            "color_hex": "#00ff00",
            "rank": 9,
            "reason": "ajuste",
        },
    )
    assert response.status_code == 200, response.text
    assert (
        response.json()["name"],
        response.json()["color_hex"],
        response.json()["rank"],
    ) == (
        "Baja demora",
        "#00FF00",
        9,
    )
    [event] = _audit(leo, permissions.QAD_UPDATE)
    assert event["reason"] == "ajuste"
    assert event["changes"]["rank"] == {"before": 4, "after": 9}


async def test_update_conflicts_and_validations(client) -> None:
    baja = await _by_code(client, "priorities", "baja")
    url = f"{QUEUE_ADMIN_API}/priorities/{baja['id']}"
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
        await client.patch(
            f"{QUEUE_ADMIN_API}/priorities/{baja['id']}", json={"rank": 5}
        )
    ).status_code == 200
    extrema = await _by_code(client, "priorities", "extrema")
    assert (
        await client.patch(
            f"{QUEUE_ADMIN_API}/priorities/{extrema['id']}", json={"rank": 4}
        )
    ).status_code == 200
    ranks = [
        i["rank"]
        for i in (await client.get(f"{QUEUE_ADMIN_API}/priorities")).json()["items"]
    ]
    assert ranks == sorted(ranks)


async def test_update_reason_name_and_reject_color(client) -> None:
    otro = await _by_code(client, "return-reasons", "otro")
    url = f"{QUEUE_ADMIN_API}/return-reasons/{otro['id']}"
    assert (await client.patch(url, json={"name": "Otro motivo"})).json()[
        "name"
    ] == "Otro motivo"
    assert (await client.patch(url, json={"color_hex": "#000000"})).status_code == 422


# --- Activar / desactivar -------------------------------------------------------------


async def test_toggle_audit_and_requires_reason_to_deactivate(client, leo) -> None:
    alta = await _by_code(client, "priorities", "alta")
    url = f"{QUEUE_ADMIN_API}/priorities/{alta['id']}"
    assert (await client.post(f"{url}/deactivate", json={})).status_code == 422
    response = await client.post(f"{url}/deactivate", json={"reason": "ya no se usa"})
    assert response.status_code == 200 and response.json()["is_active"] is False
    [event] = _audit(leo, permissions.QAD_TOGGLE)
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
    response = await client.post(
        f"{QUEUE_ADMIN_API}/priorities/{media['id']}/deactivate", json={"reason": "x"}
    )
    assert response.status_code == 409
    assert "por defecto" in response.json()["message"]


async def test_last_active_priority_cannot_be_deactivated(client, session) -> None:
    from sqlalchemy import update

    from app.modules.queue.models import Priority

    await session.execute(
        update(Priority).where(Priority.code != "baja").values(is_active=False)
    )
    baja = await _by_code(client, "priorities", "baja")
    response = await client.post(
        f"{QUEUE_ADMIN_API}/priorities/{baja['id']}/deactivate", json={"reason": "x"}
    )
    assert response.status_code == 409
    assert "al menos una" in response.json()["message"]


# --- Prioridad por defecto --------------------------------------------------------


async def _default_codes(client) -> list[str]:
    page = (await client.get(f"{QUEUE_ADMIN_API}/priorities?page_size=100")).json()
    return [i["code"] for i in page["items"] if i["is_default"]]


async def test_backfill_leaves_media_as_the_only_default(client) -> None:
    assert await _default_codes(client) == ["media"]
    # los motivos no tienen el campo
    otro = await _by_code(client, "removal-reasons", "otro")
    assert otro["is_default"] is None


async def test_set_default_switches_atomically_and_audits(client, leo) -> None:
    alta = await _by_code(client, "priorities", "alta")
    media = await _by_code(client, "priorities", "media")
    response = await client.post(
        f"{QUEUE_ADMIN_API}/priorities/{alta['id']}/set-default",
        json={"reason": "demanda"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["is_default"] is True
    assert await _default_codes(client) == ["alta"]
    events = _audit(leo, permissions.QAD_UPDATE)
    assert {
        (event["entity_id"], event["changes"]["is_default"]["after"])
        for event in events
    } == {
        (alta["id"], True),
        (media["id"], False),
    }
    assert {event["reason"] for event in events} == {"demanda"}
    # la anterior ya se puede desactivar; la nueva no
    assert (
        await client.post(
            f"{QUEUE_ADMIN_API}/priorities/{media['id']}/deactivate",
            json={"reason": "x"},
        )
    ).status_code == 200
    blocked = await client.post(
        f"{QUEUE_ADMIN_API}/priorities/{alta['id']}/deactivate", json={"reason": "x"}
    )
    assert blocked.status_code == 409 and "por defecto" in blocked.json()["message"]


async def test_set_default_requires_an_active_priority(client) -> None:
    baja = await _by_code(client, "priorities", "baja")
    await client.post(
        f"{QUEUE_ADMIN_API}/priorities/{baja['id']}/deactivate", json={"reason": "x"}
    )
    response = await client.post(
        f"{QUEUE_ADMIN_API}/priorities/{baja['id']}/set-default"
    )  # sin cuerpo
    assert response.status_code == 409 and "activa" in response.json()["message"]
    assert await _default_codes(client) == ["media"]


async def test_set_default_on_the_current_default_is_a_conflict(client) -> None:
    media = await _by_code(client, "priorities", "media")
    response = await client.post(
        f"{QUEUE_ADMIN_API}/priorities/{media['id']}/set-default"
    )
    assert response.status_code == 409
    assert await _default_codes(client) == ["media"]


async def test_set_default_unknown_id_is_404(client) -> None:
    response = await client.post(
        f"{QUEUE_ADMIN_API}/priorities/00000000-0000-0000-0000-000000000000/set-default"
    )
    assert response.status_code == 404


async def test_the_database_allows_only_one_default(session) -> None:
    from sqlalchemy.exc import IntegrityError

    from app.modules.queue.models import Priority

    row = (
        await session.execute(select(Priority).where(Priority.code == "alta"))
    ).scalar_one()
    with pytest.raises(IntegrityError):
        async with session.begin_nested():
            row.is_default = True
            await session.flush()


async def test_new_priorities_are_not_default_and_cannot_be_edited_into_it(
    client,
) -> None:
    created = (
        await client.post(f"{QUEUE_ADMIN_API}/priorities", json={**PRIO, "rank": 10})
    ).json()
    assert created["is_default"] is False
    assert await _default_codes(client) == ["media"]
    response = await client.patch(
        f"{QUEUE_ADMIN_API}/priorities/{created['id']}", json={"is_default": True}
    )
    assert response.status_code == 422  # solo se cambia con la accion dedicada


async def test_public_selector_exposes_is_default(client) -> None:
    prios = (await client.get("/api/v1/priorities")).json()
    assert [(i["code"], i["is_default"]) for i in prios] == [
        ("extrema", False),
        ("alta", False),
        ("media", True),
        ("baja", False),
    ]
    alta = await _by_code(client, "priorities", "alta")
    await client.post(f"{QUEUE_ADMIN_API}/priorities/{alta['id']}/set-default")
    prios = (await client.get("/api/v1/priorities")).json()
    assert [i["code"] for i in prios if i["is_default"]] == ["alta"]


async def test_set_default_concurrent_requests_leave_exactly_one(
    committed_client,
) -> None:
    import asyncio

    client = committed_client
    ids = {
        code: (await _by_code(client, "priorities", code))["id"]
        for code in ("alta", "baja")
    }
    try:
        results = await asyncio.gather(
            *(
                client.post(f"{QUEUE_ADMIN_API}/priorities/{i}/set-default")
                for i in ids.values()
            )
        )
        assert sorted(result.status_code for result in results) == [200, 200]
        assert len(await _default_codes(client)) == 1
    finally:
        media = await _by_code(client, "priorities", "media")
        await client.post(f"{QUEUE_ADMIN_API}/priorities/{media['id']}/set-default")


# --- Selectores y turnos existentes ------------------------------------------------


async def test_selectors_list_only_active_and_new_items_show_up(client) -> None:
    alta = await _by_code(client, "priorities", "alta")
    otro = await _by_code(client, "removal-reasons", "otro")
    devol = await _by_code(client, "return-reasons", "otro")
    await client.post(
        f"{QUEUE_ADMIN_API}/priorities/{alta['id']}/deactivate", json={"reason": "x"}
    )
    await client.post(
        f"{QUEUE_ADMIN_API}/removal-reasons/{otro['id']}/deactivate",
        json={"reason": "x"},
    )
    await client.post(
        f"{QUEUE_ADMIN_API}/return-reasons/{devol['id']}/deactivate",
        json={"reason": "x"},
    )
    created = await client.post(
        f"{QUEUE_ADMIN_API}/priorities", json={**PRIO, "rank": 10}
    )
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
    response = await client.post(
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
    assert response.status_code == 422
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
    await client.post(
        f"{QUEUE_ADMIN_API}/priorities/{alta['id']}/deactivate", json={"reason": "x"}
    )
    shown = (await client.get(f"/api/v1/queue/{entry.json()['id']}")).json()["priority"]
    assert shown["code"] == "alta"
