"""Tablas `settings` y `settings_history`: ajustes operativos editables, con
historial inmutable.

El esquema es el modulo compartido `leo_sdk.settings_store`, en modo nativo sin
FK a usuarios (`user_pk=None`): las personas viven en Leo, asi que
`updated_by` / `changed_by` guardan su uuid sin tabla local. La migracion 0012
usa `leo_sdk.settings_store.migration` con `users_table=None`.
"""

from leo_sdk.settings_store import make_settings_models

from app.core.db.base import Base

_models = make_settings_models(Base, user_pk=None)
Setting = _models.Setting
SettingHistory = _models.SettingHistory
SETTINGS_MODELS = _models
