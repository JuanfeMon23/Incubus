from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

CatalogKind = Literal[
    "priorities",
    "removal-reasons",
    "return-reasons",
    # Catalogos de categoria (sus `code` son de sistema): solo se editan nombre
    # y presentacion; no se crean ni se desactivan.
    "blood-types",
    "queue-statuses",
    "queue-transition-kinds",
    "validation-statuses",
    "result-flags",
    "trace-steps",
]


class CatalogAdminRead(BaseModel):
    """Elemento de un catalogo; `color_hex` y `rank` solo existen en prioridades
    (en los motivos son null)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    code: str
    name: str
    is_active: bool
    created_at: datetime
    updated_at: datetime
    color_hex: str | None = None
    rank: int | None = None
    # Solo prioridades: la que el ingreso preselecciona (null en los motivos).
    is_default: bool | None = None
    # Solo catalogos de categoria (null en prioridades y motivos).
    sort_order: int | None = None
    is_terminal: bool | None = None  # queue-statuses
    variant: str | None = None  # result-flags
    show_in_report: bool | None = None  # result-flags
    category: str | None = None  # trace-steps


class CatalogPage(BaseModel):
    items: list[CatalogAdminRead]
    page: int
    page_size: int
    total: int


# Las reglas de formato las valida el servicio (mensajes en espanol y
# `{code, message, details}` uniforme), no pydantic.
class CatalogCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(max_length=64)
    name: str = Field(max_length=255)
    color_hex: str | None = Field(default=None, max_length=7)  # solo prioridades
    rank: int | None = None  # solo prioridades


class CatalogUpdate(BaseModel):
    """Cambio parcial. El `code` no se edita (lo referencian integraciones y la
    interfaz). `reason` es opcional y queda en la auditoria."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, max_length=255)
    color_hex: str | None = Field(default=None, max_length=7)
    rank: int | None = None
    # Catalogos de categoria.
    sort_order: int | None = None
    variant: str | None = Field(default=None, max_length=16)  # result-flags
    show_in_report: bool | None = None  # result-flags
    reason: str | None = Field(default=None, max_length=500)


class ToggleInput(BaseModel):
    """Motivo del cambio (obligatorio al desactivar)."""

    model_config = ConfigDict(extra="forbid")

    reason: str | None = Field(default=None, max_length=500)
