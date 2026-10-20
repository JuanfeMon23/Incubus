"""Dos validaciones simultaneas de los dos ultimos examenes: la orden debe cerrar."""

import asyncio

from app.modules.results import service as results_service
from app.modules.results.tests.helpers import order_in_laboratory
from app.testing import Rendezvous


async def test_dos_validaciones_concurrentes_de_los_ultimos_examenes_finalizan_la_orden(
    committed_client, catalog, monkeypatch
):
    client = committed_client
    entry_id, _ = await order_in_laboratory(client, catalog, ("GLU", "VIH"))
    ids = {}
    for pro in ("staff-qc", "staff-hem"):
        queue = (
            await client.get("/api/v1/results/queue", params={"professional_id": pro})
        ).json()
        ids[pro] = queue[0]["tests"][0]["order_test_id"]

    rendezvous = Rendezvous()
    original = results_service.ensure_structure

    async def slow(session, catalog_, test):
        rows = await original(session, catalog_, test)
        await rendezvous.wait()
        return rows

    monkeypatch.setattr(results_service, "ensure_structure", slow)

    def validate(pro, values):
        return client.post(
            f"/api/v1/results/tests/{ids[pro]}/validate",
            json={"professional_id": pro, "professional_name": pro, "values": values},
        )

    r1, r2 = await asyncio.gather(
        validate("staff-qc", {"GLU": "90"}), validate("staff-hem", {"VIH": "neg"})
    )
    assert r1.status_code == r2.status_code == 200, (r1.text, r2.text)
    assert sorted([r1.json()["order_finalized"], r2.json()["order_finalized"]]) == [
        False,
        True,
    ]
    state = (await client.get(f"/api/v1/queue/{entry_id}")).json()["status"]
    assert state == "finalizada"
