"""Errores de negocio de ordenes con codigo propio (contrato con el frontend)."""

from app.core.exceptions import ValidationAppError


class UnansweredPreconditionsError(ValidationAppError):
    """Alguna precondicion no tiene respuesta (cumple / no cumple)."""

    code = "unanswered_preconditions"


class NoteRequiredError(ValidationAppError):
    """Una precondicion marcada como 'no cumple' exige una nota."""

    code = "note_required"
