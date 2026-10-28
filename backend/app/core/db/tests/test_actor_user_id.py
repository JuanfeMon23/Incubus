"""Columnas `*_user_id`: id de usuario de Leo junto al nombre del actor (migracion 0007)."""

import os
import subprocess
import sys
import uuid
from pathlib import Path

import psycopg
import pytest
from sqlalchemy import select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError

from app.core.config import get_settings
from app.modules.queue.models import (
    Patient,
    Priority,
    QueueEntry,
    QueueStatusHistory,
)

BACKEND_DIR = Path(__file__).resolve().parents[4]

COLUMNS = [
    ("queue_entries", "claimed_by_user_id"),
    ("queue_status_history", "actor_user_id"),
    ("order_tests", "validated_by_user_id"),
    ("order_preconditions", "reception_checked_by_user_id"),
    ("order_preconditions", "sampling_checked_by_user_id"),
    ("order_samples", "collected_by_user_id"),
    ("order_samples", "received_by_user_id"),
    ("order_results", "entered_by_user_id"),
]


async def _new_entry(session):
    priority = (await session.execute(select(Priority).limit(1))).scalars().one()
    patient = Patient(
        document_number=uuid.uuid4().hex[:15], first_name="ANA", first_last_name="P"
    )
    session.add(patient)
    await session.flush()
    entry = QueueEntry(patient_id=patient.id, priority_id=priority.id)
    session.add(entry)
    await session.flush()
    return entry, priority


@pytest.mark.parametrize(("table", "column"), COLUMNS)
async def test_columna_uuid_nullable_sin_fk(session, table, column):
    row = (
        await session.execute(
            text(
                "SELECT data_type, is_nullable FROM information_schema.columns "
                "WHERE table_name = :t AND column_name = :c"
            ),
            {"t": table, "c": column},
        )
    ).one()
    assert row.data_type == "uuid"
    assert row.is_nullable == "YES"
    fks = (
        await session.execute(
            text(
                "SELECT 1 FROM information_schema.key_column_usage k "
                "JOIN information_schema.table_constraints c USING (constraint_name) "
                "WHERE k.table_name = :t AND k.column_name = :c "
                "AND c.constraint_type = 'FOREIGN KEY'"
            ),
            {"t": table, "c": column},
        )
    ).all()
    assert fks == []


async def test_claimed_by_user_id_acepta_uuid_y_null(session):
    entry, _ = await _new_entry(session)
    assert entry.claimed_by_user_id is None
    uid = uuid.uuid4()
    entry.claimed_by = "ANA"
    entry.claimed_by_user_id = uid
    await session.flush()
    got = await session.execute(
        text("SELECT claimed_by_user_id FROM queue_entries WHERE id = :i"),
        {"i": entry.id},
    )
    assert got.scalar_one() == uid


async def test_historial_inserta_actor_user_id(session):
    entry, priority = await _new_entry(session)
    uid = uuid.uuid4()
    row = QueueStatusHistory(
        queue_entry_id=entry.id,
        to_status="pre_recepcion",
        kind="enter",
        actor="ANA",
        actor_user_id=uid,
        priority_id=priority.id,
    )
    session.add(row)
    await session.flush()
    got = await session.execute(
        text("SELECT actor_user_id FROM queue_status_history WHERE id = :i"),
        {"i": row.id},
    )
    assert got.scalar_one() == uid


async def test_historial_sigue_append_only(session):
    entry, priority = await _new_entry(session)
    row = QueueStatusHistory(
        queue_entry_id=entry.id,
        to_status="pre_recepcion",
        kind="enter",
        actor_user_id=uuid.uuid4(),
        priority_id=priority.id,
    )
    session.add(row)
    await session.flush()
    for sql in (
        "UPDATE queue_status_history SET actor_user_id = NULL WHERE id = :i",
        "DELETE FROM queue_status_history WHERE id = :i",
    ):
        with pytest.raises(DBAPIError):
            async with session.begin_nested():
                await session.execute(text(sql), {"i": row.id})


async def test_indice_historial_por_usuario_y_fecha(session):
    defn = (
        await session.execute(
            text(
                "SELECT indexdef FROM pg_indexes WHERE tablename = "
                "'queue_status_history' AND indexname = "
                "'ix_queue_status_history_actor_user_id_changed_at'"
            )
        )
    ).scalar_one()
    assert "(actor_user_id, changed_at)" in defn


def _migrate(db_url: str, *args: str) -> None:
    env = {
        **os.environ,
        "DATABASE_URL": db_url,
        "MIGRATION_DATABASE_URL": db_url,
    }
    subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=BACKEND_DIR,
        env=env,
        check=True,
        capture_output=True,
    )


def test_migracion_0007_sube_y_baja_sin_perder_datos():
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
        _migrate(db_url, "upgrade", "0006")
        sync = scratch_url.set(drivername="postgresql")
        with psycopg.connect(
            sync.render_as_string(hide_password=False), autocommit=True
        ) as conn:
            conn.execute(
                "INSERT INTO patients (document_number, first_name, first_last_name) "
                "VALUES ('MIG7', 'A', 'B')"
            )
            conn.execute(
                "INSERT INTO queue_entries (patient_id, priority_id, claimed_by) "
                "SELECT p.id, (SELECT id FROM priorities LIMIT 1), 'x' "
                "FROM patients p WHERE document_number = 'MIG7'"
            )
            conn.execute(
                "INSERT INTO queue_status_history (queue_entry_id, to_status, kind, "
                "actor, priority_id) SELECT id, 'pre_recepcion', 'enter', 'x', "
                "priority_id FROM queue_entries"
            )
            _migrate(db_url, "upgrade", "head")
            assert conn.execute(
                "SELECT actor, actor_user_id FROM queue_status_history"
            ).fetchall() == [("x", None)]
            assert conn.execute(
                "SELECT claimed_by, claimed_by_user_id FROM queue_entries"
            ).fetchall() == [("x", None)]
            uid = uuid.uuid4()
            conn.execute("UPDATE queue_entries SET claimed_by_user_id = %s", (uid,))
            with pytest.raises(psycopg.Error):
                conn.execute("DELETE FROM queue_status_history")
            _migrate(db_url, "downgrade", "0006")
            present = {
                (r[0], r[1])
                for r in conn.execute(
                    "SELECT table_name, column_name FROM information_schema.columns"
                ).fetchall()
            }
            assert not (present & set(COLUMNS))
            assert conn.execute(
                "SELECT actor FROM queue_status_history"
            ).fetchall() == [("x",)]
            assert conn.execute("SELECT claimed_by FROM queue_entries").fetchall() == [
                ("x",)
            ]
            with pytest.raises(psycopg.Error):
                conn.execute("DELETE FROM queue_status_history")
    finally:
        with psycopg.connect(
            admin.render_as_string(hide_password=False), autocommit=True
        ) as conn:
            conn.execute(f'DROP DATABASE IF EXISTS "{scratch}" WITH (FORCE)')
