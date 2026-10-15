"""Errores de negocio y su traduccion HTTP uniforme `{code, message, details}`."""

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DBAPIError

FORBIDDEN_OPERATION_SQLSTATE = "INC01"


class AppError(Exception):
    status_code: int = status.HTTP_400_BAD_REQUEST
    code: str = "app_error"

    def __init__(self, message: str, details: dict | list | str | None = None):
        self.message = message
        self.details = details
        super().__init__(message)


class NotFoundError(AppError):
    status_code = status.HTTP_404_NOT_FOUND
    code = "not_found"


class ForbiddenError(AppError):
    status_code = status.HTTP_403_FORBIDDEN
    code = "forbidden"


class ConflictError(AppError):
    status_code = status.HTTP_409_CONFLICT
    code = "conflict"


class ValidationAppError(AppError):
    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    code = "validation_error"


def _body(code: str, message: str, details) -> dict:
    return {"code": code, "message": message, "details": details}


def _app_error_handler(_r: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code, content=_body(exc.code, exc.message, exc.details)
    )


def _db_error_handler(_r: Request, exc: DBAPIError) -> JSONResponse:
    orig = exc.orig
    sqlstate = getattr(orig, "sqlstate", None) or getattr(
        getattr(orig, "__cause__", None), "sqlstate", None
    )
    if sqlstate != FORBIDDEN_OPERATION_SQLSTATE:
        raise exc
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content=_body(
            "immutable_record",
            "Operacion no permitida: el historial no se edita ni se elimina.",
            None,
        ),
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, _app_error_handler)
    app.add_exception_handler(DBAPIError, _db_error_handler)
