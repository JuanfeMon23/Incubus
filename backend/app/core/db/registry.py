"""Importa los models de todos los modulos (fuente de `target_metadata`)."""

from app.core.db.base import Base
from app.modules.orders import models as _orders  # noqa: F401
from app.modules.queue import models as _queue  # noqa: F401

__all__ = ["Base"]
