"""Permisos de Leo en TODA la API de Incubus (con un Leo falso).

- Cada ruta de `/api/v1` exige sesion (401), salvo las listadas en `PUBLIC`.
- Quitar SOLO el tag de una ruta da 403 + evento `denied` con ese tag.
- Con el tag pasa la autorizacion.
- El catalogo declarado == los tags usados (`check_catalog()`).
"""

import re
from uuid import UUID

import pytest
from httpx import AsyncClient
from leo_sdk import LeoUser

from app.conftest import FakeLeo, make_leo_user
from app.core import permissions as p
from app.core.leo import auth, catalog
from app.main import app
from app.modules.queue.transitions import QueueStatus

ZERO = "00000000-0000-0000-0000-000000000000"
API = "/api/v1"

# Rutas sin sesion, con su motivo:
# - barcode: SVG del numero de orden; lo pide un <img> que no puede llevar DPoP
#   y no contiene ningun dato (solo codifica el numero de 8 digitos de la URL).
PUBLIC = {f"{API}/orders/barcode/{{order_number}}.svg"}

# (metodo, ruta, tag unico que la protege). `{x}` se reemplaza por un UUID.
SINGLE_TAG = [
    ("POST", "/queue", p.PRE_ENQUEUE),
    ("POST", "/queue/call-next", p.REC_CALL_NEXT),
    ("PATCH", "/patients/{x}", p.REC_EDIT_PATIENT),
    ("PUT", "/queue/{x}/draft", p.REC_EDIT_PATIENT),
    ("POST", "/queue/{x}/finish-sampling", p.SAM_FINISH),
    ("POST", "/orders/close-reception/{x}", p.REC_CLOSE),
    ("POST", "/orders/samples/{x}/collect", p.SAM_COLLECT),
    ("POST", "/orders/samples/{x}/uncollect", p.SAM_COLLECT),
    ("POST", "/orders/samples/{x}/receive", p.LAB_RECEIVE),
    ("POST", "/orders/samples/{x}/unreceive", p.LAB_UNRECEIVE),
    ("POST", "/orders/by-entry/{x}/print-labels", p.LBL_PRINT),
    ("GET", "/orders/by-entry/{x}/labels.pdf", p.LBL_PRINT),
    ("GET", "/orders/by-entry/{x}/labels.zpl", p.LBL_PRINT),
    ("POST", "/orders/by-entry/{x}/samples", p.LBL_VIEW),
    ("GET", "/lab/reception", p.LAB_VIEW),
    ("GET", "/results/queue?professional_id=s", p.RES_VIEW),
    ("GET", "/results/orders/{x}?professional_id=s", p.RES_VIEW),
    ("GET", "/results/tests/{x}?professional_id=s", p.RES_VIEW),
    ("PUT", "/results/tests/{x}/values", p.RES_ENTER),
    ("POST", "/results/tests/{x}/validate", p.RES_VALIDATE),
    ("GET", "/delivery/orders/123", p.DEL_VIEW),
    ("GET", "/delivery/orders/123/report.pdf", p.DEL_VIEW),
]
ALL = set(catalog.tags)


def _url(path: str) -> str:
    return API + path.replace("{x}", ZERO)


def _api_routes() -> list[tuple[str, str]]:
    """(metodo, ruta concreta) de toda la API, leidas del esquema OpenAPI."""
    found = []
    for path, operations in app.openapi()["paths"].items():
        if path.startswith(API) and path not in PUBLIC:
            concrete = re.sub(r"\{[^}]+\}", ZERO, path)
            found += [(method.upper(), concrete) for method in sorted(operations)]
    return found


def test_the_route_table_is_not_empty() -> None:
    assert len(_api_routes()) >= 40


@pytest.mark.parametrize(("method", "path"), _api_routes())
async def test_every_api_route_requires_a_session(
    client: AsyncClient, leo: FakeLeo, method: str, path: str
) -> None:
    leo.user = None
    response = await client.request(method, path, json={})
    assert response.status_code == 401, (method, path)
    assert response.json()["code"] == "not_authenticated"


async def test_barcode_is_public_by_design(client: AsyncClient, leo: FakeLeo) -> None:
    leo.user = None
    response = await client.get(f"{API}/orders/barcode/12345678.svg")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/svg+xml")


@pytest.mark.parametrize(("method", "path", "tag"), SINGLE_TAG)
async def test_missing_tag_returns_403_and_denied_event(
    client: AsyncClient, leo: FakeLeo, method: str, path: str, tag: str
) -> None:
    leo.grant(*(ALL - {tag}))
    response = await client.request(method, _url(path), json={})
    assert response.status_code == 403, response.text
    assert response.json()["details"] == {"action": tag}
    assert [(e["action_tag"], e["result"]) for e in leo.events] == [(tag, "denied")]


@pytest.mark.parametrize(("method", "path", "tag"), SINGLE_TAG)
async def test_with_only_its_tag_the_route_authorizes(
    client: AsyncClient, leo: FakeLeo, method: str, path: str, tag: str
) -> None:
    leo.grant(tag)
    response = await client.request(method, _url(path), json={})
    assert response.status_code not in (401, 403), (method, path, response.text)
    assert leo.events == []


# --- Rutas con varios tags posibles ---------------------------------------------


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/patients/lookup?document_number=123456"),
        ("POST", "/patients/parse-cedula"),
    ],
)
async def test_patient_tools_need_enqueue_or_edit_patient(
    client: AsyncClient, leo: FakeLeo, method: str, path: str
) -> None:
    leo.grant(*(ALL - {p.PRE_ENQUEUE, p.REC_EDIT_PATIENT}))
    denied = await client.request(method, API + path, json={"raw": ""})
    assert denied.status_code == 403
    assert denied.json()["details"]["any_of"] == [p.PRE_ENQUEUE, p.REC_EDIT_PATIENT]
    assert [e["result"] for e in leo.events] == ["denied"]
    for tag in (p.PRE_ENQUEUE, p.REC_EDIT_PATIENT):
        leo.grant(tag)
        assert (
            await client.request(method, API + path, json={"raw": ""})
        ).status_code not in (401, 403)


@pytest.mark.parametrize(
    ("path", "tags"),
    [
        ("/queue/{x}", p.ANY_STAGE_VIEW),
        ("/queue/{x}/history", p.ANY_STAGE_VIEW),
        ("/orders/by-entry/{x}", p.ANY_STAGE_VIEW),
        ("/orders/123", p.ANY_STAGE_VIEW),
        ("/queue", p.ANY_STAGE_VIEW),
    ],
)
async def test_entry_reads_need_the_view_of_some_stage(
    client: AsyncClient, leo: FakeLeo, path: str, tags: tuple[str, ...]
) -> None:
    leo.grant(*(ALL - set(tags)))
    assert (await client.get(_url(path))).status_code == 403
    for tag in tags:
        leo.grant(tag)
        response = await client.get(_url(path))
        assert response.status_code not in (401, 403), (path, tag, response.text)


async def test_queue_listing_is_filtered_by_stage_permission(
    client: AsyncClient, leo: FakeLeo
) -> None:
    prio = (await client.get(f"{API}/priorities")).json()[0]["id"]
    patient = {"first_name": "A", "first_last_name": "B"}
    for number in ("111111", "222222"):
        r = await client.post(
            f"{API}/queue",
            json={
                "patient": {**patient, "document_number": number},
                "priority_id": prio,
            },
        )
        assert r.status_code == 201
    await client.post(f"{API}/queue/call-next")  # una pasa a recepcion

    leo.grant(p.PRE_VIEW)
    listed = (await client.get(f"{API}/queue")).json()
    assert {e["status"] for e in listed} == {"pre_recepcion"}
    assert len(listed) == 1

    leo.grant(p.PRE_VIEW, p.REC_VIEW)
    assert len((await client.get(f"{API}/queue")).json()) == 2

    # pedir una etapa sin su `view` -> 403 + denied con ESE tag
    leo.events.clear()
    leo.grant(p.PRE_VIEW)
    response = await client.get(f"{API}/queue?status=en_atencion_recepcion")
    assert response.status_code == 403
    assert response.json()["details"] == {"action": p.REC_VIEW}
    assert [(e["action_tag"], e["result"]) for e in leo.events] == [
        (p.REC_VIEW, "denied")
    ]


@pytest.mark.parametrize(
    ("action", "status", "missing"),
    [
        ("claim", QueueStatus.PRE_RECEPCION, p.REC_CALL_NEXT),
        ("claim", QueueStatus.EN_ESPERA_TOMA_MUESTRAS, p.SAM_CLAIM),
        ("return", QueueStatus.EN_ATENCION_RECEPCION, p.REC_RETURN),
        ("return", QueueStatus.EN_ATENCION_TOMA_MUESTRAS, p.SAM_RETURN),
        ("remove", QueueStatus.PRE_RECEPCION, p.PRE_REMOVE),
        ("remove", QueueStatus.EN_ATENCION_RECEPCION, p.REC_REMOVE),
    ],
)
async def test_state_dependent_actions_need_the_tag_of_the_current_stage(
    client: AsyncClient,
    leo: FakeLeo,
    session,
    action: str,
    status: QueueStatus,
    missing: str,
) -> None:
    from sqlalchemy import update

    from app.modules.queue.models import QueueEntry

    prio = (await client.get(f"{API}/priorities")).json()[0]["id"]
    entry = (
        await client.post(
            f"{API}/queue",
            json={
                "patient": {
                    "document_number": "999999",
                    "first_name": "A",
                    "first_last_name": "B",
                },
                "priority_id": prio,
            },
        )
    ).json()
    await session.execute(
        update(QueueEntry)
        .where(QueueEntry.id == UUID(entry["id"]))
        .values(status=status.value)
    )
    reason = ZERO
    # tiene los tags de OTRAS etapas, pero no el de esta
    leo.grant(*(ALL - {missing}))
    leo.events.clear()
    response = await client.post(
        f"{API}/queue/{entry['id']}/{action}", json={"reason_id": reason}
    )
    assert response.status_code == 403, response.text
    assert response.json()["details"] == {"action": missing}
    assert [(e["action_tag"], e["result"]) for e in leo.events] == [(missing, "denied")]
    leo.grant(missing)
    response = await client.post(
        f"{API}/queue/{entry['id']}/{action}", json={"reason_id": reason}
    )
    assert response.status_code not in (401, 403)  # pasa la autorizacion


async def test_stage_changed_between_check_and_lock_is_a_409(
    client: AsyncClient, session
) -> None:
    from app.core.exceptions import ConflictError
    from app.modules.queue import service

    prio = (await client.get(f"{API}/priorities")).json()[0]["id"]
    entry = (
        await client.post(
            f"{API}/queue",
            json={
                "patient": {
                    "document_number": "888888",
                    "first_name": "A",
                    "first_last_name": "B",
                },
                "priority_id": prio,
            },
        )
    ).json()
    with pytest.raises(ConflictError):
        await service.claim(
            session,
            UUID(entry["id"]),
            actor="x",
            professional_id=None,
            expected_status="en_espera_toma_muestras",
        )


@pytest.mark.parametrize(
    "path",
    [
        "/priorities",
        "/document-types",
        "/removal-reasons",
        "/return-reasons",
        "/catalog/tests",
        "/catalog/staff",
        "/catalog/validators",
    ],
)
async def test_shared_catalogs_need_any_incubus_permission(
    client: AsyncClient, leo: FakeLeo, path: str
) -> None:
    leo.user = make_leo_user({"vladimir.samples.view"})  # otra app, ninguna de Incubus
    assert (await client.get(API + path)).status_code == 403
    leo.grant(p.DEL_VIEW)  # basta UN permiso de Incubus
    assert (await client.get(API + path)).status_code == 200


async def test_preview_is_a_shared_tool(client: AsyncClient, leo: FakeLeo) -> None:
    leo.user = make_leo_user(set())
    assert (
        await client.post(f"{API}/orders/preview", json={"test_codes": []})
    ).status_code == 403
    leo.grant(p.RES_VIEW)
    assert (
        await client.post(f"{API}/orders/preview", json={"test_codes": []})
    ).status_code == 200


async def test_services_cannot_read_person_catalogs(
    client: AsyncClient, leo: FakeLeo
) -> None:
    leo.user = LeoUser(
        id=UUID(ZERO),
        username="acuarius",
        name="Acuarius",
        email="",
        permissions=frozenset({p.DEL_VIEW}),
        session_id=None,
        principal_type="service",
        client_id="acuarius",
    )
    response = await client.get(f"{API}/priorities")
    assert response.status_code == 403
    assert response.json()["code"] == "user_required"


async def test_a_service_with_delivery_permission_reads_delivery(
    client: AsyncClient, leo: FakeLeo
) -> None:
    service_user = LeoUser(
        id=UUID(ZERO),
        username="acuarius",
        name="Acuarius",
        email="",
        permissions=frozenset({p.DEL_VIEW}),
        session_id=None,
        principal_type="service",
        client_id="acuarius",
    )
    leo.user = service_user
    response = await client.get(f"{API}/delivery/orders/00000000")
    assert response.status_code == 404  # autorizada: la orden no existe
    leo.user = LeoUser(**{**service_user.__dict__, "permissions": frozenset()})
    assert (await client.get(f"{API}/delivery/orders/00000000")).status_code == 403


# --- Catalogo ---------------------------------------------------------------------


def test_catalog_declared_equals_used_tags() -> None:
    auth.check_catalog()  # ningun tag usado sin declarar
    assert set(catalog.tags) == set(auth.used_tags)
    assert len(catalog.tags) == 23


def test_catalog_payload_has_readable_unique_names_per_module() -> None:
    payload = catalog.to_payload()
    slugs = [m["slug"] for m in payload["modules"]]
    assert slugs == [
        "pre-reception",
        "reception",
        "label-printing",
        "sampling",
        "lab-reception",
        "results",
        "results-delivery",
    ]
    for module in payload["modules"]:
        names = [a["name"] for a in module["actions"]]
        assert len(set(names)) == len(names)
        assert module["name"][0].isupper()
        for name in names:
            assert name[0].isupper() and " " in name  # «Verbo + objeto», no un tag
            assert "." not in name


def test_every_stage_has_a_view_permission() -> None:
    assert set(p.STAGE_VIEW) == {s.value for s in QueueStatus}
    assert set(p.STAGE_VIEW.values()) <= catalog.tags
    assert all(t.endswith(".view") for t in p.STAGE_VIEW.values())
