"""Integracion con Leo (SSO, permisos y auditoria) via `leo_sdk`.

Unico punto donde se crean `LeoSettings`, el `Catalog` y `LeoAuth`. El catalogo
de acciones vive en `app.core.permissions`; las mutaciones se registran con
`record_audit` (o por `queue.events.publish_entry`, que lo llama por ti).

Cookies propias: en desarrollo todos los servicios comparten el host
`localhost` y las cookies no distinguen puertos, asi que Incubus NO usa los
nombres por defecto del SDK (`leo_access`...) para no pisar la sesion de otra
app. Se pueden cambiar con `ACCESS_COOKIE_NAME`, `REFRESH_COOKIE_NAME` y
`FLOW_COOKIE_NAME`.
"""

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Annotated, Any
from uuid import UUID

from fastapi import Depends, Request
from leo_sdk import Catalog, LeoAuth, LeoError, LeoSettings, LeoUser
from leo_sdk.tags import validate_tag

logger = logging.getLogger("app.leo")

APP_SLUG = "incubus"


class IncubusLeoSettings(LeoSettings):
    """`LeoSettings` con nombres de cookie propios de Incubus."""

    access_cookie_name: str = "incubus_access"
    refresh_cookie_name: str = "incubus_refresh"
    flow_cookie_name: str = "incubus_oauth"


settings = IncubusLeoSettings()  # type: ignore[call-arg]  # entorno / backend/.env
catalog = Catalog(APP_SLUG)
auth = LeoAuth(settings, catalog=catalog)


def actor_name(user: LeoUser) -> str:
    """Nombre con el que una persona queda en historiales y registros."""
    return user.name or user.username


@dataclass(frozen=True, slots=True)
class Actor:
    """Quien ejecuta una accion: nombre (copia en el momento) + id de Leo.

    Los servicios la reciben en lugar de strings sueltos y la graban en las
    columnas hermanas `<x>_by` / `<x>_by_user_id`. Sin actor (`Actor()`), ambas
    quedan NULL."""

    name: str | None = None
    user_id: UUID | None = None

    @classmethod
    def of(cls, user: LeoUser) -> "Actor":
        return cls(actor_name(user), user.id)


NO_ACTOR = Actor()


def client_of(user: LeoUser) -> str:
    """Quien consume una API: el `client_id` del servicio o el usuario."""
    return user.client_id or user.username


def uuid_str(value: UUID | None) -> str | None:
    """Id de usuario para respuestas JSON (None si la fila es anterior a 0007)."""
    return None if value is None else str(value)


async def record_audit(
    action_tag: str,
    user: LeoUser,
    *,
    entity_type: str,
    entity_id: object,
    before: Mapping[str, Any] | None = None,
    after: Mapping[str, Any] | None = None,
    reason: str | None = None,
) -> None:
    """Registra un evento de auditoria en Leo con el `diff(before, after)`.

    Sin datos personales del paciente: solo ids, estados y codigos. Un fallo de
    Leo (o de cualquier otro tipo) se loguea y NO propaga: la operacion de
    negocio ya se confirmo y no debe romperse por la auditoria.
    """
    try:
        await auth.audit.record(
            action_tag,
            entity_type=entity_type,
            entity_id=str(entity_id),
            changes=auth.audit.diff(before, after),
            reason=reason,
            actor=user,
        )
    except Exception:
        logger.exception("No se pudo registrar el evento de auditoría %s.", action_tag)


# --- Autorizacion mas alla de un solo tag fijo ---------------------------------


async def audit_denied(request: Request, user: LeoUser, tag: str) -> None:
    """Evento `denied` en Leo (nunca propaga un fallo de la auditoria)."""
    try:
        await auth.audit.record(
            tag,
            "denied",
            actor=user,
            reason="Intento de acceso sin permiso.",
            ip=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
            request_id=request.headers.get("x-request-id"),
        )
    except Exception:
        logger.exception("No se pudo registrar el intento denegado de %s.", tag)


async def deny(request: Request, user: LeoUser, tag: str, **details: Any) -> None:
    """Evento `denied` en Leo y 403 `forbidden`."""
    await audit_denied(request, user, tag)
    raise LeoError(
        "forbidden",
        "No tienes permiso para realizar esta acción.",
        403,
        {"action": tag, **details},
    )


async def authorize(request: Request, user: LeoUser, tag: str) -> None:
    """Exige `tag` dentro de un handler (cuando el tag depende de los datos)."""
    auth.used_tags.add(validate_tag(tag, app_slug=APP_SLUG))
    if not user.can(tag):
        await deny(request, user, tag)


def require_any_action(*tags: str) -> Any:
    """Dependencia: basta UNO de los tags (`details.any_of` lista todos)."""
    for tag in tags:
        auth.used_tags.add(validate_tag(tag, app_slug=APP_SLUG))

    async def dependency(
        request: Request, user: Annotated[LeoUser, Depends(auth.current_user)]
    ) -> LeoUser:
        if not any(user.can(t) for t in tags):
            await deny(request, user, tags[0], any_of=list(tags))
        return user

    return Depends(dependency)


async def _catalog_reader(
    request: Request, user: Annotated[LeoUser, Depends(auth.current_user)]
) -> LeoUser:
    """Persona (no servicio) con al menos un permiso de Incubus."""
    if user.is_service:
        raise LeoError(
            "user_required",
            "Esta acción es solo para personas, no para aplicaciones.",
            403,
        )
    if not any(p.startswith(f"{APP_SLUG}.") for p in user.permissions):
        raise LeoError(
            "forbidden",
            "No tienes permiso para realizar esta acción.",
            403,
            {"action": f"{APP_SLUG}.*"},
        )
    return user


# Catalogos compartidos y herramientas sin datos: cualquier persona de Incubus.
CatalogReader = Annotated[LeoUser, Depends(_catalog_reader)]
