"""`GET /api/v1/catalogs/{slug}`: catalogos propios de Incubus y proxy de los de
Vladimir (sexos) y Leo (tipos de documento)."""

from uuid import UUID

import pytest
from httpx import AsyncClient
from leo_sdk import LeoUser

from app.conftest import FakeLeo, make_leo_user
from app.core import permissions

API = "/api/v1/catalogs"


async def test_blood_types_are_listed_in_order(client: AsyncClient) -> None:
    res = await client.get(f"{API}/blood-types")
    assert res.status_code == 200
    assert [item["code"] for item in res.json()] == [
        "A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-",
    ]  # fmt: skip


async def test_queue_statuses_carry_is_terminal(client: AsyncClient) -> None:
    items = (await client.get(f"{API}/queue-statuses")).json()
    assert items[0]["code"] == "pre_recepcion"
    terminal = {item["code"] for item in items if item["is_terminal"]}
    assert terminal == {"finalizada", "retirado"}
    assert "variant" not in items[0]


async def test_result_flags_carry_variant_and_report_flag(client: AsyncClient) -> None:
    items = {
        item["code"]: item for item in (await client.get(f"{API}/result-flags")).json()
    }
    assert items["critical_high"]["variant"] == "danger"
    assert items["critical_high"]["show_in_report"] is True
    assert items["normal"]["show_in_report"] is False


async def test_trace_steps_carry_category(client: AsyncClient) -> None:
    items = {
        item["code"]: item for item in (await client.get(f"{API}/trace-steps")).json()
    }
    assert items["queue.entered"]["category"] == "queue"
    assert items["queue.entered"]["name"]


@pytest.mark.parametrize("slug", ["queue-transition-kinds", "validation-statuses"])
async def test_simple_catalogs(client: AsyncClient, slug: str) -> None:
    items = (await client.get(f"{API}/{slug}")).json()
    assert items and all(item["code"] and item["name"] for item in items)


async def test_inactive_items_only_with_include_inactive(
    client: AsyncClient, session
) -> None:
    from sqlalchemy import update

    from app.modules.queue.models import BloodType

    await session.execute(
        update(BloodType).where(BloodType.code == "O-").values(is_active=False)
    )
    codes = [item["code"] for item in (await client.get(f"{API}/blood-types")).json()]
    assert "O-" not in codes
    everything = (await client.get(f"{API}/blood-types?include_inactive=true")).json()
    assert "O-" in [item["code"] for item in everything]


async def test_sexes_come_from_vladimir_without_the_wildcard(
    client: AsyncClient,
) -> None:
    items = (await client.get(f"{API}/sexes")).json()
    assert [item["code"] for item in items] == ["male", "female"]
    assert all(item["name"] for item in items)


async def test_document_types_come_from_leo(client: AsyncClient) -> None:
    items = (await client.get(f"{API}/document-types")).json()
    assert {"CC", "TI", "CE", "PA"} <= {item["code"] for item in items}
    # Alias anterior, mismo contenido.
    legacy = (await client.get("/api/v1/document-types")).json()
    assert [item["code"] for item in legacy] == [item["code"] for item in items]


async def test_unknown_slug_is_404(client: AsyncClient) -> None:
    res = await client.get(f"{API}/nope")
    assert res.status_code == 404
    assert res.json()["code"] == "not_found"


async def test_owner_down_is_a_502(client: AsyncClient, owners) -> None:
    owners.leo.down = True
    owners.clear()
    res = await client.get(f"{API}/document-types")
    assert res.status_code == 502
    assert res.json()["code"] == "owner_catalog_unavailable"


async def test_needs_any_incubus_permission(client: AsyncClient, leo: FakeLeo) -> None:
    leo.user = make_leo_user({"vladimir.samples.view"})
    assert (await client.get(f"{API}/blood-types")).status_code == 403
    leo.grant(permissions.RES_VIEW)
    assert (await client.get(f"{API}/blood-types")).status_code == 200


async def test_requires_a_session(client: AsyncClient, leo: FakeLeo) -> None:
    leo.user = None
    assert (await client.get(f"{API}/blood-types")).status_code == 401


def _service(tags: set[str]) -> LeoUser:
    return LeoUser(
        id=UUID(int=0),
        username="acuarius",
        name="Acuarius",
        email="",
        permissions=frozenset(tags),
        session_id=None,
        principal_type="service",
        client_id="acuarius",
    )


async def test_a_service_needs_the_delivery_permission(
    client: AsyncClient, leo: FakeLeo
) -> None:
    leo.user = _service(set())
    assert (await client.get(f"{API}/result-flags")).status_code == 403
    leo.user = _service({permissions.DEL_VIEW})
    assert (await client.get(f"{API}/result-flags")).status_code == 200
