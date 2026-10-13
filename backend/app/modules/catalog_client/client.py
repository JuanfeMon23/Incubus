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
        params: dict[str, Any] = {"active": "true", "page_size": limit}
        if q:
            params["q"] = q
        return (await self._get("/lab-tests", params))["items"]

    async def get_test_by_code(self, code: str) -> dict | None:
        items = await self.search_tests(code, limit=50)
        return next(
            (t for t in items if t["code"] == code and t.get("is_active", True)), None
        )

    async def precondition_categories(self) -> dict[str, str]:
        """`id` de precondicion/item -> `category` (el examen no la expone)."""
        page = await self._get("/preconditions", {"page_size": _PAGE_SIZE})
        result: dict[str, str] = {}
        for root in page["items"]:
            result[root["id"]] = root["category"]
            for item in root.get("items") or []:
                result[item["id"]] = item["category"]
        return result


def get_catalog_client() -> CatalogClient:
    return CatalogClient(get_settings().vladimir_api_url)
