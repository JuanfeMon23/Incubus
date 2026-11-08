"""API `/api/v1/settings`: contrato, permisos (view / edit / edit-security),
errores, bloqueo optimista, historial y auditoria en Leo."""

from sqlalchemy import text

from app.conftest import FakeLeo, make_leo_user
from app.core import permissions
from app.core.leo import catalog

SETTINGS_API = "/api/v1/settings"
PLAIN = f"{SETTINGS_API}/realtime.sweep_seconds"
SECURE = f"{SETTINGS_API}/activation.code_ttl_days"
ALL = set(catalog.tags)


def _body(value, version=1, reason="Ajuste de prueba"):
    return {"value": value, "reason": reason, "expected_version": version}


def _events(leo: FakeLeo) -> list[dict]:
    return [
        event for event in leo.events if event["action_tag"] == permissions.SET_UPDATE
    ]


async def test_listado_agrupado_con_las_trece_claves_y_su_contrato(client) -> None:
    response = await client.get(SETTINGS_API)
    assert response.status_code == 200, response.text
    groups = {
        group_payload["group"]: group_payload["settings"]
        for group_payload in response.json()["groups"]
    }
    assert set(groups) == {"activation", "realtime", "pagination", "labels", "trace"}
    assert sum(len(group_settings) for group_settings in groups.values()) == 13
    ttl = next(
        setting
        for setting in groups["activation"]
        if setting["key"] == "activation.code_ttl_days"
    )
    assert ttl == {
        **ttl,
        "type": "int",
        "value": 30,
        "default": 30,
        "min": 1,
        "max": 365,
        "unit": "days",
        "version": 1,
        "requires_security_permission": True,
    }
    security = {
        setting["key"]
        for group_settings in groups.values()
        for setting in group_settings
        if setting["requires_security_permission"]
    }
    assert security == {
        "activation.code_ttl_days",
        "activation.verify_max_per_ip_doc",
        "activation.verify_max_per_doc",
        "activation.verify_window_seconds",
    }


async def test_editar_cambia_el_valor_guarda_historial_y_audita(
    client, leo: FakeLeo, session
) -> None:
    response = await client.put(PLAIN, json=_body(60))
    assert response.status_code == 200, response.text
    assert response.json()["value"] == 60 and response.json()["version"] == 2
    assert response.json()["updated_by"] == str(leo.user.id)
    history = (await client.get(f"{PLAIN}/history")).json()
    assert history["total"] == 1
    assert history["items"][0]["old_value"] == 30
    assert history["items"][0]["new_value"] == 60
    assert history["items"][0]["reason"] == "Ajuste de prueba"
    [event] = _events(leo)
    assert event["entity_type"] == "setting"
    assert event["entity_id"] == "realtime.sweep_seconds"
    assert event["reason"] == "Ajuste de prueba"
    assert event["changes"] == {"value": {"before": 30, "after": 60}}


async def test_ver_exige_view_y_editar_exige_edit(client, leo: FakeLeo) -> None:
    leo.grant(*(ALL - {permissions.SET_VIEW}))
    assert (await client.get(SETTINGS_API)).status_code == 403
    assert (await client.get(f"{PLAIN}/history")).status_code == 403
    leo.grant(permissions.SET_VIEW)
    assert (await client.get(SETTINGS_API)).status_code == 200
    assert (await client.put(PLAIN, json=_body(60))).status_code == 403


async def test_claves_de_seguridad_exigen_edit_y_edit_security(
    client, leo: FakeLeo
) -> None:
    leo.grant(permissions.SET_VIEW, permissions.SET_EDIT)
    denied = await client.put(SECURE, json=_body(10))
    assert denied.status_code == 403
    assert denied.json()["details"] == {"action": permissions.SET_EDIT_SECURITY}
    leo.grant(permissions.SET_VIEW, permissions.SET_EDIT_SECURITY)
    assert (await client.put(SECURE, json=_body(10))).status_code == 403
    leo.grant(permissions.SET_VIEW, permissions.SET_EDIT, permissions.SET_EDIT_SECURITY)
    ok = await client.put(SECURE, json=_body(10))
    assert ok.status_code == 200 and ok.json()["value"] == 10


async def test_errores_de_validacion_version_y_clave(client, leo: FakeLeo) -> None:
    out = await client.put(PLAIN, json=_body(5))  # minimo 10
    assert out.status_code == 422 and out.json()["code"] == "setting_out_of_range"
    typed = await client.put(PLAIN, json=_body("rapido"))
    assert typed.status_code == 422
    no_reason = await client.put(PLAIN, json=_body(60, reason=""))
    assert no_reason.status_code == 422
    assert (await client.put(PLAIN, json=_body(60))).status_code == 200
    stale = await client.put(PLAIN, json=_body(90, version=1))
    assert stale.status_code == 409
    assert (
        await client.put(f"{SETTINGS_API}/no.existe", json=_body(1))
    ).status_code == 404
    assert (await client.get(f"{SETTINGS_API}/no.existe/history")).status_code == 404
    assert len(_events(leo)) == 1  # solo el cambio aplicado


async def test_sin_sesion_da_401(client, leo: FakeLeo) -> None:
    leo.user = None
    assert (await client.get(SETTINGS_API)).status_code == 401
    assert (await client.put(PLAIN, json=_body(60))).status_code == 401


async def test_el_historial_es_inmutable_en_la_bd(client, session) -> None:
    await client.put(PLAIN, json=_body(60))
    import pytest
    from sqlalchemy.exc import DBAPIError

    with pytest.raises(DBAPIError):
        async with session.begin_nested():
            await session.execute(text("UPDATE settings_history SET reason = 'xxxx'"))


async def test_editar_con_un_uuid_de_usuario_arbitrario_lo_deja_en_la_bd(
    client, leo: FakeLeo, session
) -> None:
    # Sin tabla local de usuarios: el uuid de Leo se guarda tal cual.
    leo.user = make_leo_user(ALL, name="Otra Persona")
    assert (await client.put(PLAIN, json=_body(60))).status_code == 200
    row = (
        await session.execute(
            text(
                "SELECT s.updated_by, h.changed_by FROM settings s, settings_history h"
                " WHERE s.key = 'realtime.sweep_seconds'"
            )
        )
    ).one()
    assert row.updated_by == row.changed_by == leo.user.id
