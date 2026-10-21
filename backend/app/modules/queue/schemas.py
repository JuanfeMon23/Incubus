from datetime import date, datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

Sex = Literal["M", "F"]
BloodType = Literal["A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"]
# Solo digitos (7 a 15): sin guiones, espacios ni letras.
Phone = Annotated[str, Field(pattern=r"^\d{7,15}$")]
QueueStatusLiteral = Literal[
    "pre_recepcion",
    "en_atencion_recepcion",
    "en_espera_impresion",
    "en_espera_toma_muestras",
    "en_atencion_toma_muestras",
    "toma_finalizada",
    "en_laboratorio",
    "finalizada",
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
    blood_type: BloodType | None = None


class PatientUpdate(BaseModel):
    """Datos demograficos que completa la secretaria en recepcion."""

    first_name: str | None = Field(default=None, min_length=1, max_length=80)
    second_name: str | None = Field(default=None, max_length=80)
    first_last_name: str | None = Field(default=None, min_length=1, max_length=80)
    second_last_name: str | None = Field(default=None, max_length=80)
    sex: Sex | None = None
    birth_date: date | None = None
    birth_place: str | None = Field(default=None, max_length=120)
    blood_type: BloodType | None = None
    email: str | None = Field(default=None, max_length=255)
    phone: Phone | None = None
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


# `actor` en los cuerpos de entrada esta DEPRECADO: se acepta y se IGNORA mientras
# el frontend migra. El actor es siempre la persona autenticada en Leo
# (`app.core.leo.actor_name`); quitar el campo cuando nadie lo envie.


class QueueEntryCreate(BaseModel):
    patient: PatientIn
    priority_id: UUID
    actor: str | None = Field(default=None, max_length=120, deprecated=True)


class ClaimInput(BaseModel):
    actor: str | None = Field(default=None, max_length=120, deprecated=True)
    # Toma de muestras: solo el profesional asignado puede tomar al paciente.
    professional_id: str | None = Field(default=None, max_length=64)


class ReasonedActionInput(BaseModel):
    """Retiro o devolucion: el motivo parametrizado es obligatorio."""

    reason_id: UUID
    note: str | None = None
    actor: str | None = Field(default=None, max_length=120, deprecated=True)


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
    # Contador monotono por entrada (trigger en BD): el cliente descarta eventos viejos.
    version: int


class QueueEntryLive(BaseModel):
    """Vista MINIMA de una entrada para el tiempo real: sin datos personales ni
    clinicos (ni paciente, ni borrador, ni nombre del profesional). Es lo que
    viaja en los eventos y en el snapshot de `sync`; el detalle se pide por REST."""

    id: UUID
    status: QueueStatusLiteral
    version: int
    priority_id: UUID
    assigned_professional_id: str | None = None
    order_number: str | None = None


class QueueEntryEvent(QueueEntryLive):
    """Payload de un evento: la vista minima + la etapa de la que viene."""

    previous_status: QueueStatusLiteral | None = None
    sample_id: str | None = None


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
