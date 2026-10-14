import httpx

from app.modules.catalog_client.client import CatalogClient


def make_client() -> CatalogClient:
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/api/v1/lab-tests":
            return httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": "t1",
                            "code": "COL",
                            "name": "Colesterol",
                            "is_active": True,
                            "preconditions": [],
                            "sample_types": [],
                        }
                    ]
                },
            )
        if path == "/api/v1/lab-tests/t1/preconditions":
            return httpx.Response(
                200, json=[{"precondition_id": "p1", "name": "Ayuno"}]
            )
        if path == "/api/v1/lab-tests/t1/sample-types":
            return httpx.Response(
                200, json=[{"sample_type_id": "s1", "is_preferred": True}]
            )
        return httpx.Response(404)

    return CatalogClient("http://vladimir", transport=httpx.MockTransport(handler))


async def test_get_test_by_code_trae_precondiciones_y_tipos_de_muestra():
    # El listado de Vladimir no hidrata las asignaciones: salen de sus sub-recursos.
    test = await make_client().get_test_by_code("COL")
    assert test is not None
    assert test["preconditions"][0]["precondition_id"] == "p1"
    assert test["sample_types"][0]["sample_type_id"] == "s1"


async def test_get_test_by_code_inexistente():
    assert await make_client().get_test_by_code("NOPE") is None
