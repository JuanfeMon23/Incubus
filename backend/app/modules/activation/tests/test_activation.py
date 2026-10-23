"""Codigo de activacion: emision, verificacion (ataques) y listado de ordenes."""

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text

from app.modules.activation import service
from app.modules.activation.service import ALPHABET, normalize_code
from app.modules.results.tests.helpers import PATIENT, order_in_laboratory

API = "/api/v1/delivery"
GOOD = {
    "document_type": "CC",
    "document_number": PATIENT["document_number"],
    "birth_date": PATIENT["birth_date"],
}


@pytest.fixture(autouse=True)
def _fresh_limiter():
    service.limiter.reset()
    yield
    service.limiter.reset()


async def _order(client, catalog, tests=("GLU",)):
    extra: dict = {}
    entry_id, number = await order_in_laboratory(client, catalog, tests, extra)
    return entry_id, number, extra["activation_code"]


async def _verify(client, code, **over):
    return await client.post(
        f"{API}/activation/verify", json={"code": code, **GOOD, **over}
    )


# ------------------------------------------------------------------ emision


def test_generated_codes_use_the_unambiguous_alphabet_and_have_entropy():
    assert len(ALPHABET) == 32 and not set("0O1I") & set(ALPHABET)
    codes = {service.generate_code() for _ in range(500)}
    assert len(codes) == 500
    assert all(len(c) == 10 and set(c) <= set(ALPHABET) for c in codes)


def test_normalize_accepts_hyphen_case_and_spaces_and_rejects_ambiguous():
    assert normalize_code("abcde-fghjk") == "ABCDEFGHJK"
    assert normalize_code(" ABCDE FGHJK ") == "ABCDEFGHJK"
    assert normalize_code("ABCDE-FGHJ0") is None  # 0 no existe en el alfabeto
    assert normalize_code("ABCDE-FGHJ") is None  # corto


async def test_close_reception_returns_the_code_once_and_stores_only_a_hash(
    client, catalog, session
):
    _, _, shown = await _order(client, catalog)
    assert len(shown) == 11 and shown[5] == "-"
    row = (
        await session.execute(
            text("SELECT code_hash, used_at, expires_at FROM activation_codes")
        )
    ).one()
    raw = shown.replace("-", "")
    assert raw not in row.code_hash and row.code_hash != raw
    assert row.code_hash == service.hash_code(raw) and len(row.code_hash) == 64
    assert row.used_at is None
    assert timedelta(days=29) < row.expires_at - datetime.now(UTC) <= timedelta(days=30)


async def test_no_read_route_exposes_the_code(client, catalog):
    entry_id, number, shown = await _order(client, catalog)
    raw = shown.replace("-", "")
    for url in (
        f"/api/v1/orders/by-entry/{entry_id}",
        f"/api/v1/queue/{entry_id}",
        f"{API}/orders/{number}",
    ):
        body = (await client.get(url)).text
        assert raw not in body and shown not in body


# ------------------------------------------------------------- verificacion


async def test_verify_ok_marks_used_and_returns_minimal_patient(client, catalog):
    _, _, code = await _order(client, catalog)
    r = await _verify(client, code.lower())  # tolera minusculas
    assert r.status_code == 200, r.text
    assert r.json() == {
        "first_name": "MARIA",
        "second_name": None,
        "first_last_name": "RUIZ",
        "second_last_name": None,
        "document_type": "CC",
        "document_number": PATIENT["document_number"],
        "birth_date": "1990-06-15",
    }


async def test_a_used_code_cannot_be_reused(client, catalog):
    _, _, code = await _order(client, catalog)
    assert (await _verify(client, code)).status_code == 200
    assert (await _verify(client, code)).status_code == 404


async def test_expired_code_is_rejected(client, catalog, session):
    _, _, code = await _order(client, catalog)
    await session.execute(
        text(
            "UPDATE activation_codes SET created_at = now() - interval '2 days', "
            "expires_at = now() - interval '1 day'"
        )
    )
    assert (await _verify(client, code)).status_code == 404


@pytest.mark.parametrize(
    "wrong",
    [
        {"document_number": "9999999999"},
        {"document_type": "TI"},
        {"birth_date": "1990-06-16"},
    ],
)
async def test_any_wrong_datum_gives_the_same_404_and_does_not_burn_the_code(
    client, catalog, wrong
):
    _, _, code = await _order(client, catalog)
    bad = await _verify(client, code, **wrong)
    unknown = await _verify(client, "ZZZZZ-ZZZZZ")
    malformed = await _verify(client, "x")
    assert bad.status_code == unknown.status_code == malformed.status_code == 404
    assert bad.json() == unknown.json() == malformed.json()
    assert (await _verify(client, code)).status_code == 200  # sigue vigente


async def test_code_of_another_patient_does_not_verify(client, catalog, session):
    _, _, code = await _order(client, catalog)
    await session.execute(
        text(
            "INSERT INTO patients (document_type, document_number, first_name, "
            "first_last_name, birth_date) VALUES ('CC','5550001','OTRO','PACIENTE',"
            "'1990-06-15')"
        )
    )
    assert (await _verify(client, code, document_number="5550001")).status_code == 404


async def test_rate_limit_per_ip_and_document_blocks_even_the_right_code(
    client, catalog
):
    _, _, code = await _order(client, catalog)
    for _ in range(5):
        assert (await _verify(client, "AAAAA-AAAAA")).status_code == 404
    blocked = await _verify(client, code)
    assert blocked.status_code == 429
    assert blocked.json()["code"] == "too_many_attempts"
    # otro documento no queda afectado
    other = await _verify(client, "AAAAA-AAAAA", document_number="111")
    assert other.status_code == 404


async def test_requires_delivery_tag(client, leo):
    leo.grant()
    assert (await _verify(client, "AAAAA-AAAAA")).status_code == 403


async def test_concurrent_verifications_consume_the_code_exactly_once(
    committed_client, catalog
):
    client = committed_client
    _, _, code = await _order(client, catalog)
    results = await asyncio.gather(*[_verify(client, code) for _ in range(4)])
    assert sorted(r.status_code for r in results) == [200, 404, 404, 404]


# ----------------------------------------------------------- lista de ordenes


async def _finalize(client, number):
    queue = (
        await client.get(
            "/api/v1/results/queue", params={"professional_id": "staff-qc"}
        )
    ).json()
    order = next(o for o in queue if o["order_number"] == number)
    r = await client.post(
        f"/api/v1/results/tests/{order['tests'][0]['order_test_id']}/validate",
        json={
            "professional_id": "staff-qc",
            "professional_name": "Paola",
            "values": {"GLU": "95"},
        },
    )
    assert r.status_code == 200, r.text


async def test_orders_list_only_finalized_paginated_and_minimal(client, catalog):
    _, done, _ = await _order(client, catalog)
    url = f"{API}/patients/CC/{PATIENT['document_number']}/orders"
    assert (await client.get(url)).json()["items"] == []  # nada finalizado
    await _finalize(client, done)
    data = (await client.get(url)).json()
    assert data["total"] == 1 and data["page"] == 1 and data["page_size"] == 10
    (item,) = data["items"]
    assert set(item) == {
        "order_number",
        "date",
        "finalized_at",
        "status",
        "tests",
        "has_pdf",
    }
    assert item["order_number"] == done
    assert item["tests"] == ["Glucosa"] and item["has_pdf"] is True
    assert item["status"] == "finalizada"
    assert (await client.get(f"{API}/orders/{done}/report.pdf")).status_code == 200
    empty_page = (await client.get(url + "?page=2")).json()
    assert empty_page["items"] == [] and empty_page["total"] == 1


async def test_orders_list_unknown_patient_is_empty_and_params_are_bounded(client):
    r = await client.get(f"{API}/patients/CC/000/orders")
    assert r.status_code == 200 and r.json()["items"] == [] and r.json()["total"] == 0
    assert (
        await client.get(f"{API}/patients/CC/0/orders?page_size=500")
    ).status_code == 422
    assert (await client.get(f"{API}/patients/CC/0/orders?page=0")).status_code == 422
