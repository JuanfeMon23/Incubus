"""indice unico de paciente activo: un turno finalizada no cuenta como activo

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-23 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0010'
down_revision: Union[str, Sequence[str], None] = '0009'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

INDEX = 'uq_queue_entries_active_patient'


def upgrade() -> None:
    """Idempotente: la BD de desarrollo pudo ajustarse a mano con el mismo predicado."""
    op.execute(f'DROP INDEX IF EXISTS {INDEX}')
    op.execute(
        f"CREATE UNIQUE INDEX {INDEX} ON queue_entries (patient_id) "
        "WHERE status NOT IN ('retirado', 'finalizada')"
    )


def downgrade() -> None:
    op.execute(f'DROP INDEX IF EXISTS {INDEX}')
    op.execute(
        f"CREATE UNIQUE INDEX {INDEX} ON queue_entries (patient_id) "
        "WHERE status <> 'retirado'"
    )
