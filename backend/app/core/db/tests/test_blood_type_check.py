"""CHECK `ck_patients_blood_type` y normalizacion de RH invalido (migracion 0008)."""

import uuid

import psycopg
import pytest
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError

from app.core.config import get_settings
from app.core.db.tests.test_actor_user_id import _migrate
from app.modules.queue.models import Patient

VALID = ["A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"]


def _patient(blood_type):
    return Patient(
        document_number=uuid.uuid4().hex[:15],
        first_name="ANA",
        first_last_name="P",
        blood_type=blood_type,
    )


@pytest.mark.parametrize("value", [*VALID, None])
async def test_check_acepta_rh_valido_y_null(session, value):
    session.add(_patient(value))
    await session.flush()


@pytest.mark.parametrize("value", ["DD", "22", "a+", "O", "AB", ""])
async def test_check_rechaza_rh_invalido(session, value):
    session.add(_patient(value))
    with pytest.raises(IntegrityError, match="ck_patients_blood_type"):
        await session.flush()


def test_migracion_0008_normaliza_rh_invalido_y_baja():
    url = make_url(get_settings().database_url)
    scratch = f"{url.database.removesuffix('_test')}_mig_{uuid.uuid4().hex[:8]}"
    admin = url.set(drivername="postgresql", database="postgres")
    scratch_url = url.set(database=scratch)
    with psycopg.connect(
        admin.render_as_string(hide_password=False), autocommit=True
    ) as conn:
        conn.execute(f'CREATE DATABASE "{scratch}"')
    try:
        db_url = scratch_url.render_as_string(hide_password=False)
        _migrate(db_url, "upgrade", "0007")
        sync = scratch_url.set(drivername="postgresql")
        with psycopg.connect(
            sync.render_as_string(hide_password=False), autocommit=True
        ) as conn:
            for doc, rh in (("M1", "DD"), ("M2", "22"), ("M3", "O+"), ("M4", None)):
                conn.execute(
                    "INSERT INTO patients (document_number, first_name, "
                    "first_last_name, blood_type) VALUES (%s, 'NOMBRE', 'APE', %s)",
                    (doc, rh),
                )
            _migrate(db_url, "upgrade", "head")
            rows = conn.execute(
                "SELECT document_number, first_name, blood_type FROM patients "
                "ORDER BY document_number"
            ).fetchall()
            assert rows == [
                ("M1", "NOMBRE", None),
                ("M2", "NOMBRE", None),
                ("M3", "NOMBRE", "O+"),
                ("M4", "NOMBRE", None),
            ]
            with pytest.raises(psycopg.errors.CheckViolation):
                conn.execute("UPDATE patients SET blood_type = 'DD'")
            _migrate(db_url, "downgrade", "0007")
            conn.execute(
                "UPDATE patients SET blood_type = 'DD' WHERE document_number = 'M1'"
            )
    finally:
        with psycopg.connect(
            admin.render_as_string(hide_password=False), autocommit=True
        ) as conn:
            conn.execute(f'DROP DATABASE IF EXISTS "{scratch}" WITH (FORCE)')
