"""Fixtures compartidas.

- `session`: BD real dentro de una transaccion externa que se revierte al final
  (savepoint anidado para sobrevivir a los `commit()` de los routers).
- `client`: httpx contra la app, con `get_session` y el catalogo de Vladimir
  reemplazados (sesion del test y `FakeCatalog`).
"""

from collections.abc import AsyncGenerator

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.database import engine
from app.core.database import get_session as real_get_session
from app.main import app
from app.modules.catalog_client.client import get_catalog_client


class FakeCatalog:
    """Catalogo en memoria con la forma de `/api/v1/lab-tests` de Vladimir."""

    def __init__(self) -> None:
        self.tests: dict[str, dict] = {}
        self.categories: dict[str, str] = {}

    def add_test(self, code: str, name: str, preconditions: list[dict]) -> None:
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
            "preconditions": pres,
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
    session: AsyncSession, catalog: FakeCatalog
) -> AsyncGenerator[AsyncClient]:
    async def override_get_session() -> AsyncGenerator[AsyncSession]:
        yield session

    app.dependency_overrides[real_get_session] = override_get_session
    app.dependency_overrides[get_catalog_client] = lambda: catalog
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()
