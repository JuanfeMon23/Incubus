"""Sexo, tipo de documento y tipo de sangre se validan contra su catalogo (dueno
o BD); los estados de la cola, contra `queue_statuses`."""

import pytest

CEDULA_RAW = "\x00\x00PubDSK_1\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x000001020304050\x00GOMEZ\x00\x00\x00\x00RODRIGUEZ\x00\x00JUAN\x00\x00CARLOS\x00\x00\x00\x00M19850312\x0005001\x00O+\x00"
BASE = {"first_name": "ANA", "first_last_name": "LOPEZ", "document_number": "7770001"}


async def _priority(client):
    prs = (await client.get("/api/v1/priorities")).json()
    return next(priority["id"] for priority in prs if priority["code"] == "media")


async def _enter(client, **patient):
    return await client.post(
        "/api/v1/queue",
        json={"patient": {**BASE, **patient}, "priority_id": await _priority(client)},
    )


@pytest.mark.parametrize("sex", ["any", "M", "x"])
async def test_ingreso_con_sexo_invalido_es_422(client, sex):
    res = await _enter(client, sex=sex)
    assert res.status_code == 422
    assert res.json()["code"] == "validation_error"
    assert res.json()["details"] == {"sex": sex}


async def test_ingreso_con_sexo_valido_guarda_el_codigo_del_catalogo(client):
    res = await _enter(client, sex="female")
    assert res.status_code == 201
    assert res.json()["patient"]["sex"] == "female"


async def test_ingreso_con_tipo_de_documento_inactivo_en_leo_es_422(client, owners):
    owners.leo.data[0]["is_active"] = False  # CC
    res = await _enter(client, document_type="CC")
    assert res.status_code == 422
    assert res.json()["details"] == {"document_type": "CC"}


async def test_ingreso_con_tipo_de_sangre_inexistente_es_422(client):
    res = await _enter(client, blood_type="Z+")
    assert res.status_code == 422
    assert res.json()["details"] == {"blood_type": "Z+"}


async def test_tipo_de_sangre_inactivo_en_bd_es_422(client, session):
    from sqlalchemy import update

    from app.modules.queue.models import BloodType

    await session.execute(
        update(BloodType).where(BloodType.code == "O-").values(is_active=False)
    )
    assert (await _enter(client, blood_type="O-")).status_code == 422
    assert (await _enter(client, blood_type="O+")).status_code == 201


async def test_edicion_de_paciente_valida_sexo_y_sangre(client):
    patient_id = (await _enter(client)).json()["patient"]["id"]
    bad_sex = await client.patch(f"/api/v1/patients/{patient_id}", json={"sex": "any"})
    assert bad_sex.status_code == 422
    bad_blood = await client.patch(
        f"/api/v1/patients/{patient_id}", json={"blood_type": "Z+"}
    )
    assert bad_blood.status_code == 422
    ok = await client.patch(
        f"/api/v1/patients/{patient_id}", json={"sex": "male", "blood_type": "AB+"}
    )
    assert ok.status_code == 200
    assert ok.json()["sex"] == "male" and ok.json()["blood_type"] == "AB+"


async def test_dueno_caido_con_copia_vencida_sigue_validando(client, owners):
    assert (await _enter(client, sex="male")).status_code == 201  # llena la cache
    owners.vladimir.down = owners.leo.down = True
    cache = owners.catalogs._cache
    for key, (_, rows) in list(cache.items()):
        cache[key] = (0.0, rows)  # vencida
    res = await _enter(client, sex="female", document_number="7770002")
    assert res.status_code == 201


async def test_dueno_caido_sin_copia_es_502(client, owners):
    owners.vladimir.down = True
    res = await _enter(client, sex="male")
    assert res.status_code == 502
    assert res.json()["code"] == "owner_catalog_unavailable"


async def test_filtro_de_estados_desconocido_es_422(client):
    res = await client.get("/api/v1/queue", params={"status": "no_existe"})
    assert res.status_code == 422
    assert res.json()["details"] == {"status": "no_existe"}


async def test_filtro_de_estados_conocido(client):
    res = await client.get("/api/v1/queue", params={"status": "pre_recepcion"})
    assert res.status_code == 200


async def test_parse_cedula_devuelve_el_codigo_de_sexo_del_catalogo(client):
    res = await client.post("/api/v1/patients/parse-cedula", json={"raw": CEDULA_RAW})
    assert res.status_code == 200
    assert res.json()["sex"] == "male"
