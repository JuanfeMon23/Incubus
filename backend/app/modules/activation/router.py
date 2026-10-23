"""Verificacion del codigo de activacion (API de servicio para Acuarius)."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.exceptions import NotFoundError
from app.core.leo import record_audit
from app.core.permissions import DEL_VIEW, CanViewDelivery
from app.modules.activation import service

Session = Annotated[AsyncSession, Depends(get_session)]

router = APIRouter(tags=["entrega"])


class VerifyInput(BaseModel):
    code: str = Field(min_length=1, max_length=32)
    document_type: str = Field(min_length=1, max_length=8)
    document_number: str = Field(min_length=1, max_length=20)
    birth_date: date


@router.post("/activation/verify")
async def verify_activation(
    body: VerifyInput, request: Request, session: Session, user: CanViewDelivery
) -> dict:
    """Consume el codigo si coincide TODO; cualquier fallo es el mismo 404."""
    ip = request.client.host if request.client else "unknown"
    service.check_rate_limit(
        ip, body.document_type.strip().upper(), body.document_number.strip()
    )
    patient = await service.consume_code(
        session, body.code, body.document_type, body.document_number, body.birth_date
    )
    if patient is None:
        raise NotFoundError("Código de activación no válido.")
    await session.commit()
    await record_audit(
        DEL_VIEW,
        user,
        entity_type="patient",
        entity_id=patient.id,
        after={"activation": "used"},
    )
    return {
        "first_name": patient.first_name,
        "second_name": patient.second_name,
        "first_last_name": patient.first_last_name,
        "second_last_name": patient.second_last_name,
        "document_type": patient.document_type,
        "document_number": patient.document_number,
        "birth_date": patient.birth_date.isoformat(),
    }
