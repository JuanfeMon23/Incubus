"""Importa los models de todos los modulos (fuente de `target_metadata`)."""

from app.core.db import settings_model as _settings  # noqa: F401
from app.core.db.base import Base
from app.modules.activation import models as _activation  # noqa: F401
from app.modules.orders import models as _orders  # noqa: F401  (incluye OrderTestEvent)
from app.modules.queue import models as _queue  # noqa: F401

__all__ = ["Base"]
