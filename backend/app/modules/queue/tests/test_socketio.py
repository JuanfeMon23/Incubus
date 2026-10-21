"""Tiempo real por Socket.IO: handshake, rooms, eventos sin PII, sync y WS legado.

Servidor uvicorn REAL en puerto efimero (la misma app y el mismo bucle que las
pruebas) y `socketio.AsyncClient` como cliente. Los cambios se provocan por REST
con el cliente httpx de siempre; el nuevo no tiene vias de escritura.
"""

import asyncio
import json
from contextlib import asynccontextmanager

import pytest
import pytest_asyncio
import socketio
import uvicorn

from app.core import realtime
from app.core.config import get_settings
from app.main import app
from app.modules.orders.tests.test_sampling import (
    PATIENT as SAMPLING_PATIENT,
)
from app.modules.orders.tests.test_sampling import (
    _claim,
    _printed,
)
from app.modules.queue import events, rooms
from app.modules.queue import socket_handlers as handlers
from app.testing import DpopKey

NS = "/queue"
PII_PATIENT = {
    "document_number": "7766554433",
    "first_name": "ZULEMA",
    "first_last_name": "QUINTERO",
}
PII_WORDS = ("ZULEMA", "QUINTERO", "7766554433", "ANA", "LOPEZ", "5544332211")
LIVE_KEYS = {
    "id",
    "status",
    "version",
    "priority_id",
    "assigned_professional_id",
    "order_number",
}


def _origin() -> str:
    return get_settings().cors_origins_list[0]


@pytest_asyncio.fixture(scope="session")
async def live_url():
    config = uvicorn.Config(
        app, host="127.0.0.1", port=0, log_level="warning", lifespan="off"
    )
    server = uvicorn.Server(config)
    task = asyncio.create_task(server.serve())
    while not server.started:
        await asyncio.sleep(0.01)
    port = server.servers[0].sockets[0].getsockname()[1]
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    await task


@pytest.fixture(autouse=True)
def _session_for_sync(session, monkeypatch):
    """`sync` lee con la sesion de la prueba (transaccion que se revierte)."""

    @asynccontextmanager
    async def use_test_session():
        yield session

    monkeypatch.setattr(handlers, "open_session", use_test_session)


class Probe:
    def __init__(self) -> None:
        self.sio = socketio.AsyncClient()
        self.events: list[tuple[str, dict]] = []

        async def catch_all(event, *args):
            self.events.append((event, args[0] if args else None))

        self.sio.on("*", catch_all, namespace=NS)

    async def subscribe(self, *room_names):
        return await self.sio.call("subscribe", {"rooms": list(room_names)}, NS)

    async def sync(self):
        # El ack llega DESPUES de lo emitido antes (misma cola del socket): sirve
        # de barrera para afirmar que algo NO llego, sin dormir.
        return await self.sio.call("sync", None, NS)

    def named(self, name):
        return [p for n, p in self.events if n == name]


HANDSHAKE_HTU = "http://incubus.test/socket.io/"  # PUBLIC_URL (conftest) + path


@pytest.fixture
def browser(leo) -> DpopKey:
    """Llave DPoP del "navegador" ligada a la sesion falsa de Leo."""
    key = DpopKey()
    leo.jkt = key.jkt
    return key


@pytest_asyncio.fixture
async def connect(live_url, leo, browser):
    """Conecta un cliente Socket.IO con sesion de Leo (cookie + prueba DPoP).

    `cookie=False` / `dpop=False` omiten cada parte; `key` firma con otra llave."""
    opened: list[Probe] = []

    async def _connect(
        origin: str | None = None,
        *,
        cookie: bool | str = True,
        dpop: bool | str = True,
        **kwargs,
    ) -> Probe:
        probe = Probe()
        headers = {} if origin == "" else {"Origin": origin or _origin()}
        if cookie:
            name = "incubus_access" if cookie is True else cookie
            headers["Cookie"] = f"{name}={leo.access_token}"
        proof = browser.proof("GET", HANDSHAKE_HTU) if dpop is True else dpop
        await probe.sio.connect(
            live_url,
            namespaces=[NS],
            headers=headers,
            auth={"dpop": proof} if dpop else None,
            transports=["websocket"],
            wait_timeout=5,
            **kwargs,
        )
        opened.append(probe)
        return probe

    yield _connect
    for p in opened:
        await p.sio.disconnect()


async def _priority(client):
    prs = {p["code"]: p["id"] for p in (await client.get("/api/v1/priorities")).json()}
    return prs["media"]


async def _enter(client, patient=PII_PATIENT):
    res = await client.post(
        "/api/v1/queue",
        json={"patient": patient, "priority_id": await _priority(client)},
    )
    assert res.status_code == 201
    return res.json()


# --- Rooms (unitarias) ----------------------------------------------------------


def test_rooms_validos_se_construyen_y_se_parsean():
    assert rooms.stage_room("pre_recepcion") == "stage:pre_recepcion"
    assert rooms.is_valid_room("stage:en_laboratorio")
    assert rooms.is_valid_room("entry:018f3c1e-7b8a-7c3d-9e2f-0123456789ab")
    assert rooms.is_valid_room("staff:staff-1")


@pytest.mark.parametrize(
    "bad",
    [
        "stage:inexistente",
        "stage:",
        "entry:no-es-uuid",
        "staff:",
        "staff:con espacios",
        "staff:" + "x" * 65,
        "otro:1",
        "pre_recepcion",
        "",
        None,
        7,
    ],
)
def test_rooms_mal_formados_se_rechazan(bad):
    assert not rooms.is_valid_room(bad)


# --- Handshake -------------------------------------------------------------------


async def test_origin_valido_con_sesion_conecta_y_guarda_el_principal(connect, leo):
    probe = await connect()
    assert probe.sio.connected
    session = await realtime.sio.get_session(probe.sio.get_sid(NS), namespace=NS)
    assert session["principal"].name == "Tester Uno"
    assert session["principal"].permissions == leo.user.permissions


async def test_origin_ajeno_es_rechazado(connect):
    with pytest.raises(socketio.exceptions.ConnectionError):
        await connect(origin="https://evil.example")


async def test_sin_origin_se_rechaza_por_defecto(connect):
    with pytest.raises(socketio.exceptions.ConnectionError):
        await connect(origin="")


async def test_sin_origin_se_acepta_si_la_bandera_lo_permite(connect, monkeypatch):
    monkeypatch.setattr(get_settings(), "socketio_allow_no_origin", True)
    probe = await connect(origin="")
    assert probe.sio.connected


async def test_authenticate_socket_rechaza_origin_ajeno():
    assert (
        await realtime.authenticate_socket(
            {"HTTP_ORIGIN": "https://evil.example"}, None
        )
        is None
    )


# --- subscribe / unsubscribe ----------------------------------------------------------


async def test_subscribe_valido_une_a_varios_estados_y_responde_ack(connect):
    probe = await connect()
    ack = await probe.subscribe(
        "stage:pre_recepcion", "stage:en_atencion_recepcion", "staff:staff-1"
    )
    assert ack["ok"] is True
    assert set(ack["joined"]) == {
        "stage:pre_recepcion",
        "stage:en_atencion_recepcion",
        "staff:staff-1",
    }


@pytest.mark.parametrize(
    "payload",
    [
        {"rooms": ["stage:inexistente"]},
        {"rooms": ["entry:123"]},
        {"rooms": ["staff:"]},
        {"rooms": "stage:pre_recepcion"},
        {"rooms": [1]},
        {},
        None,
        "stage:pre_recepcion",
    ],
)
async def test_subscribe_invalido_responde_error_y_no_une_nada(connect, payload):
    probe = await connect()
    ack = await probe.sio.call("subscribe", payload, NS)
    assert ack["ok"] is False
    assert ack["error"] == "invalid_rooms"
    assert (await probe.subscribe())["joined"] == []


async def test_subscribe_con_un_room_invalido_no_une_ninguno(connect):
    probe = await connect()
    ack = await probe.subscribe("stage:pre_recepcion", "stage:basura")
    assert ack["ok"] is False
    assert (await probe.subscribe())["joined"] == []


async def test_subscribe_limita_los_rooms_por_socket(connect, monkeypatch):
    monkeypatch.setattr(get_settings(), "socketio_max_rooms", 2)
    probe = await connect()
    assert (await probe.subscribe("stage:pre_recepcion"))["ok"] is True
    ack = await probe.subscribe("stage:en_laboratorio", "stage:finalizada")
    assert ack["ok"] is False
    assert ack["error"] == "too_many_rooms"
    assert (await probe.subscribe())["joined"] == ["stage:pre_recepcion"]


async def test_unsubscribe_sale_del_room_y_deja_de_recibir(connect, client):
    probe = await connect()
    await probe.subscribe("stage:pre_recepcion")
    ack = await probe.sio.call("unsubscribe", {"rooms": ["stage:pre_recepcion"]}, NS)
    assert ack == {"ok": True, "joined": []}
    await _enter(client)
    await events.drain()
    await probe.sync()
    assert probe.events == []


# --- Emision ------------------------------------------------------------------------


async def test_alta_llega_solo_al_stage_suscrito_y_sin_pii(connect, client):
    en_pre = await connect()
    en_otro = await connect()
    sin_nada = await connect()
    await en_pre.subscribe("stage:pre_recepcion")
    await en_otro.subscribe("stage:en_laboratorio")
    entry = await _enter(client)
    await events.drain()
    for p in (en_pre, en_otro, sin_nada):
        await p.sync()
    assert en_otro.events == [] and sin_nada.events == []
    [(name, payload)] = en_pre.events
    assert name == "entry:created"
    assert set(payload) == LIVE_KEYS
    assert payload["id"] == entry["id"]
    assert payload["status"] == "pre_recepcion"
    assert payload["version"] == entry["version"]
    assert payload["priority_id"] == entry["priority"]["id"]
    assert payload["assigned_professional_id"] is None
    raw = json.dumps(en_pre.events)
    for word in PII_WORDS:
        assert word not in raw


async def test_cambio_de_etapa_llega_al_stage_nuevo_al_anterior_y_a_la_entrada(
    connect, client
):
    nuevo = await connect()
    anterior = await connect()
    por_entrada = await connect()
    ajeno = await connect()
    entry = await _enter(client)
    await nuevo.subscribe("stage:en_atencion_recepcion")
    await anterior.subscribe("stage:pre_recepcion")
    await por_entrada.subscribe(f"entry:{entry['id']}")
    await ajeno.subscribe(
        "stage:en_laboratorio", "entry:" + "0" * 8 + "-0000-0000-0000-" + "0" * 12
    )
    await events.drain()
    res = await client.post(f"/api/v1/queue/{entry['id']}/claim", json={"actor": "a"})
    assert res.status_code == 200
    await events.drain()
    for p in (nuevo, anterior, por_entrada, ajeno):
        await p.sync()
    assert ajeno.events == []
    for p in (nuevo, anterior, por_entrada):
        [(name, payload)] = p.events
        assert name == "status:changed"
        assert payload["status"] == "en_atencion_recepcion"
        assert payload["previous_status"] == "pre_recepcion"
        assert payload["version"] == res.json()["version"]
        assert set(payload) == LIVE_KEYS | {"previous_status"}


async def test_un_cliente_en_varios_rooms_del_mismo_evento_lo_recibe_una_vez(
    connect, client
):
    entry = await _enter(client)
    probe = await connect()
    await probe.subscribe(
        "stage:pre_recepcion", "stage:en_atencion_recepcion", f"entry:{entry['id']}"
    )
    await events.drain()
    await client.post(f"/api/v1/queue/{entry['id']}/claim", json={"actor": "a"})
    await events.drain()
    await probe.sync()
    assert len(probe.events) == 1


async def test_retiro_emite_entry_removed_al_stage_anterior(connect, client):
    entry = await _enter(client)
    anterior = await connect()
    removidos = await connect()
    await anterior.subscribe("stage:pre_recepcion")
    await removidos.subscribe("stage:retirado")
    reasons = (await client.get("/api/v1/removal-reasons")).json()
    res = await client.post(
        f"/api/v1/queue/{entry['id']}/remove",
        json={"actor": "a", "reason_id": reasons[0]["id"]},
    )
    assert res.status_code == 200, res.text
    await events.drain()
    for p in (anterior, removidos):
        await p.sync()
    for p in (anterior, removidos):
        [(name, payload)] = p.events
        assert name == "entry:removed"
        assert payload["status"] == "retirado"
        assert payload["previous_status"] == "pre_recepcion"


async def test_borrador_emite_entry_updated_con_version_mayor(connect, client):
    entry = await _enter(client)
    claimed = await client.post(
        f"/api/v1/queue/{entry['id']}/claim", json={"actor": "a"}
    )
    probe = await connect()
    await probe.subscribe(f"entry:{entry['id']}")
    await events.drain()
    res = await client.put(
        f"/api/v1/queue/{entry['id']}/draft", json={"test_codes": ["GLU"]}
    )
    await events.drain()
    await probe.sync()
    [(name, payload)] = probe.events
    assert name == "entry:updated"
    assert "previous_status" not in payload
    assert payload["version"] == res.json()["version"] > claimed.json()["version"]
    assert "GLU" not in json.dumps(payload)  # el borrador (clinico) no viaja


async def test_tubo_emite_sample_updated_con_sample_id_a_staff_y_entrada(
    connect, client, catalog
):
    entry_id, number = await _printed(client, catalog)
    await _claim(client, entry_id)
    tube = (await client.get(f"/api/v1/orders/by-entry/{entry_id}")).json()["samples"][
        0
    ]
    staff = await connect()
    ajeno = await connect()
    await staff.subscribe("staff:staff-1")
    await ajeno.subscribe("staff:staff-2")
    await events.drain()
    await client.post(f"/api/v1/orders/samples/{tube['id']}/collect", json={})
    await client.post(f"/api/v1/orders/samples/{tube['id']}/uncollect", json={})
    await events.drain()
    for p in (staff, ajeno):
        await p.sync()
    assert ajeno.events == []
    assert [n for n, _ in staff.events] == ["sample:updated", "sample:updated"]
    first, second = (p for _, p in staff.events)
    assert first["sample_id"] == second["sample_id"] == tube["id"]
    assert first["assigned_professional_id"] == "staff-1"
    assert first["order_number"] == number
    assert first["version"] < second["version"]


async def test_claim_de_toma_llega_a_la_etapa_anterior_y_al_profesional(
    connect, client, catalog
):
    entry_id, _ = await _printed(client, catalog)
    anterior = await connect()
    staff = await connect()
    await anterior.subscribe("stage:en_espera_toma_muestras")
    await staff.subscribe("staff:staff-1")
    await events.drain()
    await _claim(client, entry_id)
    await events.drain()
    for p in (anterior, staff):
        await p.sync()
    for p in (anterior, staff):
        [(name, payload)] = p.events
        assert name == "status:changed"
        assert payload["previous_status"] == "en_espera_toma_muestras"
        assert payload["status"] == "en_atencion_toma_muestras"


async def test_eventos_de_una_entrada_llegan_en_orden_de_version(connect, client):
    entry = await _enter(client)
    probe = await connect()
    await probe.subscribe(f"entry:{entry['id']}")
    await client.post(f"/api/v1/queue/{entry['id']}/claim", json={"actor": "a"})
    for i in range(3):
        await client.put(
            f"/api/v1/queue/{entry['id']}/draft", json={"test_codes": [f"T{i}"]}
        )
    await events.drain()
    await probe.sync()
    versions = [p["version"] for _, p in probe.events]
    assert len(versions) == 4
    assert versions == sorted(versions) and len(set(versions)) == 4


# --- sync -----------------------------------------------------------------------------


async def test_sync_devuelve_snapshot_minimo_de_los_stages_suscritos(connect, client):
    primera = await _enter(client)
    otra = await _enter(client, {**PII_PATIENT, "document_number": "7766554434"})
    await client.post(f"/api/v1/queue/{otra['id']}/claim", json={"actor": "a"})
    probe = await connect()
    await probe.subscribe("stage:pre_recepcion", f"entry:{primera['id']}")
    ack = await probe.sync()
    assert ack["ok"] is True
    [row] = ack["entries"]
    assert set(row) == LIVE_KEYS
    assert row["id"] == primera["id"]
    assert row["version"] == primera["version"]
    assert row["status"] == "pre_recepcion"
    raw = json.dumps(ack)
    for word in PII_WORDS:
        assert word not in raw


async def test_sync_sin_stages_devuelve_lista_vacia(connect):
    probe = await connect()
    assert await probe.sync() == {"ok": True, "entries": []}


# --- WS nativo retirado -----------------------------------------------------------------


async def test_ws_queue_nativo_ya_no_existe(live_url):
    import aiohttp

    async with aiohttp.ClientSession() as http:
        with pytest.raises(aiohttp.WSServerHandshakeError):
            async with http.ws_connect(
                live_url.replace("http", "ws") + "/ws/queue",
                headers={"Origin": _origin()},
            ):
                pass


# --- Publicador / Redis -------------------------------------------------------------------


async def test_un_fallo_del_socketio_no_rompe_la_respuesta(client, monkeypatch, caplog):
    async def boom(*_a, **_k):
        raise RuntimeError("socketio roto")

    monkeypatch.setattr(realtime.sio, "emit", boom)
    res = await client.post(
        "/api/v1/queue",
        json={"patient": SAMPLING_PATIENT, "priority_id": await _priority(client)},
    )
    assert res.status_code == 201
    await events.drain()
    assert "socketio roto" in caplog.text


def test_sin_redis_url_usa_el_manager_en_memoria():
    assert realtime.build_manager(None) is None


def test_con_redis_url_usa_async_redis_manager(monkeypatch):
    seen = {}

    class FakeManager:
        def __init__(self, url):
            seen["url"] = url

    monkeypatch.setattr(socketio, "AsyncRedisManager", FakeManager)
    manager = realtime.build_manager("redis://localhost:6379/0")
    assert isinstance(manager, FakeManager)
    assert seen["url"] == "redis://localhost:6379/0"


# === Autenticacion con Leo (cookie + prueba DPoP en `auth`) ==========================

from app.conftest import make_leo_user
from app.core import permissions as perms
from app.core.leo import auth as leo_auth
from app.main import queue_namespace


async def test_sin_cookie_se_rechaza(connect):
    with pytest.raises(socketio.exceptions.ConnectionError):
        await connect(cookie=False)


async def test_sin_prueba_dpop_se_rechaza(connect):
    with pytest.raises(socketio.exceptions.ConnectionError):
        await connect(dpop=False)


async def test_prueba_firmada_por_otra_llave_se_rechaza(connect):
    forged = DpopKey().proof("GET", HANDSHAKE_HTU)
    # firma valida de OTRA llave: su jkt no es el de la sesion de Leo
    with pytest.raises(socketio.exceptions.ConnectionError):
        await connect(dpop=forged)


async def test_prueba_con_firma_alterada_se_rechaza(connect, browser):
    head, payload, _sig = browser.proof("GET", HANDSHAKE_HTU).split(".")
    other = DpopKey().proof("GET", HANDSHAKE_HTU).split(".")[2]
    with pytest.raises(socketio.exceptions.ConnectionError):
        await connect(dpop=f"{head}.{payload}.{other}")


@pytest.mark.parametrize(
    ("htm", "htu", "iat"),
    [
        ("POST", HANDSHAKE_HTU, 0),  # htm equivocado
        ("GET", "http://incubus.test/socket.io", 0),  # htu sin la barra final
        ("GET", "http://otro.test/socket.io/", 0),  # htu de otro host
        ("GET", HANDSHAKE_HTU, -120),  # iat fuera de la ventana de 60 s
        ("GET", HANDSHAKE_HTU, 120),
    ],
)
async def test_prueba_con_claims_invalidos_se_rechaza(connect, browser, htm, htu, iat):
    import time

    proof = browser.proof(htm, htu, iat=time.time() + iat)
    with pytest.raises(socketio.exceptions.ConnectionError):
        await connect(dpop=proof)


async def test_prueba_repetida_se_rechaza_una_sola_vez_vale(connect, browser):
    proof = browser.proof("GET", HANDSHAKE_HTU)
    first = await connect(dpop=proof)
    assert first.sio.connected
    with pytest.raises(socketio.exceptions.ConnectionError):
        await connect(dpop=proof)  # replay


async def test_cada_conexion_con_prueba_nueva_entra(connect):
    a = await connect()
    b = await connect()
    assert a.sio.connected and b.sio.connected


async def test_sesion_inactiva_en_leo_se_rechaza(connect, leo):
    leo.user = None
    with pytest.raises(socketio.exceptions.ConnectionError):
        await connect()


async def test_sesion_sin_permisos_de_incubus_se_rechaza(connect, leo):
    leo.user = make_leo_user({"vladimir.samples.view"})
    with pytest.raises(socketio.exceptions.ConnectionError):
        await connect()


async def test_la_cookie_de_otra_app_no_vale(connect):
    """Con el nombre por defecto del SDK (`leo_access`) no entra: cada app usa
    la suya y no se pisan las sesiones."""
    with pytest.raises(socketio.exceptions.ConnectionError):
        await connect(cookie="leo_access")


def test_cada_etapa_exige_el_view_de_su_pantalla():
    from app.core.realtime import Principal, authorize_room

    for status, view in perms.STAGE_VIEW.items():
        yes = Principal("1", "u", "U", frozenset({view}))
        no = Principal("1", "u", "U", frozenset(perms.ANY_STAGE_VIEW) - {view})
        assert authorize_room(yes, rooms.stage_room(status)), status
        assert not authorize_room(no, rooms.stage_room(status)), status


def test_authorize_room_de_entrada_y_profesional():
    from app.core.realtime import Principal, authorize_room

    nobody = Principal("1", "u", "U", frozenset({perms.RES_VALIDATE}))
    viewer = Principal("1", "u", "U", frozenset({perms.LAB_VIEW}))
    sampler = Principal("1", "u", "U", frozenset({perms.SAM_VIEW}))
    entry = rooms.entry_room("00000000-0000-0000-0000-000000000001")
    assert not authorize_room(nobody, entry)
    assert authorize_room(viewer, entry)
    assert not authorize_room(viewer, rooms.staff_room("staff-1"))
    assert authorize_room(sampler, rooms.staff_room("staff-1"))
    assert not authorize_room(sampler, "otra:cosa")


async def test_subscribe_a_etapa_sin_permiso_responde_forbidden(connect, leo):
    leo.grant(perms.PRE_VIEW)
    probe = await connect()
    denied = await probe.subscribe("stage:en_atencion_recepcion")
    assert denied == {"ok": False, "error": "forbidden"}
    ok = await probe.subscribe("stage:pre_recepcion")
    assert ok == {"ok": True, "joined": ["stage:pre_recepcion"]}
    # atomico: un room prohibido entre varios no une ninguno
    mixed = await probe.subscribe("stage:en_laboratorio", "stage:pre_recepcion")
    assert mixed["error"] == "forbidden"


async def test_subscribe_a_entrada_y_profesional_exige_permisos(connect, leo):
    entry = "entry:00000000-0000-0000-0000-000000000001"
    leo.grant(perms.PRE_VIEW)
    probe = await connect()
    assert (await probe.subscribe(entry))["ok"] is True  # algun view de etapa
    assert (await probe.subscribe("staff:staff-1"))["error"] == "forbidden"
    leo.grant(perms.SAM_VIEW)
    leo_auth.sessions._cache.clear()
    assert (await probe.subscribe("staff:staff-1"))["ok"] is True


async def test_eventos_solo_llegan_a_quien_puede_ver_esa_etapa(connect, client, leo):
    leo.grant(perms.PRE_VIEW, perms.RES_VIEW)
    allowed = await connect()
    await allowed.subscribe("stage:pre_recepcion")
    leo.grant(perms.SAM_VIEW)
    leo_auth.sessions._cache.clear()
    blind = await connect()
    assert (await blind.subscribe("stage:pre_recepcion"))["error"] == "forbidden"
    leo.grant(*perms.catalog.tags)  # quien escribe por REST tiene todo
    await _enter(client)
    await events.drain()
    await allowed.sync()
    await blind.sync()
    assert len(allowed.named("entry:created")) == 1
    assert blind.named("entry:created") == []


async def test_el_sync_revalida_con_la_cache_de_introspeccion(connect, leo):
    probe = await connect()
    inicial = leo.introspections
    for _ in range(3):
        await probe.sync()
    assert leo.introspections == inicial  # misma cache de 30 s: sin llamadas


async def test_sesion_revocada_desconecta_en_el_siguiente_evento(connect, leo):
    probe = await connect()
    leo.user = None  # Leo revoca la sesion
    leo_auth.sessions._cache.clear()  # vence la cache de 30 s
    assert await probe.sync() == {"ok": False, "error": "session_expired"}
    for _ in range(50):
        if not probe.sio.connected:
            break
        await asyncio.sleep(0.02)
    assert not probe.sio.connected


async def test_permisos_quitados_sacan_de_los_rooms_en_el_siguiente_evento(
    connect, leo
):
    leo.grant(perms.PRE_VIEW, perms.REC_VIEW)
    probe = await connect()
    await probe.subscribe("stage:pre_recepcion", "stage:en_atencion_recepcion")
    leo.grant(perms.PRE_VIEW)  # se le quita recepcion
    leo_auth.sessions._cache.clear()
    joined = (await probe.subscribe("stage:pre_recepcion"))["joined"]
    assert joined == ["stage:pre_recepcion"]


async def test_barrido_desconecta_los_tokens_vencidos_sin_llamar_a_leo(
    connect, leo, monkeypatch
):
    probe = await connect()
    llamadas = leo.introspections
    assert await queue_namespace.disconnect_expired() == 0
    monkeypatch.setattr(realtime, "_now", lambda: 4_000_000_000)  # tras exp
    assert await queue_namespace.disconnect_expired() == 1
    assert leo.introspections == llamadas
    for _ in range(50):
        if not probe.sio.connected:
            break
        await asyncio.sleep(0.02)
    assert not probe.sio.connected
