"""catalogos de categoria en BD: CHECK de categoria -> FK al code

Crea `blood_types`, `queue_statuses`, `queue_transition_kinds`,
`validation_statuses`, `result_flags` y `trace_steps` (code, name, sort_order,
is_active y columnas de comportamiento), con semilla de los valores vigentes, y
reemplaza los CHECK de categoria por FK al `code`:
`patients.blood_type`, `queue_entries.status`, `queue_status_history.{from_status,
to_status,kind}`, `order_tests.validation_status`, `order_results.flag` y
`order_test_events.step`.

Sexo es de Vladimir (`male`/`female`): se quita `ck_patients_sex_values` (la
validacion pasa al backend contra su API), se ensancha la columna y se migran los
datos `M`/`F` -> `male`/`female` (downgrade reversible).

Revision ID: 0013
Revises: 0012
Create Date: 2026-11-09 10:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0013"
down_revision: Union[str, Sequence[str], None] = "0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

BLOOD_TYPES = ["A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"]

# (code, name, is_terminal)
QUEUE_STATUSES = [
    ("pre_recepcion", "Pre-recepción", False),
    ("en_atencion_recepcion", "En atención de recepción", False),
    ("en_espera_impresion", "Espera de impresión de etiquetas", False),
    ("en_espera_toma_muestras", "Espera de toma de muestras", False),
    ("en_atencion_toma_muestras", "En atención de toma de muestras", False),
    ("toma_finalizada", "Toma de muestras finalizada", False),
    ("en_laboratorio", "En laboratorio", False),
    ("finalizada", "Finalizada", True),
    ("retirado", "Retirado", True),
]
TRANSITION_KINDS = [
    ("enter", "Ingreso a la cola"),
    ("advance", "Avance"),
    ("return", "Devolución"),
    ("remove", "Retiro"),
]
VALIDATION_STATUSES = [
    ("pending", "Pendiente"),
    ("draft", "Borrador"),
    ("validated", "Validada"),
]
# (code, name, variant, show_in_report)
RESULT_FLAGS = [
    ("normal", "Normal", "success", False),
    ("low", "Bajo", "warning", True),
    ("high", "Alto", "warning", True),
    ("abnormal", "Anormal", "warning", True),
    ("critical_low", "Crítico bajo", "danger", True),
    ("critical_high", "Crítico alto", "danger", True),
]
# (code, name, category)
TRACE_STEPS = [
    ("order.test_added", "Prueba agregada", "order"),
    ("order.finalized", "Orden finalizada", "order"),
    ("labels.printed", "Etiquetas impresas", "labels"),
    ("labels.downloaded", "Etiquetas descargadas", "labels"),
    ("sample.collected", "Tubo tomado", "sampling"),
    ("sample.uncollected", "Toma deshecha", "sampling"),
    ("lab.received", "Tubo recibido en laboratorio", "lab"),
    ("lab.unreceived", "Recepción deshecha", "lab"),
    ("precondition.checked", "Precondición verificada", "sampling"),
    ("result.entered", "Resultado capturado", "capture"),
    ("result.changed", "Resultado modificado", "capture"),
    ("result.cleared", "Resultado borrado", "capture"),
    ("test.validated", "Prueba validada", "validation"),
    ("activation.issued", "Activación emitida", "activation"),
    ("activation.used", "Activación usada", "activation"),
    ("delivery.order_viewed", "Orden consultada por el servicio de entrega", "delivery"),
    ("delivery.report_downloaded", "Informe descargado", "delivery"),
    ("delivery.patient_orders_listed", "Órdenes del paciente listadas", "delivery"),
    ("queue.entered", "Ingreso a la cola", "queue"),
    ("queue.reception_claimed", "Recepción iniciada", "reception"),
    ("queue.reception_closed", "Recepción cerrada", "reception"),
    ("queue.labels_printed", "Etiquetas impresas (cola)", "labels"),
    ("queue.sampling_claimed", "Toma de muestras iniciada", "sampling"),
    ("queue.sampling_finished", "Toma de muestras finalizada", "sampling"),
    ("queue.in_laboratory", "Paso a laboratorio", "lab"),
    ("queue.removed", "Retirado de la cola", "queue"),
    ("queue.returned", "Devuelto en la cola", "queue"),
]

_STATUS_IN = ", ".join(f"'{code}'" for code, _, _ in QUEUE_STATUSES)

# (tabla, columna, catalogo, indice nuevo o None si ya hay uno que empieza por la columna)
_FKS = [
    ("patients", "blood_type", "blood_types", "ix_patients_blood_type"),
    ("queue_entries", "status", "queue_statuses", None),
    ("queue_status_history", "from_status", "queue_statuses", "ix_queue_status_history_from_status"),
    ("queue_status_history", "to_status", "queue_statuses", None),
    ("queue_status_history", "kind", "queue_transition_kinds", "ix_queue_status_history_kind"),
    ("order_tests", "validation_status", "validation_statuses", "ix_order_tests_validation_status"),
    ("order_results", "flag", "result_flags", "ix_order_results_flag"),
    ("order_test_events", "step", "trace_steps", "ix_order_test_events_step"),
]


def _catalog_table(name: str, *extra: sa.Column | sa.CheckConstraint) -> None:
    op.create_table(
        name,
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default=sa.text("0"), nullable=False),
        *extra,
        sa.Column("id", sa.UUID(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{name}")),
        sa.UniqueConstraint("code", name=op.f(f"uq_{name}_code")),
    )
    op.execute(
        f"CREATE TRIGGER trg_{name}_forbid_delete BEFORE DELETE ON {name} "
        "FOR EACH ROW EXECUTE FUNCTION fn_forbid_delete()"
    )


def upgrade() -> None:
    bind = op.get_bind()

    _catalog_table("blood_types")
    _catalog_table(
        "queue_statuses",
        sa.Column("is_terminal", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    _catalog_table("queue_transition_kinds")
    _catalog_table("validation_statuses")
    _catalog_table(
        "result_flags",
        sa.Column("variant", sa.String(length=16), nullable=False),
        sa.Column("show_in_report", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.CheckConstraint(
            "variant IN ('success', 'warning', 'danger')", name=op.f("ck_result_flags_variant")
        ),
    )
    _catalog_table("trace_steps", sa.Column("category", sa.String(length=16), nullable=False))

    for position, code in enumerate(BLOOD_TYPES, start=1):
        bind.execute(
            sa.text("INSERT INTO blood_types (code, name, sort_order) VALUES (:c, :c, :o)"),
            {"c": code, "o": position},
        )
    for position, (code, name, terminal) in enumerate(QUEUE_STATUSES, start=1):
        bind.execute(
            sa.text(
                "INSERT INTO queue_statuses (code, name, sort_order, is_terminal) "
                "VALUES (:c, :n, :o, :t)"
            ),
            {"c": code, "n": name, "o": position, "t": terminal},
        )
    for position, (code, name) in enumerate(TRANSITION_KINDS, start=1):
        bind.execute(
            sa.text("INSERT INTO queue_transition_kinds (code, name, sort_order) VALUES (:c, :n, :o)"),
            {"c": code, "n": name, "o": position},
        )
    for position, (code, name) in enumerate(VALIDATION_STATUSES, start=1):
        bind.execute(
            sa.text("INSERT INTO validation_statuses (code, name, sort_order) VALUES (:c, :n, :o)"),
            {"c": code, "n": name, "o": position},
        )
    for position, (code, name, variant, show) in enumerate(RESULT_FLAGS, start=1):
        bind.execute(
            sa.text(
                "INSERT INTO result_flags (code, name, sort_order, variant, show_in_report) "
                "VALUES (:c, :n, :o, :v, :s)"
            ),
            {"c": code, "n": name, "o": position, "v": variant, "s": show},
        )
    for position, (code, name, category) in enumerate(TRACE_STEPS, start=1):
        bind.execute(
            sa.text(
                "INSERT INTO trace_steps (code, name, sort_order, category) "
                "VALUES (:c, :n, :o, :g)"
            ),
            {"c": code, "n": name, "o": position, "g": category},
        )
    # Filas historicas con codigos fuera de la semilla no deben romper el FK.
    op.execute(
        "INSERT INTO trace_steps (code, name, sort_order, category) "
        "SELECT DISTINCT step, step, 1000, 'order' FROM order_test_events "
        "ON CONFLICT (code) DO NOTHING"
    )
    op.execute(
        "INSERT INTO queue_statuses (code, name, sort_order) "
        "SELECT DISTINCT from_status, from_status, 1000 FROM queue_status_history "
        "WHERE from_status IS NOT NULL ON CONFLICT (code) DO NOTHING"
    )

    # CHECK de categoria fuera: el RH pasa a FK; el sexo es de Vladimir.
    op.drop_constraint(op.f("ck_patients_blood_type"), "patients", type_="check")
    op.drop_constraint(op.f("ck_patients_sex_values"), "patients", type_="check")
    op.drop_constraint(op.f("ck_queue_entries_status_values"), "queue_entries", type_="check")
    op.drop_constraint(op.f("ck_queue_status_history_to_status_values"), "queue_status_history", type_="check"
    )
    op.drop_constraint(op.f("ck_queue_status_history_kind_values"), "queue_status_history", type_="check"
    )

    op.alter_column(
        "patients", "sex", existing_type=sa.String(length=1), type_=sa.String(length=16)
    )
    op.execute("UPDATE patients SET sex = 'male' WHERE sex = 'M'")
    op.execute("UPDATE patients SET sex = 'female' WHERE sex = 'F'")

    for table, column, catalog, index in _FKS:
        op.create_foreign_key(
            op.f(f"fk_{table}_{column}_{catalog}"), table, catalog, [column], ["code"]
        )
        if index:
            op.create_index(op.f(index), table, [column])


def downgrade() -> None:
    for table, column, catalog, index in reversed(_FKS):
        if index:
            op.drop_index(op.f(index), table_name=table)
        op.drop_constraint(op.f(f"fk_{table}_{column}_{catalog}"), table, type_="foreignkey")

    # Sexo: solo male/female caben en el CHECK anterior; otro codigo queda NULL.
    op.execute("UPDATE patients SET sex = 'M' WHERE sex = 'male'")
    op.execute("UPDATE patients SET sex = 'F' WHERE sex = 'female'")
    op.execute("UPDATE patients SET sex = NULL WHERE sex NOT IN ('M', 'F')")
    op.alter_column(
        "patients", "sex", existing_type=sa.String(length=16), type_=sa.String(length=1)
    )
    op.create_check_constraint(op.f("ck_patients_sex_values"), "patients", "sex IN ('M', 'F')")
    op.create_check_constraint(
        op.f("ck_patients_blood_type"),
        "patients",
        "blood_type IS NULL OR blood_type IN "
        "('A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-')",
    )
    op.create_check_constraint(
        op.f("ck_queue_entries_status_values"), "queue_entries", f"status IN ({_STATUS_IN})"
    )
    op.create_check_constraint(
        op.f("ck_queue_status_history_to_status_values"),
        "queue_status_history",
        f"to_status IN ({_STATUS_IN})",
    )
    op.create_check_constraint(
        op.f("ck_queue_status_history_kind_values"),
        "queue_status_history",
        "kind IN ('enter', 'advance', 'return', 'remove')",
    )

    for name in (
        "trace_steps",
        "result_flags",
        "validation_statuses",
        "queue_transition_kinds",
        "queue_statuses",
        "blood_types",
    ):
        op.execute(f"DROP TRIGGER IF EXISTS trg_{name}_forbid_delete ON {name}")
        op.drop_table(name)
