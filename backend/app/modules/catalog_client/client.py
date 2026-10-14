"""Cliente HTTP del catalogo de Vladimir (`/api/v1`).

Vladimir es la fuente del catalogo; Incubus solo lo consulta y guarda snapshot
en la orden. El cliente es inyectable (`get_catalog_client`) para pruebas.
"""

from typing import Any

import httpx

from app.core.config import get_settings
from app.core.exceptions import AppError

_PAGE_SIZE = 200


class CatalogUnavailableError(AppError):
    status_code = 502
    code = "catalog_unavailable"


class CatalogClient:
    def __init__(
        self, base_url: str, transport: httpx.AsyncBaseTransport | None = None
    ):
        self._base_url = base_url.rstrip("/")
        self._transport = transport

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        try:
            async with httpx.AsyncClient(
                base_url=self._base_url, timeout=10.0, transport=self._transport
            ) as http:
                response = await http.get(f"/api/v1{path}", params=params)
                response.raise_for_status()
                return response.json()
        except httpx.HTTPError as exc:
            raise CatalogUnavailableError(
                "No se pudo consultar el catalogo de Vladimir.", {"path": path}
            ) from exc

    async def search_tests(self, q: str | None, limit: int = 20) -> list[dict]:
        """Busca examenes activos por nombre o codigo.

        Los codigos usan guion bajo (`ACIDO_URICO`); si quien busca escribe con
        espacios y no hay resultados, se reintenta con guion bajo.
        """
        params: dict[str, Any] = {"active": "true", "page_size": limit}
        if q:
            params["q"] = q
        items = (await self._get("/lab-tests", params))["items"]
        if not items and q and " " in q.strip():
            params["q"] = "_".join(q.split())
            items = (await self._get("/lab-tests", params))["items"]
        return items

    async def get_test_by_code(self, code: str) -> dict | None:
        """Examen activo con sus precondiciones y tipos de muestra.

        El listado `/lab-tests` de Vladimir no hidrata las asignaciones (llegan
        vacias), asi que se piden a los sub-recursos del examen.
        """
        items = await self.search_tests(code, limit=50)
        test = next(
            (t for t in items if t["code"] == code and t.get("is_active", True)), None
        )
        if test is None:
            return None
        base = f"/lab-tests/{test['id']}"
        return {
            **test,
            "preconditions": await self._get(f"{base}/preconditions"),
            "sample_types": await self._get(f"{base}/sample-types"),
        }

    async def precondition_categories(self) -> dict[str, str]:
        """`id` de precondicion/item -> `category` (el examen no la expone)."""
        page = await self._get("/preconditions", {"page_size": _PAGE_SIZE})
        result: dict[str, str] = {}
        for root in page["items"]:
            result[root["id"]] = root["category"]
            for item in root.get("items") or []:
                result[item["id"]] = item["category"]
        return result

    async def sample_types_by_id(self) -> dict[str, dict]:
        """`id` del tipo de muestra -> detalle (nombre, color, orden de extraccion)."""
        samples = await self._get("/samples", {"page_size": _PAGE_SIZE})
        result: dict[str, dict] = {}
        for sample in samples["items"]:
            page = await self._get(
                f"/samples/{sample['id']}/types", {"page_size": _PAGE_SIZE}
            )
            for item in page["items"]:
                result[item["id"]] = item
        return result

    async def areas_by_id(self) -> dict[str, str]:
        """`id` del area -> acronimo (`code`) con el que se rotula el tubo."""
        page = await self._get("/lab-areas", {"page_size": _PAGE_SIZE})
        return {a["id"]: a["code"] for a in page["items"]}

    async def list_staff(self) -> list[dict]:
        """Personal activo (para elegir al profesional de toma de muestras)."""
        page = await self._get("/staff", {"page_size": _PAGE_SIZE, "active": "true"})
        return [
            {
                "id": s["id"],
                "name": f"{s['first_name']} {s['last_name']}",
                "job_title": s.get("job_title"),
            }
            for s in page["items"]
        ]


def get_catalog_client() -> CatalogClient:
    return CatalogClient(get_settings().vladimir_api_url)
