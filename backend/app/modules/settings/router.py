"""Rutas `/api/v1/settings` (router del SDK + permisos y auditoria de Incubus).

El SDK pide un "actor" con `user_id`, `username` y `request_id`: aqui es
`SettingsCaller`, que ademas guarda al `LeoUser` para la auditoria en Leo.
"""

from dataclasses import dataclass
from typing import Annotated, Any
from uuid import UUID

from fastapi import Depends
from leo_sdk import LeoUser
from leo_sdk.settings_store import SettingsRouterDeps, build_settings_router

from app.core import runtime_settings
from app.core.leo import auth, record_audit
from app.core.permissions import SET_EDIT, SET_EDIT_SECURITY, SET_UPDATE, SET_VIEW
from app.core.trace import _request_id


@dataclass(frozen=True)
class SettingsCaller:
    user: LeoUser
    user_id: UUID
    username: str
    request_id: str | None


def _editor(tag: str) -> Any:
    user_dep = auth.require_action(tag)

    async def dependency(user: Annotated[LeoUser, user_dep]) -> SettingsCaller:
        return SettingsCaller(user, user.id, user.username, _request_id.get())

    return Depends(dependency)


async def audit_update(
    caller: SettingsCaller, key: str, before: Any, after: Any, reason: str
) -> None:
    """Evento `incubus.settings.update` (valor anterior/nuevo y motivo)."""
    await record_audit(
        SET_UPDATE,
        caller.user,
        entity_type="setting",
        entity_id=key,
        before={"value": before},
        after={"value": after},
        reason=reason,
    )


settings_router = build_settings_router(
    runtime_settings.store,
    SettingsRouterDeps(
        view_dep=auth.require_action(SET_VIEW),
        edit_dep=_editor(SET_EDIT),
        edit_security_dep=_editor(SET_EDIT_SECURITY),
        audit=audit_update,
    ),
)
