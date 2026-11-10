"""Etiquetas que salen de BD: marcas del informe y pasos de la trazabilidad."""

from sqlalchemy import update

from app.modules.catalogs import service
from app.modules.orders.models import ResultFlag, TraceStep


async def test_report_flag_labels_only_include_flags_shown_in_the_report(session):
    labels = await service.report_flag_labels(session)
    assert labels["critical_high"] == "Crítico alto"
    assert "normal" not in labels


async def test_report_flag_labels_follow_the_database(session):
    await session.execute(
        update(ResultFlag).where(ResultFlag.code == "low").values(name="Disminuido")
    )
    await session.execute(
        update(ResultFlag).where(ResultFlag.code == "high").values(show_in_report=False)
    )
    labels = await service.report_flag_labels(session)
    assert labels["low"] == "Disminuido"
    assert "high" not in labels


async def test_trace_step_names_follow_the_database(session):
    await session.execute(
        update(TraceStep).where(TraceStep.code == "queue.entered").values(name="Llegó")
    )
    names = await service.trace_step_names(session)
    assert names["queue.entered"] == "Llegó"
    assert names["test.validated"]
