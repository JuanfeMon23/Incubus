"""`deploy/db_roles.sql`: roles de minimo privilegio.

Corre el script contra una BD temporal (`incubus_roles_test_<hex>`, migrada con
`MIGRATION_DATABASE_URL` mientras `DATABASE_URL` apunta a un servidor inexistente,
para probar tambien `migrations/env.py`) y verifica con `SET ROLE` lo que
`incubus_app` puede y no puede hacer. La BD se elimina al terminar y los roles solo
si no existian en el servidor.
"""

import asyncio
import os
import subprocess
import sys
import uuid
from collections.abc import AsyncGenerator
from pathlib import Path

import asyncpg
import pytest
import pytest_asyncio
from sqlalchemy.engine import make_url

from app.core.config import get_settings

BACKEND_DIR = Path(__file__).resolve().parents[4]
SCRIPT = (BACKEND_DIR / "deploy" / "db_roles.sql").read_text(encoding="utf-8")
ROLES = ("incubus_app", "incubus_migrator")
INSUFFICIENT_PRIVILEGE = "42501"
APPEND_ONLY = ("queue_status_history", "order_test_events", "settings_history")


def _dsn(database: str, driver: str) -> str:
    url = make_url(get_settings().database_url)
    return url.set(drivername=driver, database=database).render_as_string(
        hide_password=False
    )


async def _sqlstate(conn: asyncpg.Connection, role: str, sql: str) -> str | None:
    """SQLSTATE con que falla `sql` ejecutado como `role` (None si funciona)."""
    await conn.execute(f"SET ROLE {role}")
    try:
        await conn.execute(sql)
    except asyncpg.PostgresError as exc:
        return exc.sqlstate
    finally:
        await conn.execute("RESET ROLE")
    return None


@pytest_asyncio.fixture(scope="module")
async def roles_db() -> AsyncGenerator[asyncpg.Connection]:
    roles_db_name = f"incubus_roles_test_{uuid.uuid4().hex[:8]}"
    admin = await asyncpg.connect(_dsn("postgres", "postgresql"))
    existing = {
        r["rolname"]
        for r in await admin.fetch(
            "SELECT rolname FROM pg_roles WHERE rolname = ANY($1)", list(ROLES)
        )
    }
    await admin.execute(f'CREATE DATABASE "{roles_db_name}"')
    conn = None
    try:
        result = await asyncio.to_thread(
            subprocess.run,
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=BACKEND_DIR,
            env={
                **os.environ,
                "DATABASE_URL": "postgresql+asyncpg://nadie:x@127.0.0.1:1/nada",
                "MIGRATION_DATABASE_URL": _dsn(roles_db_name, "postgresql+asyncpg"),
            },
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr
        conn = await asyncpg.connect(_dsn(roles_db_name, "postgresql"))
        await conn.execute(SCRIPT)
        yield conn
    finally:
        if conn is not None:
            await conn.close()
        await admin.execute(f'DROP DATABASE IF EXISTS "{roles_db_name}" WITH (FORCE)')
        for role in ROLES:
            if role not in existing:
                await admin.execute(f"DROP ROLE IF EXISTS {role}")
        await admin.close()


async def test_alembic_uso_migration_database_url(roles_db) -> None:
    assert await roles_db.fetchval("SELECT count(*) FROM alembic_version") == 1


async def test_el_script_es_idempotente(roles_db) -> None:
    await roles_db.execute(SCRIPT)
    await roles_db.execute(SCRIPT)


async def test_roles_sin_privilegios_de_rol(roles_db) -> None:
    for role in ROLES:
        row = await roles_db.fetchrow(
            "SELECT rolsuper, rolcreatedb, rolcreaterole, rolreplication, "
            "rolbypassrls FROM pg_roles WHERE rolname = $1",
            role,
        )
        assert not any(row.values()), role
    assert not await roles_db.fetchval(
        "SELECT pg_has_role('incubus_app', 'incubus_migrator', 'MEMBER')"
    )


def test_el_script_no_define_contrasenas_ni_default_privileges() -> None:
    code = "\n".join(
        line for line in SCRIPT.splitlines() if not line.lstrip().startswith("--")
    ).upper()
    assert "PASSWORD" not in code
    assert "DEFAULT PRIVILEGES" not in code


async def test_migrator_es_duenio_de_esquema_tablas_y_funciones(roles_db) -> None:
    owners = {
        r["tableowner"]
        for r in await roles_db.fetch(
            "SELECT tableowner FROM pg_tables WHERE schemaname = 'public'"
        )
    }
    assert owners == {"incubus_migrator"}
    schema_owner = await roles_db.fetchval(
        "SELECT pg_get_userbyid(nspowner) FROM pg_namespace WHERE nspname = 'public'"
    )
    assert schema_owner == "incubus_migrator"
    fn_owners = {
        r["owner"]
        for r in await roles_db.fetch(
            "SELECT pg_get_userbyid(proowner) AS owner FROM pg_proc p "
            "JOIN pg_namespace n ON n.oid = p.pronamespace "
            "WHERE n.nspname = 'public' AND p.prokind = 'f'"
        )
    }
    assert fn_owners == {"incubus_migrator"}


async def test_las_tablas_append_only_estan_descubiertas(roles_db) -> None:
    """Toda tabla cuyo trigger prohibe UPDATE y DELETE solo tiene SELECT/INSERT."""
    discovered = {
        r["relname"]
        for r in await roles_db.fetch(
            "SELECT DISTINCT c.relname FROM pg_trigger t "
            "JOIN pg_class c ON c.oid = t.tgrelid WHERE NOT t.tgisinternal "
            "AND (t.tgtype & 8) <> 0 AND (t.tgtype & 16) <> 0"
        )
    }
    assert discovered == set(APPEND_ONLY)
    for table in discovered:
        privs = {
            p
            for p in ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE")
            if await roles_db.fetchval(
                "SELECT has_table_privilege('incubus_app', $1, $2)", table, p
            )
        }
        assert privs == {"SELECT", "INSERT"}, table


async def test_app_opera_tablas_normales(roles_db) -> None:
    await roles_db.execute("SET ROLE incubus_app")
    try:
        await roles_db.execute(
            "INSERT INTO order_counters (year_month, last_value) VALUES ('0001', 1)"
        )
        await roles_db.execute(
            "UPDATE order_counters SET last_value = 2 WHERE year_month = '0001'"
        )
        assert (
            await roles_db.fetchval(
                "SELECT last_value FROM order_counters WHERE year_month = '0001'"
            )
            == 2
        )
        await roles_db.execute("DELETE FROM order_counters WHERE year_month = '0001'")
    finally:
        await roles_db.execute("RESET ROLE")


async def test_secuencias_usage_y_select_sin_update(roles_db) -> None:
    rows = await roles_db.fetch(
        "SELECT has_sequence_privilege('incubus_app', c.oid, 'USAGE') u, "
        "has_sequence_privilege('incubus_app', c.oid, 'SELECT') s, "
        "has_sequence_privilege('incubus_app', c.oid, 'UPDATE') w "
        "FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
        "WHERE c.relkind = 'S' AND n.nspname = 'public'"
    )
    assert all(r["u"] and r["s"] and not r["w"] for r in rows)


async def test_secuencia_usable_al_insertar(roles_db) -> None:
    """Una tabla con secuencia (serial) exige USAGE: la app inserta en ella."""
    await _sqlstate(
        roles_db,
        "incubus_migrator",
        "CREATE TABLE seq_prueba (id serial PRIMARY KEY, v text)",
    )
    try:
        await roles_db.execute(SCRIPT)
        assert (
            await _sqlstate(
                roles_db, "incubus_app", "INSERT INTO seq_prueba (v) VALUES ('x')"
            )
            is None
        )
    finally:
        await _sqlstate(roles_db, "incubus_migrator", "DROP TABLE seq_prueba")


@pytest.mark.parametrize("table", APPEND_ONLY)
async def test_append_only_sin_update_delete_ni_ddl(roles_db, table: str) -> None:
    for sql in (
        f"UPDATE {table} SET id = id",
        f"DELETE FROM {table}",
        f"TRUNCATE {table}",
        f"DROP TABLE {table}",
        f"ALTER TABLE {table} DISABLE TRIGGER ALL",
        f"ALTER TABLE {table} ADD COLUMN x int",
    ):
        state = await _sqlstate(roles_db, "incubus_app", sql)
        assert state == INSUFFICIENT_PRIVILEGE, sql


async def test_tablas_con_trigger_anti_delete_no_dan_delete_a_la_app(roles_db) -> None:
    for table in ("patients", "orders", "queue_entries", "order_results"):
        assert (
            await _sqlstate(roles_db, "incubus_app", f"DELETE FROM {table}")
            == INSUFFICIENT_PRIVILEGE
        ), table
    assert await _sqlstate(roles_db, "incubus_app", "SELECT * FROM patients") is None


@pytest.mark.parametrize(
    "sql",
    [
        "DROP TABLE patients",
        "ALTER TABLE patients ADD COLUMN x int",
        "TRUNCATE patients",
        "CREATE TABLE intruso (id int)",
        "DROP SCHEMA public CASCADE",
        "CREATE INDEX ix_intruso ON patients (document_number)",
        "SELECT * FROM alembic_version",
        "CREATE ROLE intruso",
    ],
)
async def test_app_no_puede_ddl_ni_truncate(roles_db, sql: str) -> None:
    assert await _sqlstate(roles_db, "incubus_app", sql) == INSUFFICIENT_PRIVILEGE


async def test_migrator_hace_ddl_y_las_tablas_nuevas_requieren_reaplicar(
    roles_db,
) -> None:
    create = "CREATE TABLE tabla_nueva (id serial PRIMARY KEY, v text)"
    assert await _sqlstate(roles_db, "incubus_migrator", create) is None
    try:
        # Falla cerrada: la tabla nueva no es accesible hasta re-aplicar el script.
        assert (
            await _sqlstate(roles_db, "incubus_app", "SELECT * FROM tabla_nueva")
            == INSUFFICIENT_PRIVILEGE
        )
        await roles_db.execute(SCRIPT)
        assert (
            await _sqlstate(roles_db, "incubus_app", "SELECT * FROM tabla_nueva")
            is None
        )
    finally:
        assert (
            await _sqlstate(roles_db, "incubus_migrator", "DROP TABLE tabla_nueva")
            is None
        )


def test_los_tests_no_apuntan_alembic_a_desarrollo() -> None:
    """El conftest fija MIGRATION_DATABASE_URL a la BD `_test`: un .env futuro con
    esa variable no desvia las migraciones de los tests."""
    assert os.environ["MIGRATION_DATABASE_URL"] == os.environ["DATABASE_URL"]
    assert make_url(os.environ["DATABASE_URL"]).database.endswith("_test")
