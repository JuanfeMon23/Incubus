"""`order_test_events` (append-only) y columnas de autoria nuevas (migracion 0011)."""

import os
import subprocess
import sys
import uuid
from pathlib import Path

import psycopg
import pytest
from sqlalchemy import select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.core.config import get_settings
from app.modules.orders.models import Order, OrderSample, OrderTest, OrderTestEvent
from app.modules.queue.models import Patient, Priority, QueueEntry

BACKEND_DIR = Path(__file__).resolve().parents[4]


async def _order(session) -> tuple[Order, OrderTest, OrderSample]:
    priority = (await session.execute(select(Priority).limit(1))).scalars().one()
    patient = Patient(
        document_number=uuid.uuid4().hex[:15], first_name="ANA", first_last_name="P"
    )
    session.add(patient)
    await session.flush()
    entry = QueueEntry(patient_id=patient.id, priority_id=priority.id)
    session.add(entry)
    await session.flush()
    order = Order(
        order_number=uuid.uuid4().hex[:8],
        queue_entry_id=entry.id,
        patient_id=patient.id,
    )
    session.add(order)
    await session.flush()
    test = OrderTest(
        order_id=order.id, test_code="GLU", test_name="Glucosa", snapshot={}
    )
    sample = OrderSample(
        order_id=order.id,
        sample_type_id="s1",
        sample_type_code="SUE",
        name="Suero",
        test_codes=["GLU"],
    )
    session.add_all([test, sample])
    await session.flush()
    return order, test, sample


async def _event(session, order, test=None, sample=None, **kw) -> OrderTestEvent:
    values = {"step": "muestra.recolectada", "summary": "Muestra recolectada"} | kw
    ev = OrderTestEvent(
        order_id=order.id,
        order_test_id=test.id if test else None,
        order_sample_id=sample.id if sample else None,
        **values,
    )
    session.add(ev)
    await session.flush()
    return ev


async def test_defaults_de_la_bd(session):
    order, test, _ = await _order(session)
    ev = await _event(session, order, test)
    await session.refresh(ev)
    assert ev.occurred_at is not None
    assert ev.details == {}
    assert ev.actor_name is None and ev.actor_user_id is None
    assert ev.staff_id is None and ev.request_id is None
    assert ev.id.version == 7


async def test_evento_de_orden_completa_sin_prueba_ni_tubo(session):
    order, _, _ = await _order(session)
    ev = await _event(session, order, step="orden.creada", summary="Orden creada")
    assert ev.order_test_id is None and ev.order_sample_id is None


async def test_guarda_actores_y_detalles(session):
    order, test, sample = await _order(session)
    leo, staff = uuid.uuid4(), uuid.uuid4()
    ev = await _event(
        session,
        order,
        test,
        sample,
        actor_name="ANA",
        actor_user_id=leo,
        staff_id=staff,
        details={"volumen_ml": 3},
        request_id="req-1",
    )
    row = (
        await session.execute(
            text(
                "SELECT actor_user_id, staff_id, details FROM order_test_events WHERE id = :i"
            ),
            {"i": ev.id},
        )
    ).one()
    assert (row.actor_user_id, row.staff_id, row.details) == (
        leo,
        staff,
        {"volumen_ml": 3},
    )


async def test_update_bloqueado_por_trigger(session):
    order, test, _ = await _order(session)
    ev = await _event(session, order, test)
    with pytest.raises(DBAPIError, match="solo insercion"):
        async with session.begin_nested():
            await session.execute(
                text("UPDATE order_test_events SET summary = 'x' WHERE id = :i"),
                {"i": ev.id},
            )


async def test_delete_bloqueado_por_trigger(session):
    order, test, _ = await _order(session)
    ev = await _event(session, order, test)
    with pytest.raises(DBAPIError, match="solo insercion"):
        async with session.begin_nested():
            await session.execute(
                text("DELETE FROM order_test_events WHERE id = :i"), {"i": ev.id}
            )


@pytest.mark.parametrize(
    "step", ["muestra.recolectada", "orden.creada", "resultado.validado.final"]
)
async def test_step_valido(session, step):
    order, _, _ = await _order(session)
    ev = await _event(session, order, step=step)
    assert ev.step == step


@pytest.mark.parametrize(
    "step",
    [
        "",
        "muestra",
        "Muestra.recolectada",
        "muestra.Recolectada",
        "muestra.",
        ".x",
        "muestra-recolectada",
        "muestra.recolectada1",
        "1muestra.x",
        "muestra.a b",
    ],
)
async def test_step_invalido_viola_check(session, step):
    order, _, _ = await _order(session)
    with pytest.raises(IntegrityError, match="step_format"):
        async with session.begin_nested():
            await _event(session, order, step=step)


async def test_step_de_mas_de_40_caracteres_se_rechaza(session):
    order, _, _ = await _order(session)
    with pytest.raises(DBAPIError):
        async with session.begin_nested():
            await _event(session, order, step="a." + "b" * 40)


async def test_summary_y_step_son_obligatorios(session):
    order, _, _ = await _order(session)
    for col in ("summary", "step"):
        values = {"step": "a.b", "summary": "s"} | {col: None}
        with pytest.raises(IntegrityError):
            async with session.begin_nested():
                session.add(OrderTestEvent(order_id=order.id, **values))
                await session.flush()


async def test_fks_inexistentes_se_rechazan(session):
    order, _, _ = await _order(session)
    for kw in (
        {"order_id": uuid.uuid4()},
        {"order_id": order.id, "order_test_id": uuid.uuid4()},
        {"order_id": order.id, "order_sample_id": uuid.uuid4()},
    ):
        with pytest.raises(IntegrityError, match="fk_order_test_events"):
            async with session.begin_nested():
                session.add(OrderTestEvent(step="a.b", summary="s", **kw))
                await session.flush()


async def test_fks_son_on_delete_restrict(session):
    rows = (
        (
            await session.execute(
                text(
                    "SELECT confdeltype::text FROM pg_constraint "
                    "WHERE conrelid = 'order_test_events'::regclass AND contype = 'f'"
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 3 and set(rows) == {"r"}


async def test_indices_existen(session):
    names = set(
        (
            await session.execute(
                text(
                    "SELECT indexname FROM pg_indexes WHERE tablename = 'order_test_events'"
                )
            )
        ).scalars()
    )
    assert {"ix_order_test_events_order", "ix_order_test_events_test"} <= names


async def test_columnas_nuevas_nullable_y_created_at_not_null(session):
    expected = {
        ("order_tests", "created_at"): ("timestamp with time zone", "NO"),
        ("order_tests", "created_by"): ("character varying", "YES"),
        ("order_tests", "created_by_user_id"): ("uuid", "YES"),
        ("order_samples", "labels_printed_by"): ("character varying", "YES"),
        ("order_samples", "labels_printed_by_user_id"): ("uuid", "YES"),
        ("activation_codes", "created_by_user_id"): ("uuid", "YES"),
        ("activation_codes", "used_by_client"): ("character varying", "YES"),
    }
    for (table, col), (dtype, nullable) in expected.items():
        row = (
            await session.execute(
                text(
                    "SELECT data_type, is_nullable FROM information_schema.columns "
                    "WHERE table_name = :t AND column_name = :c"
                ),
                {"t": table, "c": col},
            )
        ).one()
        assert (row.data_type, row.is_nullable) == (dtype, nullable), (table, col)


async def test_order_test_created_at_por_defecto_y_autoria_nula(session):
    _, test, sample = await _order(session)
    await session.refresh(test)
    assert test.created_at is not None
    assert test.created_by is None and test.created_by_user_id is None
    assert sample.labels_printed_by is None and sample.labels_printed_by_user_id is None


def _migrate(db_url: str, *args: str) -> None:
    subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=BACKEND_DIR,
        env={**os.environ, "DATABASE_URL": db_url},
        check=True,
        capture_output=True,
    )


def test_migracion_sube_baja_y_sube_con_datos_existentes():
    url = make_url(get_settings().database_url)
    scratch = f"{url.database.removesuffix('_test')}_mig_{uuid.uuid4().hex[:8]}"
    admin = url.set(drivername="postgresql", database="postgres")
    scratch_url = url.set(database=scratch)
    with psycopg.connect(
        admin.render_as_string(hide_password=False), autocommit=True
    ) as c:
        c.execute(f'CREATE DATABASE "{scratch}"')
    try:
        db_url = scratch_url.render_as_string(hide_password=False)
        _migrate(db_url, "upgrade", "0010")
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
                "SELECT p.id, (SELECT id FROM priorities LIMIT 1) FROM patients p"
            )
            conn.execute(
                "INSERT INTO orders (order_number, queue_entry_id, patient_id, created_at) "
                "SELECT '26100001', q.id, q.patient_id, '2026-01-02 03:04:05+00' "
                "FROM queue_entries q"
            )
            conn.execute(
                "INSERT INTO order_tests (order_id, test_code, test_name, snapshot) "
                "SELECT id, 'GLU', 'Glucosa', '{}' FROM orders"
            )
            for _ in range(2):  # sube, baja, sube
                _migrate(db_url, "upgrade", "head")
                row = conn.execute(
                    "SELECT t.created_at = o.created_at, t.created_by FROM order_tests t "
                    "JOIN orders o ON o.id = t.order_id"
                ).fetchone()
                assert row == (True, None)
                assert conn.execute(
                    "SELECT count(*) FROM order_test_events"
                ).fetchone() == (0,)
                _migrate(db_url, "downgrade", "0010")
                assert not conn.execute(
                    "SELECT 1 FROM information_schema.tables WHERE table_name = 'order_test_events'"
                ).fetchone()
                assert not conn.execute(
                    "SELECT 1 FROM pg_proc WHERE proname = 'fn_forbid_update_delete'"
                ).fetchone()
                cols = {
                    r[0]
                    for r in conn.execute(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_name = 'order_tests'"
                    )
                }
                assert not cols & {"created_at", "created_by", "created_by_user_id"}
                assert conn.execute("SELECT test_code FROM order_tests").fetchall() == [
                    ("GLU",)
                ]
            _migrate(db_url, "upgrade", "head")
    finally:
        with psycopg.connect(
            admin.render_as_string(hide_password=False), autocommit=True
        ) as c:
            c.execute(f'DROP DATABASE IF EXISTS "{scratch}" WITH (FORCE)')
