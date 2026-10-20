import asyncio

from app.modules.orders.tests.test_sampling import PRO, _printed
from app.modules.queue import service
from app.testing import Rendezvous

CLAIM = {"actor": "Luis Perez", "professional_id": PRO["professional_id"]}


def _overlap_unlocked_reads(monkeypatch) -> None:
    """Las lecturas SIN bloqueo de la entrada se solapan entre transacciones: si
    la validacion se hiciera con una lectura asi, ambas pasarian (TOCTOU)."""
    rendezvous = Rendezvous()
    original = service.get_entry

    async def spy(session, entry_id, *, lock=False):
        entry = await original(session, entry_id, lock=lock)
        if not lock:
            await rendezvous.wait()
        return entry

    monkeypatch.setattr(service, "get_entry", spy)


async def test_dos_claims_simultaneos_de_la_toma_uno_200_y_otro_409(
    committed_client, catalog, monkeypatch
):
    client = committed_client
    entry_id, _ = await _printed(client, catalog)
    _overlap_unlocked_reads(monkeypatch)
    url = f"/api/v1/queue/{entry_id}/claim"
    results = await asyncio.gather(*(client.post(url, json=CLAIM) for _ in range(3)))
    codes = sorted(r.status_code for r in results)
    assert codes == [200, 409, 409], [r.text for r in results]
    hist = (await client.get(f"/api/v1/queue/{entry_id}/history")).json()
    assert [h["to_status"] for h in hist].count("en_atencion_toma_muestras") == 1


async def test_dos_claims_simultaneos_de_recepcion_uno_200_y_otro_409(
    committed_client, monkeypatch
):
    client = committed_client
    pr = {p["code"]: p["id"] for p in (await client.get("/api/v1/priorities")).json()}
    entry = (
        await client.post(
            "/api/v1/queue",
            json={
                "patient": {
                    "document_number": "99887766",
                    "first_name": "A",
                    "first_last_name": "B",
                },
                "priority_id": pr["media"],
            },
        )
    ).json()
    _overlap_unlocked_reads(monkeypatch)
    url = f"/api/v1/queue/{entry['id']}/claim"
    results = await asyncio.gather(
        *(client.post(url, json={"actor": f"u{i}"}) for i in range(3))
    )
    assert sorted(r.status_code for r in results) == [200, 409, 409]
