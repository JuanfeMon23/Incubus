"""Migracion 0014: `document_types` local eliminada (Leo es el dueno del catalogo)."""

import uuid

import psycopg
from sqlalchemy.engine import make_url

from app.core.config import get_settings
from app.core.db.tests.test_actor_user_id import _migrate


def test_migracion_0014_elimina_document_types_y_downgrade_la_recrea_con_semilla():
    url = make_url(get_settings().database_url)
    scratch = f"{url.database.removesuffix('_test')}_mig_{uuid.uuid4().hex[:8]}"
    admin = url.set(drivername="postgresql", database="postgres")
    scratch_url = url.set(database=scratch)
    admin_dsn = admin.render_as_string(hide_password=False)
    with psycopg.connect(admin_dsn, autocommit=True) as conn:
        conn.execute(f'CREATE DATABASE "{scratch}"')
    try:
        db_url = scratch_url.render_as_string(hide_password=False)
        sync = scratch_url.set(drivername="postgresql").render_as_string(
            hide_password=False
        )
        _migrate(db_url, "upgrade", "head")
        with psycopg.connect(sync, autocommit=True) as conn:
            assert conn.execute("SELECT to_regclass('document_types')").fetchone() == (
                None,
            )
            _migrate(db_url, "downgrade", "0013")
            assert conn.execute("SELECT count(*) FROM document_types").fetchone() == (
                9,
            )
            assert conn.execute(
                "SELECT count(*) FROM pg_trigger "
                "WHERE tgname = 'trg_document_types_forbid_delete'"
            ).fetchone() == (1,)
            _migrate(db_url, "upgrade", "head")
            assert conn.execute("SELECT to_regclass('document_types')").fetchone() == (
                None,
            )
            assert conn.execute(
                "SELECT count(*) FROM pg_trigger "
                "WHERE tgname = 'trg_document_types_forbid_delete'"
            ).fetchone() == (0,)
    finally:
        with psycopg.connect(admin_dsn, autocommit=True) as conn:
            conn.execute(f'DROP DATABASE IF EXISTS "{scratch}" WITH (FORCE)')
