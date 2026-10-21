"""Fixtures compartidas.

- BD de pruebas aislada: se usa `<nombre>_test` (misma instancia que `DATABASE_URL`,
  se crea si falta y se migra), para no depender de los datos de desarrollo.
- `session`: transaccion externa que se revierte al final (savepoint anidado).
- `client`: httpx contra la app, con `get_session` y el catalogo de Vladimir
  reemplazados (sesion del test y `FakeCatalog`).
"""

import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy.engine import make_url


def _prepare_test_database() -> None:
    from app.core.config import get_settings

    url = make_url(get_settings().database_url)
    test_name = f"{url.database}_test"
    sync_url = url.set(drivername="postgresql", database="postgres")
    import psycopg

    with psycopg.connect(
        sync_url.render_as_string(hide_password=False), autocommit=True
    ) as conn:
        exists = conn.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s", (test_name,)
        ).fetchone()
        if not exists:
            conn.execute(f'CREATE DATABASE "{test_name}"')
    os.environ["DATABASE_URL"] = url.set(database=test_name).render_as_string(
        hide_password=False
    )
    from app.core.config import get_settings as _gs

    _gs.cache_clear()
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=Path(__file__).resolve().parent.parent,
        env=os.environ.copy(),
        check=True,
        capture_output=True,
    )


_prepare_test_database()

import time
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from leo_sdk import LeoError, LeoUnavailableError, LeoUser
from leo_sdk.models import Introspection, IntrospectUser
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.database import engine
from app.core.database import get_session as real_get_session
from app.core.leo import auth
from app.core.leo import catalog as leo_catalog
from app.main import app
from app.modules.catalog_client.client import get_catalog_client


@dataclass
class FakeLeo:
    """Doble de Leo para los tests: usuario actual y eventos de auditoria.

    `user=None` -> sin sesion (401). Por defecto el usuario tiene TODOS los tags
    del catalogo; usar `grant(*tags)` para dar solo algunos. `down=True` simula
    Leo caido al auditar.
    """

    user: LeoUser | None = None
    events: list[dict[str, Any]] = field(default_factory=list)
    down: bool = False
    # Introspeccion (sockets): token de la cookie, llave DPoP ligada y llamadas.
    access_token: str = "token-falso"
    jkt: str | None = None
    introspections: int = 0

    def grant(self, *tags: str) -> None:
        self.user = make_leo_user(tags)


def make_leo_user(tags: Any, name: str = "Tester Uno") -> LeoUser:
    return LeoUser(
        id=uuid4(),
        username="tester",
        name=name,
        email="tester@example.com",
        permissions=frozenset(tags),
        session_id=uuid4(),
        access_token="token-falso",
        jkt="jkt-falso",
    )


@pytest.fixture
def leo(monkeypatch: pytest.MonkeyPatch) -> FakeLeo:
    fake = FakeLeo(user=make_leo_user(leo_catalog.tags))

    async def ingest_audit(payload: dict[str, Any]) -> None:
        if fake.down:
            raise LeoUnavailableError("down")
        fake.events.append(payload)

    async def introspect(token: str, jkt: str) -> Introspection:
        fake.introspections += 1
        user = fake.user
        if user is None or token != fake.access_token or jkt != fake.jkt:
            return Introspection(active=False)
        return Introspection(
            active=True,
            user=IntrospectUser(
                id=user.id, username=user.username, name=user.name, email=user.email
            ),
            permissions=sorted(user.permissions),
            session_id=user.session_id,
            exp=int(time.time()) + 3600,
        )

    monkeypatch.setattr(auth.client, "ingest_audit", ingest_audit)
    monkeypatch.setattr(auth.client, "introspect", introspect)
    auth.audit._queue.clear()
    auth.sessions._cache.clear()
    auth.sessions._replay._seen.clear()
    return fake


def _override_current_user(leo: FakeLeo) -> None:
    async def current_user() -> LeoUser:
        if leo.user is None:
            raise LeoError("not_authenticated", "Inicia sesión para continuar.", 401)
        return leo.user

    app.dependency_overrides[auth.current_user] = current_user


class FakeCatalog:
    """Catalogo en memoria con la forma de `/api/v1/lab-tests` de Vladimir."""

    def __init__(self) -> None:
        self.tests: dict[str, dict] = {}
        self.categories: dict[str, str] = {}
        self.sample_types: dict[str, dict] = {}
        self.areas: dict[str, str] = {}
        self.managers: dict[str, str | None] = {}
        self.templates: dict[str, dict] = {}
        self.staff: list[dict] = []

    def add_area(
        self, area_id: str, code: str, manager_staff_id: str | None = None
    ) -> None:
        self.areas[area_id] = code
        self.managers[area_id] = manager_staff_id

    def add_template(self, version_id: str, analytes: list[dict]) -> None:
        rows = []
        for i, a in enumerate(analytes):
            rows.append(
                {
                    "code": a["code"],
                    "name": a["name"],
                    "section": a.get("section"),
                    "sort_order": i + 1,
                    "result_type": a["result_type"],
                    "unit": a.get("unit"),
                    "decimals": a.get("decimals"),
                    "options": a.get("options", []),
                    "formula": a.get("formula"),
                    "is_required": a.get("is_required", True),
                    "is_reportable": True,
                    "ranges": [
                        {
                            "is_active": True,
                            **{
                                k: None
                                for k in (
                                    "age_min",
                                    "age_max",
                                    "age_unit",
                                    "low",
                                    "high",
                                    "critical_low",
                                    "critical_high",
                                    "expected_option_id",
                                    "expected_boolean",
                                    "display_text",
                                )
                            },
                            **r,
                        }
                        for r in a.get("ranges", [])
                    ],
                }
            )
        self.templates[version_id] = {"version_id": version_id, "analytes": rows}

    def add_staff(self, staff_id: str, first: str, last: str, job_title: str) -> None:
        self.staff.append(
            {"id": staff_id, "name": f"{first} {last}", "job_title": job_title}
        )

    def add_sample_type(
        self, type_id: str, name: str, color: str, draw_order: int | None = None
    ) -> None:
        self.sample_types[type_id] = {
            "id": type_id,
            "code": type_id.upper(),
            "name": name,
            "cap_color_hex": color,
            "draw_order": draw_order,
            "collection_instructions": None,
            "is_active": True,
        }

    def add_test(
        self,
        code: str,
        name: str,
        preconditions: list[dict],
        sample_types: list[tuple] | None = None,
        area_id: str | None = None,
        template: str | None = None,
    ) -> None:
        pres = []
        for i, p in enumerate(preconditions):
            pid = f"pre-{code}-{i}"
            self.categories[pid] = p["category"]
            pres.append(
                {
                    "id": f"row-{pid}",
                    "precondition_id": pid,
                    "is_active": True,
                    "name": p.get("name", p["category"]),
                    "duration_value": p.get("value"),
                    "duration_unit": p.get("unit"),
                    "patient_instructions": p.get("text"),
                }
            )
        self.tests[code] = {
            "id": f"id-{code}",
            "code": code,
            "name": name,
            "is_active": True,
            "area_id": area_id,
            "result_template_version_id": template,
            "preconditions": pres,
            "sample_types": [
                {
                    "sample_type_id": sid,
                    "is_preferred": pref,
                    "required_volume_ml": vol,
                    "is_active": True,
                }
                for sid, pref, vol in (sample_types or [])
            ],
        }

    async def search_tests(self, q: str | None, limit: int = 20) -> list[dict]:
        return [
            t
            for t in self.tests.values()
            if not q or q.lower() in t["code"].lower() or q.lower() in t["name"].lower()
        ]

    async def get_test_by_code(self, code: str) -> dict | None:
        return self.tests.get(code)

    async def precondition_categories(self) -> dict[str, str]:
        return self.categories

    async def sample_types_by_id(self) -> dict[str, dict]:
        return self.sample_types

    async def areas_by_id(self) -> dict[str, str]:
        return self.areas

    async def list_staff(self) -> list[dict]:
        return self.staff

    async def areas_with_managers(self) -> list[dict]:
        names = {s["id"]: s["name"] for s in self.staff}
        return [
            {
                "id": area_id,
                "code": code,
                "name": code,
                "manager_staff_id": self.managers.get(area_id),
                "manager_name": names.get(self.managers.get(area_id) or ""),
            }
            for area_id, code in self.areas.items()
        ]

    async def template_structure(self, version_id: str) -> dict:
        return self.templates[version_id]

    async def warm_templates(self, version_ids: list[str]) -> None:
        return None


@pytest_asyncio.fixture
async def session() -> AsyncGenerator[AsyncSession]:
    async with engine.connect() as connection:
        outer = await connection.begin()
        maker = async_sessionmaker(
            bind=connection,
            expire_on_commit=False,
            join_transaction_mode="create_savepoint",
        )
        async with maker() as test_session:
            yield test_session
        await outer.rollback()


@pytest_asyncio.fixture
def catalog() -> FakeCatalog:
    return FakeCatalog()


@pytest_asyncio.fixture
async def client(
    session: AsyncSession, catalog: FakeCatalog, leo: FakeLeo
) -> AsyncGenerator[AsyncClient]:
    async def override_get_session() -> AsyncGenerator[AsyncSession]:
        yield session

    app.dependency_overrides[real_get_session] = override_get_session
    _override_current_user(leo)
    app.dependency_overrides[get_catalog_client] = lambda: catalog
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def committed_client(
    catalog: FakeCatalog, leo: FakeLeo
) -> AsyncGenerator[AsyncClient]:
    """Cliente con sesiones REALES por request (commit de verdad), para probar
    concurrencia entre transacciones. Limpia las tablas de datos al terminar
    (solo la BD `_test`; los catalogos parametrizados se conservan)."""
    app.dependency_overrides[get_catalog_client] = lambda: catalog
    _override_current_user(leo)
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac
    finally:
        app.dependency_overrides.clear()
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "TRUNCATE queue_status_history, order_results, order_samples, "
                    "order_preconditions, order_tests, orders, order_counters, "
                    "queue_entries, patients RESTART IDENTITY CASCADE"
                )
            )
        await engine.dispose()


@pytest_asyncio.fixture
async def published(monkeypatch) -> list[dict]:
    """Captura los mensajes que `publish_entry` entrega (antes de proyectarlos a
    la vista minima de cada transporte) en lugar de enviarlos a clientes.

    Tras la peticion, `await events.drain()` espera a que se entreguen."""
    from app.modules.queue import events

    sent: list[dict] = []

    async def record(message: dict) -> None:
        sent.append(message)

    monkeypatch.setattr(events, "_deliver", record)
    return sent
