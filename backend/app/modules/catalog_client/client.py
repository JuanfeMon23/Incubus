"""Cliente HTTP del catalogo de Vladimir (`/api/v1`).

Vladimir es la fuente del catalogo; Incubus solo lo consulta y guarda snapshot
en la orden. El cliente es inyectable (`get_catalog_client`) para pruebas.
"""

import asyncio
from typing import Any

import httpx
from leo_sdk import (
    LeoClient,
    LeoError,
    LeoSettings,
    ServiceAccessDenied,
    ServiceTokenProvider,
)

from app.core.config import get_settings
from app.core.exceptions import AppError

_PAGE_SIZE = 200

# Slug de la app de Vladimir en Leo: audiencia del token de servicio.
VLADIMIR_AUDIENCE = "vladimir"

# (base_url, version_id) -> estructura de plantilla publicada (inmutable).
_TEMPLATE_CACHE: dict[tuple[str, str], dict] = {}


class CatalogUnavailableError(AppError):
    status_code = 502
    code = "catalog_unavailable"


class CatalogForbiddenError(AppError):
    status_code = 502
    code = "catalog_forbidden"


_FORBIDDEN_MESSAGE = (
    "Incubus no tiene permiso para consultar el catálogo de Vladimir. "
    "Pídele a un administrador de Leo que le conceda acceso."
)


class CatalogClient:
    def __init__(
        self,
        base_url: str,
        transport: httpx.AsyncBaseTransport | None = None,
        auth: httpx.Auth | None = None,
    ):
        self._base_url = base_url.rstrip("/")
        self._transport = transport
        self._auth = auth

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        try:
            async with httpx.AsyncClient(
                base_url=self._base_url,
                timeout=10.0,
                transport=self._transport,
                auth=self._auth,
            ) as http:
                response = await http.get(f"/api/v1{path}", params=params)
                if response.status_code in (401, 403):
                    raise CatalogForbiddenError(_FORBIDDEN_MESSAGE, {"path": path})
                response.raise_for_status()
                return response.json()
        except ServiceAccessDenied as exc:
            raise CatalogForbiddenError(_FORBIDDEN_MESSAGE, {"path": path}) from exc
        except LeoError as exc:  # Leo caido o credenciales de la app rechazadas
            raise CatalogUnavailableError(
                "No se pudo autenticar con Leo para consultar el catalogo de "
                "Vladimir. Revisa que Leo este disponible y las credenciales de "
                "Incubus.",
                {"path": path},
            ) from exc
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

    async def areas_with_managers(self) -> list[dict]:
        """Areas con su encargado actual (el profesional que valida)."""
        page = await self._get("/lab-areas", {"page_size": _PAGE_SIZE})
        out = []
        for area in page["items"]:
            manager = area.get("current_manager") or {}
            out.append(
                {
                    "id": area["id"],
                    "code": area["code"],
                    "name": area["name"],
                    "manager_staff_id": manager.get("staff_id"),
                    "manager_name": manager.get("staff_name"),
                }
            )
        return out

    async def warm_templates(self, version_ids: list[str]) -> None:
        """Precarga plantillas en cache (en segundo plano, sin propagar errores)."""
        results = await asyncio.gather(
            *[self.template_structure(v) for v in dict.fromkeys(version_ids)],
            return_exceptions=True,
        )
        del results

    async def template_structure(self, version_id: str) -> dict:
        """Plantilla publicada de un examen: secciones, analitos, opciones y rangos.

        Una version publicada es inmutable, asi que se guarda en memoria del
        proceso; las llamadas internas se hacen en paralelo.
        """
        cached = _TEMPLATE_CACHE.get((self._base_url, version_id))
        if cached is not None:
            return cached
        version = await self._get(f"/result-template-versions/{version_id}")
        base = (
            f"/result-templates/{version['result_template_id']}/versions/{version_id}"
        )
        sections_raw, template_analytes, analytes_page = await asyncio.gather(
            self._get(f"{base}/sections"),
            self._get(f"{base}/analytes"),
            self._get("/analytes", {"page_size": _PAGE_SIZE}),
        )
        sections = {s["id"]: s for s in sections_raw}
        analytes = {a["id"]: a for a in analytes_page["items"]}
        active = [
            ta
            for ta in sorted(template_analytes, key=lambda x: x["sort_order"])
            if ta.get("is_active", True)
        ]
        set_ids = sorted(
            {ta["option_set_id"] for ta in active if ta.get("option_set_id")}
        )
        options_pages, ranges_lists = await asyncio.gather(
            asyncio.gather(
                *[
                    self._get(
                        f"/result-option-sets/{sid}/options", {"page_size": _PAGE_SIZE}
                    )
                    for sid in set_ids
                ]
            ),
            asyncio.gather(
                *[
                    self._get(f"{base}/analytes/{ta['id']}/reference-ranges")
                    for ta in active
                ]
            ),
        )
        options_by_set = {
            sid: [
                {
                    "id": o["id"],
                    "label": o["label"],
                    "is_abnormal": o.get("is_abnormal", False),
                }
                for o in sorted(page["items"], key=lambda o: o["sort_order"])
                if o.get("is_active", True)
            ]
            for sid, page in zip(set_ids, options_pages, strict=True)
        }
        out = []
        for ta, ranges in zip(active, ranges_lists, strict=True):
            analyte = analytes.get(ta["analyte_id"], {})
            section = sections.get(ta.get("section_id") or "", {})
            out.append(
                {
                    "code": analyte.get("code", ta["analyte_id"]),
                    "name": analyte.get("name", ta["analyte_id"]),
                    "section": section.get("name"),
                    "sort_order": ta["sort_order"],
                    "result_type": ta["result_type"],
                    "unit": ta.get("unit"),
                    "decimals": ta.get("decimals"),
                    "options": options_by_set.get(ta.get("option_set_id") or "", []),
                    "formula": ta.get("formula"),
                    "is_required": ta.get("is_required", True),
                    "is_reportable": ta.get("is_reportable", True),
                    "ranges": [r for r in ranges if r.get("is_active", True)],
                }
            )
        structure = {"version_id": version_id, "analytes": out}
        if version.get("status", "published") == "published":
            _TEMPLATE_CACHE[(self._base_url, version_id)] = structure
        return structure


_leo: tuple[LeoClient, ServiceTokenProvider] | None = None


def _service_token_provider() -> ServiceTokenProvider:
    """Un unico proveedor de tokens de servicio por proceso (perezoso)."""
    global _leo
    if _leo is None:
        leo = LeoClient(LeoSettings())
        _leo = (leo, ServiceTokenProvider(leo))
    return _leo[1]


async def close_token_provider() -> None:
    """Cierra el cliente HTTP de Leo (apagado de la app)."""
    global _leo
    if _leo is not None:
        leo, _leo = _leo[0], None
        await leo.aclose()


def get_catalog_client() -> CatalogClient:
    return CatalogClient(
        get_settings().vladimir_api_url,
        auth=_service_token_provider().auth(VLADIMIR_AUDIENCE),
    )
