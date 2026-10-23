"""Emision y verificacion del codigo de activacion (un solo uso, hash en BD)."""

import hashlib
import hmac
import re
import secrets
from datetime import UTC, date, datetime, timedelta

from leo_sdk import LeoUser
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import runtime_settings
from app.core.config import get_settings
from app.core.exceptions import AppError
from app.core.leo import Actor
from app.core.leo import settings as leo_settings
from app.core.rate_limit import SlidingWindowLimiter
from app.core.trace import record_test_event
from app.modules.activation.models import ActivationCode
from app.modules.orders.models import Order
from app.modules.queue.models import Patient

# 32 simbolos sin ambiguos (sin 0/O/1/I): 10 caracteres = 50 bits de entropia.
ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
CODE_LENGTH = 10
_NON_CODE = re.compile(r"[\s-]")

limiter = SlidingWindowLimiter()


class TooManyAttemptsError(AppError):
    status_code = 429
    code = "too_many_attempts"


def generate_code() -> str:
    return "".join(secrets.choice(ALPHABET) for _ in range(CODE_LENGTH))


def display_code(code: str) -> str:
    """Forma legible para imprimir: `ABCDE-FGHJK`."""
    return f"{code[:5]}-{code[5:]}"


def normalize_code(raw: str) -> str | None:
    """Mayusculas sin guiones/espacios; `None` si no puede ser un codigo valido."""
    code = _NON_CODE.sub("", raw).upper()
    if len(code) != CODE_LENGTH or any(c not in ALPHABET for c in code):
        return None
    return code


def _key() -> bytes:
    pepper = get_settings().activation_code_pepper
    return (pepper or leo_settings.app_client_secret.get_secret_value()).encode()


def hash_code(code: str) -> str:
    return hmac.new(_key(), code.encode(), hashlib.sha256).hexdigest()


async def issue_code(
    session: AsyncSession, order: Order, actor: Actor | None = None
) -> str:
    """Crea el codigo de la orden y lo devuelve en claro (UNICA vez)."""
    code = generate_code()
    expires_at = datetime.now(UTC) + timedelta(
        days=await runtime_settings.get("activation.code_ttl_days")
    )
    session.add(
        ActivationCode(
            patient_id=order.patient_id,
            order_id=order.id,
            code_hash=hash_code(code),
            expires_at=expires_at,
            created_by_user_id=actor.user_id if actor else None,
        )
    )
    await session.flush()
    await record_test_event(
        session,
        "activation.issued",
        actor,
        order.id,
        summary="Código de activación emitido",
        details={"expires_at": expires_at},  # nunca el codigo
    )
    return display_code(code)


async def check_rate_limit(ip: str, document_type: str, document_number: str) -> None:
    """Limites y ventana vigentes de Ajustes, leidos en cada intento."""
    s = await runtime_settings.get_many(
        "activation.verify_max_per_ip_doc",
        "activation.verify_max_per_doc",
        "activation.verify_window_seconds",
    )
    window = s["activation.verify_window_seconds"]
    doc = f"{document_type}:{document_number}"
    for key, limit in (
        (f"ip-doc:{ip}:{doc}", s["activation.verify_max_per_ip_doc"]),
        (f"doc:{doc}", s["activation.verify_max_per_doc"]),
    ):
        wait = limiter.hit(key, limit, window)
        if wait is not None:
            raise TooManyAttemptsError(
                "Demasiados intentos. Intenta más tarde.",
                {"retry_after_seconds": int(wait)},
            )


async def consume_code(
    session: AsyncSession,
    raw_code: str,
    document_type: str,
    document_number: str,
    birth_date: date,
    *,
    actor: Actor | LeoUser | None = None,
    client: str | None = None,
) -> Patient | None:
    """Marca el codigo como usado SOLO si todo coincide, en una sentencia atomica.

    El `UPDATE ... WHERE used_at IS NULL` serializa los intentos simultaneos:
    el perdedor reevalua el WHERE tras el bloqueo y no encuentra fila. Un dato
    incorrecto no consume el codigo. Devuelve el paciente o `None`.
    """
    code = normalize_code(raw_code)
    if code is None:
        return None
    now = datetime.now(UTC)
    row = (
        await session.execute(
            update(ActivationCode)
            .where(
                ActivationCode.code_hash == hash_code(code),
                ActivationCode.used_at.is_(None),
                ActivationCode.expires_at > now,
                ActivationCode.patient_id == Patient.id,
                Patient.document_type == document_type.strip().upper(),
                Patient.document_number == document_number.strip(),
                Patient.birth_date == birth_date,
            )
            .values(used_at=now, used_by_client=client[:64] if client else None)
            .returning(ActivationCode.patient_id, ActivationCode.order_id)
            .execution_options(synchronize_session=False)
        )
    ).first()
    if row is None:
        return None
    patient_id, order_id = row
    await record_test_event(
        session,
        "activation.used",
        actor,
        order_id,
        summary="Código de activación usado",
        details={"client": client},  # nunca el codigo ni datos del paciente
    )
    return await session.get(Patient, patient_id)
