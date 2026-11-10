"""Catalogos de categoria (migracion 0013): semilla, FK al code, sexo de Vladimir."""

import uuid

import psycopg
import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError

from app.core.config import get_settings
from app.core.db.tests.test_actor_user_id import _migrate
from app.modules.queue.transitions import QueueStatus

CATALOGS = {
    "blood_types": 8,
    "queue_statuses": 9,
    "queue_transition_kinds": 4,
    "validation_statuses": 3,
    "result_flags": 6,
    "trace_steps": 27,
}


@pytest.mark.parametrize(("table", "count"), CATALOGS.items())
async def test_semilla_con_codigo_nombre_orden_y_activo(session, table, count):
    rows = (
        await session.execute(
            text(
                f"SELECT code, name, sort_order, is_active FROM {table} ORDER BY sort_order"
            )
        )
    ).all()
    assert len(rows) == count
    assert all(row.name and row.is_active for row in rows)
    assert len({row.code for row in rows}) == count


async def test_estados_de_cola_coinciden_con_el_enum_de_sistema(session):
    codes = (
        (await session.execute(text("SELECT code FROM queue_statuses"))).scalars().all()
    )
    assert set(codes) == {status.value for status in QueueStatus}
    terminal = (
        (
            await session.execute(
                text("SELECT code FROM queue_statuses WHERE is_terminal")
            )
        )
        .scalars()
        .all()
    )
    assert set(terminal) == {"finalizada", "retirado"}


async def test_estado_de_cola_inexistente_viola_el_fk(session):
    await session.execute(
        text(
            "INSERT INTO patients (document_number, first_name, first_last_name) "
            "VALUES ('FKQ1', 'A', 'B')"
        )
    )
    with pytest.raises(IntegrityError, match="fk_queue_entries_status_queue_statuses"):
        await session.execute(
            text(
                "INSERT INTO queue_entries (patient_id, priority_id, status) "
                "SELECT p.id, (SELECT id FROM priorities LIMIT 1), 'inventado' "
                "FROM patients p WHERE document_number = 'FKQ1'"
            )
        )


@pytest.mark.parametrize(
    ("table", "column", "catalog"),
    [
        ("patients", "blood_type", "blood_types"),
        ("queue_entries", "status", "queue_statuses"),
        ("queue_status_history", "from_status", "queue_statuses"),
        ("queue_status_history", "to_status", "queue_statuses"),
        ("queue_status_history", "kind", "queue_transition_kinds"),
        ("order_tests", "validation_status", "validation_statuses"),
        ("order_results", "flag", "result_flags"),
        ("order_test_events", "step", "trace_steps"),
    ],
)
async def test_columna_de_categoria_es_fk_al_code_del_catalogo(
    session, table, column, catalog
):
    found = (
        await session.execute(
            text(
                "SELECT confrelid::regclass::text FROM pg_constraint "
                "WHERE contype = 'f' AND conname = :name"
            ),
            {"name": f"fk_{table}_{column}_{catalog}"},
        )
    ).scalar_one()
    assert found == catalog


async def test_catalogo_no_se_borra(session):
    with pytest.raises(Exception, match="nada se elimina"):
        await session.execute(text("DELETE FROM blood_types"))


async def test_sexo_ya_no_tiene_check_y_acepta_codigos_de_vladimir(session):
    for number, sex in (("SX1", "male"), ("SX2", "female"), ("SX3", None)):
        await session.execute(
            text(
                "INSERT INTO patients (document_number, first_name, first_last_name, sex) "
                "VALUES (:n, 'A', 'B', :s)"
            ),
            {"n": number, "s": sex},
        )


def test_migracion_0013_migra_sexo_sube_y_baja():
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
        _migrate(db_url, "upgrade", "0012")
        sync = scratch_url.set(drivername="postgresql")
        with psycopg.connect(
            sync.render_as_string(hide_password=False), autocommit=True
        ) as conn:
            for doc, sex in (("S1", "M"), ("S2", "F"), ("S3", None)):
                conn.execute(
                    "INSERT INTO patients (document_number, first_name, first_last_name, sex) "
                    "VALUES (%s, 'A', 'B', %s)",
                    (doc, sex),
                )
            conn.execute(
                "INSERT INTO queue_entries (patient_id, priority_id) "
                "SELECT p.id, (SELECT id FROM priorities LIMIT 1) FROM patients p "
                "WHERE document_number = 'S1'"
            )
            _migrate(db_url, "upgrade", "head")
            sexes = conn.execute(
                "SELECT document_number, sex FROM patients ORDER BY document_number"
            ).fetchall()
            assert sexes == [("S1", "male"), ("S2", "female"), ("S3", None)]
            assert conn.execute("SELECT count(*) FROM blood_types").fetchone() == (8,)
            with pytest.raises(psycopg.errors.ForeignKeyViolation):
                conn.execute("UPDATE queue_entries SET status = 'inventado'")
            with pytest.raises(psycopg.errors.ForeignKeyViolation):
                conn.execute("UPDATE patients SET blood_type = 'XX'")
            _migrate(db_url, "downgrade", "0012")
            sexes = conn.execute(
                "SELECT document_number, sex FROM patients ORDER BY document_number"
            ).fetchall()
            assert sexes == [("S1", "M"), ("S2", "F"), ("S3", None)]
            assert conn.execute(
                "SELECT to_regclass('blood_types'), to_regclass('trace_steps')"
            ).fetchone() == (None, None)
            with pytest.raises(psycopg.errors.CheckViolation):
                conn.execute("UPDATE patients SET sex = 'X'")
            with pytest.raises(psycopg.errors.CheckViolation):
                conn.execute("UPDATE queue_entries SET status = 'inventado'")
            _migrate(db_url, "upgrade", "head")
    finally:
        with psycopg.connect(
            admin.render_as_string(hide_password=False), autocommit=True
        ) as conn:
            conn.execute(f'DROP DATABASE IF EXISTS "{scratch}" WITH (FORCE)')
