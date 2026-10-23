"""Datos de prueba REALES del flujo completo de Incubus (solo DESARROLLO).

Por cada orden recorre, contra la API HTTP de Incubus y con la sesion del
administrador de desarrollo (login de Leo + DPoP ES256), todas las etapas:
pre-recepcion -> turno/cola -> recepcion (borrador, preanaliticos, cierre) ->
impresion de etiquetas -> toma de muestras -> recepcion de laboratorio ->
captura -> validacion por area -> orden finalizada (y PDF disponible).

Uso, desde `backend/`:
    uv run python -m scripts.seed_demo_flow
    uv run python -m scripts.seed_demo_flow --document-type CC \
        --document-number 792083643 --count 10

Sin credenciales en el codigo: el usuario/clave del administrador salen de las
variables de entorno LEO_ADMIN_USERNAME / LEO_ADMIN_PASSWORD o del `.env` de
Leo (`--leo-env`, por defecto `../../leo/backend/.env`).
"""

import argparse
import asyncio
import base64
import json
import os
import random
import sys
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import httpx
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature

BACKEND_DIR = Path(__file__).resolve().parents[1]
DEFAULT_LEO_ENV = BACKEND_DIR.parents[1] / "leo" / "backend" / ".env"
PATIENT_IN_FIELDS = (
    "document_type",
    "document_number",
    "first_name",
    "second_name",
    "first_last_name",
    "second_last_name",
    "sex",
    "birth_date",
    "blood_type",
)
ACTIVE_STATUSES = (
    "pre_recepcion",
    "en_atencion_recepcion",
    "en_espera_impresion",
    "en_espera_toma_muestras",
    "en_atencion_toma_muestras",
    "toma_finalizada",
    "en_laboratorio",
)
# Datos que exige el cierre de recepcion; si faltan se completan (como la secretaria).
DEMO_DEMOGRAPHICS = {
    "sex": "F",
    "birth_date": "1990-05-05",
    "birth_place": "Bogota",
    "blood_type": "O+",
    "email": "paciente.demo@example.com",
    "phone": "3001234567",
    "address": "Calle 1 # 2-3",
}


class SeedError(Exception):
    """Error legible para quien ejecuta el script (sin trazas ni respuestas crudas)."""


# ------------------------------------------------------------------ entorno


def read_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            values[key.strip()] = value.strip().strip("'\"")
    return values


def admin_credentials(leo_env: Path) -> tuple[str, str]:
    file_values = read_env_file(leo_env)
    user = os.environ.get("LEO_ADMIN_USERNAME") or file_values.get("LEO_ADMIN_USERNAME")
    password = os.environ.get("LEO_ADMIN_PASSWORD") or file_values.get(
        "LEO_ADMIN_PASSWORD"
    )
    if not user or not password:
        raise SeedError(
            "No encuentro el administrador de desarrollo. Define LEO_ADMIN_USERNAME y "
            f"LEO_ADMIN_PASSWORD o revisa el archivo {leo_env} (opcion --leo-env)."
        )
    return user, password


# ------------------------------------------------------------ sesion + DPoP


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def describe_error(method: str, path: str, response: httpx.Response) -> str:
    """Mensaje legible de un error de la API (nunca la respuesta cruda)."""
    message = None
    try:
        body = response.json()
        message = body.get("message")
        if message is None and isinstance(body.get("detail"), list):
            message = "; ".join(
                f"{'.'.join(str(p) for p in d.get('loc', [])[1:])}: {d.get('msg')}"
                for d in body["detail"]
            )
        elif message is None and isinstance(body.get("detail"), str):
            message = body["detail"]
    except ValueError:
        pass
    return (
        f"{method} {path} fallo (HTTP {response.status_code}): "
        f"{message or 'sin detalle'}"
    )


class Session:
    """Sesion BFF de Incubus: login en Leo con DPoP ES256 y cookies del backend."""

    def __init__(self, api_url: str, leo_api: str, login: str, password: str):
        self.api = api_url.rstrip("/")
        self.leo_api = leo_api.rstrip("/")
        self._login, self._password = login, password
        self.key = ec.generate_private_key(ec.SECP256R1())
        numbers = self.key.public_key().public_numbers()
        self.jwk = {
            "kty": "EC",
            "crv": "P-256",
            "x": _b64(numbers.x.to_bytes(32, "big")),
            "y": _b64(numbers.y.to_bytes(32, "big")),
        }
        self.http = httpx.Client(timeout=60)
        self.leo = httpx.Client(timeout=30)

    def _proof(self, method: str, url: str) -> str:
        header = _b64(
            json.dumps(
                {"typ": "dpop+jwt", "alg": "ES256", "jwk": self.jwk},
                separators=(",", ":"),
            ).encode()
        )
        payload = _b64(
            json.dumps(
                {
                    "htm": method,
                    "htu": url.split("?")[0],
                    "iat": int(time.time()),
                    "jti": uuid.uuid4().hex,
                },
                separators=(",", ":"),
            ).encode()
        )
        r, s = decode_dss_signature(
            self.key.sign(f"{header}.{payload}".encode(), ec.ECDSA(hashes.SHA256()))
        )
        signature = _b64(r.to_bytes(32, "big") + s.to_bytes(32, "big"))
        return f"{header}.{payload}.{signature}"

    def _send(
        self, client: httpx.Client, method: str, url: str, **kw
    ) -> httpx.Response:
        headers = dict(kw.pop("headers", {}))
        headers["DPoP"] = self._proof(method, url)
        try:
            return client.request(method, url, headers=headers, **kw)
        except httpx.HTTPError as exc:
            raise SeedError(
                f"No pude conectar con {url.split('?')[0]}. Verifica que el servicio "
                "este arrancado."
            ) from exc

    def login(self) -> None:
        self.http.cookies.clear()
        self.leo.cookies.clear()
        r = self._send(self.http, "GET", f"{self.api}/auth/login")
        if r.status_code != 200:
            raise SeedError(f"Incubus no inicio el login (HTTP {r.status_code}).")
        query = parse_qs(urlsplit(r.json()["authorize_url"]).query)
        r = self._send(
            self.leo,
            "POST",
            f"{self.leo_api}/auth/login",
            json={"login": self._login, "password": self._password},
        )
        if r.status_code != 200:
            raise SeedError(
                "Leo rechazo las credenciales del administrador de desarrollo "
                f"(HTTP {r.status_code})."
            )
        keys = (
            "client_id",
            "redirect_uri",
            "state",
            "code_challenge",
            "code_challenge_method",
            "dpop_jkt",
        )
        r = self._send(
            self.leo,
            "POST",
            f"{self.leo_api}/auth/authorize",
            json={k: query[k][0] for k in keys},
        )
        if r.status_code != 200:
            raise SeedError(f"Leo no autorizo a Incubus (HTTP {r.status_code}).")
        callback = parse_qs(urlsplit(r.json()["redirect_to"]).query)
        r = self._send(
            self.http,
            "GET",
            f"{self.api}/auth/callback",
            params={"code": callback["code"][0], "state": callback["state"][0]},
        )
        if r.status_code != 200:
            raise SeedError(f"Incubus no completo el login (HTTP {r.status_code}).")

    def call(
        self, method: str, path: str, *, ok: tuple[int, ...] = (200, 201), **kw
    ) -> httpx.Response:
        url = f"{self.api}{path}"
        response = self._send(self.http, method, url, **kw)
        if response.status_code == 401:  # token vencido: renueva la sesion una vez
            self.login()
            response = self._send(self.http, method, url, **kw)
        if response.status_code not in ok:
            raise SeedError(describe_error(method, path, response))
        return response

    def json(self, method: str, path: str, **kw):
        return self.call(method, path, **kw).json()


# ------------------------------------------------------------------ catalogo


@dataclass(frozen=True)
class CatalogTest:
    code: str
    name: str
    area_id: str


async def load_catalog() -> tuple[list[CatalogTest], list[dict], list[dict]]:
    """Examenes activos con plantilla de resultados, tubo y area con encargado.

    Lee el catalogo de Vladimir con el mismo cliente (y credenciales de servicio)
    que usa Incubus. Devuelve (examenes, areas con encargado, personal)."""
    from app.modules.catalog_client.client import get_catalog_client

    catalog = get_catalog_client()
    areas = await catalog.areas_with_managers()
    managed = {a["id"] for a in areas if a.get("manager_staff_id")}
    gate = asyncio.Semaphore(8)

    async def check(item: dict) -> CatalogTest | None:
        version = item.get("result_template_version_id")
        if not item.get("is_active", True) or not version:
            return None
        if str(item.get("area_id")) not in managed:
            return None
        async with gate:
            full = await catalog.get_test_by_code(item["code"])
            if not full or not full.get("sample_types"):
                return None
            structure = await catalog.template_structure(str(version))
        if not any(a["result_type"] != "calculated" for a in structure["analytes"]):
            return None
        return CatalogTest(item["code"], item["name"], str(item["area_id"]))

    items = await catalog.search_tests(None, limit=200)
    eligible = [t for t in await asyncio.gather(*map(check, items)) if t]
    return eligible, areas, await catalog.list_staff()


def read_catalog():
    try:
        return asyncio.run(load_catalog())
    except Exception as exc:  # catalogo / Leo caidos: mensaje legible
        raise SeedError(
            f"No pude leer el catalogo de Vladimir ({getattr(exc, 'message', exc)}). "
            "Verifica que Vladimir (8000) y Leo (8100) esten arrancados y que "
            "backend/.env de Incubus este completo."
        ) from exc


# ------------------------------------------------------------ pura/testeable


def pick_test_codes(
    eligible: list[CatalogTest], rand: random.Random, max_tests: int = 4
) -> list[str]:
    """1 a `max_tests` examenes distintos al azar."""
    count = rand.randint(1, min(max_tests, len(eligible)))
    return [t.code for t in rand.sample(eligible, count)]


def precondition_checks(
    preconditions: list[dict], rand: random.Random, stage: str
) -> list[dict]:
    """Respuesta a cada preanalitico: casi siempre 'cumple'; a veces 'no cumple'
    con la nota obligatoria."""
    out = []
    for item in preconditions:
        met = rand.random() > 0.12
        note = (
            None if met else f"Paciente refiere no cumplir «{item['name']}» ({stage})."
        )
        out.append({"key": item["key"], "met": met, "note": note})
    return out


# --------------------------------------------------------------------- flujo


def ensure_patient(session: Session, args: argparse.Namespace) -> dict:
    r = session.call(
        "GET",
        "/api/v1/patients/lookup",
        params={
            "document_type": args.document_type,
            "document_number": args.document_number,
        },
        ok=(200, 404),
    )
    if r.status_code == 200:
        return r.json()
    if not args.create_patient:
        raise SeedError(
            f"El paciente {args.document_type} {args.document_number} no existe en "
            "Incubus. No lo creo por mi cuenta: ejecuta con --create-patient o usa un "
            "documento existente (--document-type / --document-number)."
        )
    return {
        "document_type": args.document_type,
        "document_number": args.document_number,
        "first_name": "Paciente",
        "first_last_name": "Demo",
    }


def pending_entry(session: Session, patient: dict) -> dict | None:
    """Turno sin terminar del paciente (p. ej. una corrida interrumpida)."""
    rows = session.json(
        "GET", "/api/v1/queue", params=[("status", s) for s in ACTIVE_STATUSES]
    )
    return next(
        (
            e
            for e in rows
            if e["patient"]["document_type"] == patient["document_type"]
            and e["patient"]["document_number"] == patient["document_number"]
        ),
        None,
    )


def enter_queue(session: Session, patient: dict, rand: random.Random) -> dict:
    priority = rand.choice(session.json("GET", "/api/v1/priorities"))
    body = {
        "patient": {k: patient[k] for k in PATIENT_IN_FIELDS if patient.get(k)},
        "priority_id": priority["id"],
    }
    r = session.call("POST", "/api/v1/queue", json=body, ok=(201, 409))
    if r.status_code == 409:
        raise SeedError(
            "El paciente ya tiene un turno activo en la cola; terminalo o retiralo "
            "antes de generar datos."
        )
    return r.json()


def complete_demographics(session: Session, entry: dict) -> None:
    patient = entry["patient"]
    missing = {k: v for k, v in DEMO_DEMOGRAPHICS.items() if not patient.get(k)}
    if missing:
        session.json("PATCH", f"/api/v1/patients/{patient['id']}", json=missing)


def run_order(
    session: Session,
    patient: dict,
    eligible: list[CatalogTest],
    sampler: dict,
    validators: dict[str, dict],
    rand: random.Random,
) -> dict:
    # Pre-recepcion + turno: entra a la cola y recepcion toma al paciente (la
    # persona autenticada queda como duena del turno).
    entry_id = enter_queue(session, patient, rand)["id"]
    session.json("POST", f"/api/v1/queue/{entry_id}/claim", json={})
    complete_demographics(session, session.json("GET", f"/api/v1/queue/{entry_id}"))
    codes = pick_test_codes(eligible, rand)
    session.json("PUT", f"/api/v1/queue/{entry_id}/draft", json={"test_codes": codes})
    preview = session.json("POST", "/api/v1/orders/preview", json={"test_codes": codes})
    closed = session.json(
        "POST",
        f"/api/v1/orders/close-reception/{entry_id}",
        json={
            "test_codes": codes,
            "precondition_checks": precondition_checks(
                preview["preconditions"], rand, "recepcion"
            ),
        },
    )
    number = closed["order_number"]
    # Etiquetas: se crean los tubos y se asigna el profesional de toma.
    session.json("POST", f"/api/v1/orders/by-entry/{entry_id}/samples")
    session.json(
        "POST",
        f"/api/v1/orders/by-entry/{entry_id}/print-labels",
        json={"professional_id": sampler["id"], "professional_name": sampler["name"]},
    )
    # Toma de muestras: el profesional asignado toma al paciente y los tubos.
    session.json(
        "POST",
        f"/api/v1/queue/{entry_id}/claim",
        json={"professional_id": sampler["id"]},
    )
    detail = session.json("GET", f"/api/v1/orders/by-entry/{entry_id}")
    if detail["preconditions"]:
        session.json(
            "POST",
            f"/api/v1/orders/by-entry/{entry_id}/precondition-checks",
            json={
                "stage": "sampling",
                "checks": precondition_checks(detail["preconditions"], rand, "toma"),
            },
        )
    for sample in detail["samples"]:
        session.json("POST", f"/api/v1/orders/samples/{sample['id']}/collect")
    session.json("POST", f"/api/v1/queue/{entry_id}/finish-sampling")
    # Recepcion en laboratorio: check de entrada de cada tubo.
    for sample in detail["samples"]:
        session.json("POST", f"/api/v1/orders/samples/{sample['id']}/receive")
    return finish_in_lab(session, entry_id, number, codes, validators, rand)


def finish_in_lab(
    session: Session,
    entry_id: str,
    number: str,
    codes: list[str],
    validators: dict[str, dict],
    rand: random.Random,
) -> dict:
    """Captura + validacion: cada area la valida su encargado. Deja la orden
    finalizada y comprueba que su PDF este disponible."""
    from scripts.demo_values import values_for_test

    flagged = 0
    for validator in validators.values():
        r = session.call(
            "GET",
            f"/api/v1/results/orders/{entry_id}",
            params={"professional_id": validator["id"]},
            ok=(200, 403),  # 403: la orden no tiene examenes de esa area
        )
        if r.status_code != 200:
            continue
        for item in r.json()["tests"]:
            if item["validation_status"] == "validated":
                continue  # corrida retomada: ya validado
            path = f"/api/v1/results/tests/{item['order_test_id']}"
            test = session.json(
                "GET", path, params={"professional_id": validator["id"]}
            )
            body = {
                "professional_id": validator["id"],
                "professional_name": validator["name"],
                "values": values_for_test(
                    test["results"], test["patient"]["sex"], None, rand
                ),
            }
            session.json("PUT", f"{path}/values", json=body)
            done = session.json("POST", f"{path}/validate", json=body)
            flagged += sum(
                1 for x in done["results"] if x.get("flag") not in (None, "normal")
            )
    status = session.json("GET", f"/api/v1/queue/{entry_id}")["status"]
    if status != "finalizada":
        raise SeedError(f"La orden {number} no quedo finalizada (estado «{status}»).")
    pdf = session.call("GET", f"/api/v1/delivery/orders/{number}/report.pdf")
    if not pdf.content.startswith(b"%PDF"):
        raise SeedError(f"El PDF de la orden {number} no es valido.")
    return {
        "order_number": number,
        "tests": codes,
        "status": status,
        "flags": flagged,
        "pdf_bytes": len(pdf.content),
    }


# ----------------------------------------------------------------------- cli


# ----------------------------------------------------------------------- cli


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="python -m scripts.seed_demo_flow",
        description="Genera ordenes FINALIZADAS de prueba recorriendo el flujo "
        "completo de Incubus por su API (solo desarrollo).",
    )
    p.add_argument("--document-type", default="CC")
    p.add_argument("--document-number", default="792083643")
    p.add_argument("--count", type=int, default=10)
    p.add_argument("--seed", type=int, help="semilla del azar (reproducible)")
    p.add_argument("--api-url", default="http://localhost:8001")
    p.add_argument("--leo-api-url", help="por defecto LEO_API_URL de backend/.env")
    p.add_argument("--leo-env", type=Path, default=DEFAULT_LEO_ENV)
    p.add_argument("--create-patient", action="store_true")
    args = p.parse_args(argv)
    if not 1 <= args.count <= 200:
        p.error("--count debe estar entre 1 y 200.")
    return args


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="replace")
    args = parse_args(argv)
    rand = random.Random(args.seed)
    results: list[dict] = []
    try:
        leo_api = args.leo_api_url or read_env_file(BACKEND_DIR / ".env").get(
            "LEO_API_URL", "http://localhost:8100/api/v1"
        )
        login, password = admin_credentials(args.leo_env)
        print("[catalogo] Leyendo examenes con plantilla de resultados...")
        eligible, areas, staff = read_catalog()
        if not eligible:
            raise SeedError("El catalogo no tiene examenes con plantilla activa.")
        samplers = [
            s for s in staff if "toma de muestras" in (s["job_title"] or "").casefold()
        ]
        if not samplers:
            raise SeedError("No hay personal de toma de muestras en el catalogo.")
        validators = {
            a["id"]: {"id": a["manager_staff_id"], "name": a["manager_name"]}
            for a in areas
            if a.get("manager_staff_id")
        }
        print(
            f"[catalogo] {len(eligible)} examenes elegibles, {len(validators)} areas."
        )

        session = Session(args.api_url, leo_api, login, password)
        session.login()
        patient = ensure_patient(session, args)
        print(f"[paciente] {args.document_type} {args.document_number} listo.")
        for n in range(1, args.count + 1):
            stuck = pending_entry(session, patient)
            if stuck and stuck["status"] == "en_laboratorio":
                # Corrida interrumpida: se retoma la captura y validacion.
                order = session.json("GET", f"/api/v1/orders/by-entry/{stuck['id']}")
                result = finish_in_lab(
                    session,
                    stuck["id"],
                    order["order_number"],
                    [t["code"] for t in order["tests"]],
                    validators,
                    rand,
                )
            elif stuck:
                raise SeedError(
                    f"El paciente ya tiene un turno sin terminar (estado "
                    f"«{stuck['status']}», orden {stuck.get('order_number') or '-'}). "
                    "Termina o retira ese turno en Incubus y vuelve a ejecutar."
                )
            else:
                result = run_order(
                    session, patient, eligible, rand.choice(samplers), validators, rand
                )
            results.append(result)
            print(
                f"[{n}/{args.count}] orden {result['order_number']} "
                f"{result['status']} | pruebas: {', '.join(result['tests'])} | "
                f"banderas: {result['flags']} | PDF {result['pdf_bytes']} B"
            )
    except SeedError as exc:
        print(f"\nERROR: {exc}", file=sys.stderr)
        print(f"Ordenes finalizadas antes del error: {len(results)}.", file=sys.stderr)
        return 1
    print(
        f"\nListo: {len(results)} ordenes finalizadas para "
        f"{args.document_type} {args.document_number}."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
