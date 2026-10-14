from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

Sex = Literal["M", "F"]
QueueStatusLiteral = Literal[
    "pre_recepcion",
    "en_atencion_recepcion",
    "en_espera_impresion",
    "en_espera_toma_muestras",
    "en_atencion_toma_muestras",
    "toma_finalizada",
    "retirado",
]


class CatalogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    code: str
    name: str


class PriorityRead(CatalogRead):
    color_hex: str
    rank: int


class PatientIn(BaseModel):
    """Datos que trae el codigo de barras de la cedula (pre-recepcion)."""

    document_type: str = Field(default="CC", max_length=8)
    document_number: str = Field(min_length=3, max_length=20)
    first_name: str = Field(min_length=1, max_length=80)
    second_name: str | None = Field(default=None, max_length=80)
    first_last_name: str = Field(min_length=1, max_length=80)
    second_last_name: str | None = Field(default=None, max_length=80)
    sex: Sex | None = None
    birth_date: date | None = None
    blood_type: str | None = Field(default=None, max_length=3)


class PatientUpdate(BaseModel):
    """Datos demograficos que completa la secretaria en recepcion."""

    first_name: str | None = Field(default=None, min_length=1, max_length=80)
    second_name: str | None = Field(default=None, max_length=80)
    first_last_name: str | None = Field(default=None, min_length=1, max_length=80)
    second_last_name: str | None = Field(default=None, max_length=80)
    sex: Sex | None = None
    birth_date: date | None = None
    birth_place: str | None = Field(default=None, max_length=120)
    blood_type: str | None = Field(default=None, max_length=3)
    email: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=32)
    address: str | None = Field(default=None, max_length=255)
    insurer: str | None = Field(default=None, max_length=150)


class PatientRead(PatientIn):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    birth_place: str | None
    email: str | None
    phone: str | None
    address: str | None
    insurer: str | None


class QueueEntryCreate(BaseModel):
    patient: PatientIn
    priority_id: UUID
    actor: str | None = Field(default=None, max_length=120)


class ClaimInput(BaseModel):
    actor: str | None = Field(default=None, max_length=120)
    # Toma de muestras: solo el profesional asignado puede tomar al paciente.
    professional_id: str | None = Field(default=None, max_length=64)


class ReasonedActionInput(BaseModel):
    """Retiro o devolucion: el motivo parametrizado es obligatorio."""

    reason_id: UUID
    note: str | None = None
    actor: str | None = Field(default=None, max_length=120)


class DraftInput(BaseModel):
    test_codes: list[str] = Field(default_factory=list)


class QueueEntryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    status: QueueStatusLiteral
    claimed_by: str | None
    assigned_professional_id: str | None = None
    assigned_professional_name: str | None = None
    arrived_at: datetime
    draft: dict
    patient: PatientRead
    priority: PriorityRead
    order_number: str | None = None


class HistoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    from_status: str | None
    to_status: str
    kind: str
    changed_at: datetime
    actor: str | None
    note: str | None
    removal_reason_id: UUID | None
    return_reason_id: UUID | None
