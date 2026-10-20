"""`queue_entries.version`: contador monotono mantenido por trigger en la BD."""

import os
import subprocess
import sys
import uuid
from pathlib import Path

import psycopg
from sqlalchemy import select, text
from sqlalchemy.engine import make_url

from app.core.config import get_settings
from app.modules.queue.models import Patient, Priority, QueueEntry

BACKEND_DIR = Path(__file__).resolve().parents[4]


async def _new_entry(session) -> QueueEntry:
    priority = (await session.execute(select(Priority).limit(1))).scalars().one()
    patient = Patient(
        document_number=uuid.uuid4().hex[:15],
        first_name="ANA",
        first_last_name="PRUEBA",
    )
    session.add(patient)
    await session.flush()
    entry = QueueEntry(patient_id=patient.id, priority_id=priority.id)
    session.add(entry)
    await session.flush()
    return entry


async def _db_version(session, entry_id) -> int:
    row = await session.execute(
        text("SELECT version FROM queue_entries WHERE id = :id"), {"id": entry_id}
    )
    return row.scalar_one()


async def test_columna_existe_not_null_con_default_cero(session):
    row = (
        await session.execute(
            text(
                "SELECT data_type, is_nullable, column_default "
                "FROM information_schema.columns "
                "WHERE table_name = 'queue_entries' AND column_name = 'version'"
            )
        )
    ).one()
    assert row.data_type == "integer"
    assert row.is_nullable == "NO"
    assert row.column_default == "0"


async def test_insert_empieza_en_cero(session):
    entry = await _new_entry(session)
    assert entry.version == 0
    assert await _db_version(session, entry.id) == 0


async def test_update_de_estado_incrementa_en_uno(session):
    entry = await _new_entry(session)
    entry.status = "en_atencion_recepcion"
    await session.flush()
    assert await _db_version(session, entry.id) == 1


async def test_update_de_draft_incrementa_en_uno(session):
    entry = await _new_entry(session)
    entry.draft = {"test_codes": ["GLU"]}
    await session.flush()
    assert await _db_version(session, entry.id) == 1


async def test_update_de_profesional_asignado_incrementa_en_uno(session):
    entry = await _new_entry(session)
    entry.assigned_professional_id = "p-1"
    entry.assigned_professional_name = "DRA. LOPEZ"
    await session.flush()
    assert await _db_version(session, entry.id) == 1


async def test_orm_lee_la_version_nueva_tras_flush_sin_refresh(session):
    entry = await _new_entry(session)
    for expected in (1, 2, 3):
        entry.draft = {"n": expected}
        await session.flush()
        assert entry.version == expected


async def test_varios_updates_incrementan_de_uno_en_uno(session):
    entry = await _new_entry(session)
    for _ in range(3):
        await session.execute(
            text("UPDATE queue_entries SET claimed_by = 'x' WHERE id = :id"),
            {"id": entry.id},
        )
    assert await _db_version(session, entry.id) == 3


async def test_update_no_puede_bajar_ni_fijar_la_version(session):
    entry = await _new_entry(session)
    await session.execute(
        text("UPDATE queue_entries SET claimed_by = 'x' WHERE id = :id"),
        {"id": entry.id},
    )
    for forced in (0, -5, 999):
        await session.execute(
            text("UPDATE queue_entries SET version = :v WHERE id = :id"),
            {"v": forced, "id": entry.id},
        )
    assert await _db_version(session, entry.id) == 4


def _migrate(db_url: str, *args: str) -> None:
    env = {**os.environ, "DATABASE_URL": db_url}
    subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=BACKEND_DIR,
        env=env,
        check=True,
        capture_output=True,
    )


def test_migracion_sube_y_baja_sin_perder_datos():
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
        _migrate(db_url, "upgrade", "0005")
        sync = scratch_url.set(drivername="postgresql")
        with psycopg.connect(
            sync.render_as_string(hide_password=False), autocommit=True
        ) as conn:
            conn.execute(
                "INSERT INTO patients (document_number, first_name, first_last_name) "
                "VALUES ('MIG1', 'A', 'B')"
            )
            conn.execute(
                "INSERT INTO queue_entries (patient_id, priority_id) "
                "SELECT p.id, (SELECT id FROM priorities LIMIT 1) "
                "FROM patients p WHERE document_number = 'MIG1'"
            )
            _migrate(db_url, "upgrade", "head")
            assert conn.execute("SELECT version FROM queue_entries").fetchall() == [
                (0,)
            ]
            conn.execute("UPDATE queue_entries SET claimed_by = 'x'")
            assert conn.execute("SELECT version FROM queue_entries").fetchone() == (1,)
            _migrate(db_url, "downgrade", "0005")
            cols = conn.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'queue_entries'"
            ).fetchall()
            assert ("version",) not in cols
            assert conn.execute("SELECT claimed_by FROM queue_entries").fetchall() == [
                ("x",)
            ]
            assert not conn.execute(
                "SELECT 1 FROM pg_proc WHERE proname = 'fn_queue_entries_bump_version'"
            ).fetchone()
            assert not conn.execute(
                "SELECT 1 FROM pg_trigger WHERE tgname = 'trg_queue_entries_bump_version'"
            ).fetchone()
    finally:
        with psycopg.connect(
            admin.render_as_string(hide_password=False), autocommit=True
        ) as conn:
            conn.execute(f'DROP DATABASE IF EXISTS "{scratch}" WITH (FORCE)')
