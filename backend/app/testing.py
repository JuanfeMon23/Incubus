"""Utilidades compartidas solo para pruebas."""

import asyncio
import json
import time
from typing import Any
from uuid import uuid4

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
from leo_sdk.crypto import b64url_encode, jwk_thumbprint


class Rendezvous:
    """Fuerza a dos transacciones a solaparse en un punto concreto.

    Si no hay serializacion (falta un bloqueo), ambas llegan a `wait()` antes de
    continuar. Si una espera a la otra y esta no llega (porque un bloqueo la
    serializa), se libera por tiempo."""

    def __init__(self, timeout: float = 0.4) -> None:
        self.timeout = timeout
        self.arrived = 0
        self.both = asyncio.Event()

    async def wait(self) -> None:
        self.arrived += 1
        if self.arrived >= 2:
            self.both.set()
        try:
            await asyncio.wait_for(self.both.wait(), self.timeout)
        except TimeoutError:
            self.both.set()


# --- DPoP (llave de un "navegador" para firmar pruebas) -----------------------------


def _b64json(value: dict[str, Any]) -> str:
    return b64url_encode(json.dumps(value, separators=(",", ":")).encode("utf-8"))


class DpopKey:
    """Llave ES256 de un navegador de prueba: firma pruebas DPoP (RFC 9449)."""

    def __init__(self) -> None:
        self.private_key = ec.generate_private_key(ec.SECP256R1())
        numbers = self.private_key.public_key().public_numbers()
        self.public_jwk = {
            "kty": "EC",
            "crv": "P-256",
            "x": b64url_encode(numbers.x.to_bytes(32, "big")),
            "y": b64url_encode(numbers.y.to_bytes(32, "big")),
        }
        self.jkt = jwk_thumbprint(self.public_jwk)

    def _sign(self, signing_input: bytes) -> str:
        der = self.private_key.sign(signing_input, ec.ECDSA(hashes.SHA256()))
        r, s = decode_dss_signature(der)
        return b64url_encode(r.to_bytes(32, "big") + s.to_bytes(32, "big"))

    def proof(
        self,
        htm: str,
        htu: str,
        *,
        iat: float | None = None,
        jti: str | None = None,
        signer: "DpopKey | None" = None,
    ) -> str:
        """Prueba firmada; `signer` firma con OTRA llave (prueba invalida)."""
        payload = {
            "htm": htm,
            "htu": htu,
            "iat": int(time.time() if iat is None else iat),
            "jti": jti or uuid4().hex,
        }
        head = {"typ": "dpop+jwt", "alg": "ES256", "jwk": self.public_jwk}
        signing_input = f"{_b64json(head)}.{_b64json(payload)}"
        return (
            f"{signing_input}.{(signer or self)._sign(signing_input.encode('ascii'))}"
        )
