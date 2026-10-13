"""Numero de orden `AAMMNNNN`: anio(2) + mes(2) + consecutivo(4), por mes.

El mes/anio se toman en la zona del laboratorio (America/Bogota), no en UTC.
La asignacion atomica del consecutivo vive en `orders/repository.py`.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

LAB_TIMEZONE = ZoneInfo("America/Bogota")
MAX_SEQUENCE = 9999


class OrderNumberExhaustedError(Exception):
    """Se agotaron los 9999 consecutivos del mes."""


def year_month_key(moment: datetime) -> tuple[int, int]:
    local = moment.astimezone(LAB_TIMEZONE)
    return local.year, local.month


def format_order_number(year: int, month: int, sequence: int) -> str:
    if sequence < 1:
        raise ValueError("El consecutivo debe ser >= 1.")
    if sequence > MAX_SEQUENCE:
        raise OrderNumberExhaustedError(
            f"Se agotaron los {MAX_SEQUENCE} consecutivos del mes {year}-{month:02d}."
        )
    return f"{year % 100:02d}{month:02d}{sequence:04d}"
