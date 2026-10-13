from datetime import UTC, datetime

import pytest

from app.modules.orders.order_number import (
    MAX_SEQUENCE,
    OrderNumberExhaustedError,
    format_order_number,
    year_month_key,
)


def test_formato_ocho_digitos():
    assert format_order_number(2026, 10, 1) == "26100001"
    assert format_order_number(2027, 1, 37) == "27010037"
    assert format_order_number(2026, 12, 9999) == "26129999"


def test_consecutivo_fuera_de_rango():
    with pytest.raises(OrderNumberExhaustedError):
        format_order_number(2026, 10, MAX_SEQUENCE + 1)
    with pytest.raises(ValueError):
        format_order_number(2026, 10, 0)


def test_clave_mes_usa_zona_bogota_no_utc():
    # 2026-11-01 02:00 UTC = 2026-10-31 21:00 en Bogota (UTC-5)
    assert year_month_key(datetime(2026, 11, 1, 2, 0, tzinfo=UTC)) == (2026, 10)
    assert year_month_key(datetime(2026, 11, 1, 5, 0, tzinfo=UTC)) == (2026, 11)
