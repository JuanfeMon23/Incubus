"""CHECK de blood_type en patients (normaliza RH invalido a NULL)

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-20 15:00:00.000000

"""
import logging
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0008'
down_revision: Union[str, Sequence[str], None] = '0007'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

log = logging.getLogger('alembic.runtime.migration')

_VALID = "'A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-'"
CONDITION = f"blood_type IN ({_VALID})"
CHECK = 'ck_patients_blood_type'


def upgrade() -> None:
    """Upgrade schema."""
    # Datos de prueba antiguos guardaron RH invalido ('DD', '22'); se anulan
    # antes de la restriccion. Solo se registra el conteo, nunca los datos.
    result = op.get_bind().exec_driver_sql(
        f"UPDATE patients SET blood_type = NULL "
        f"WHERE blood_type IS NOT NULL AND blood_type NOT IN ({_VALID})"
    )
    log.info('0008: %s paciente(s) con blood_type invalido normalizados a NULL', result.rowcount)
    op.create_check_constraint(op.f(CHECK), 'patients', f"blood_type IS NULL OR {CONDITION}")


def downgrade() -> None:
    """Downgrade schema.

    Quita el CHECK. Los blood_type normalizados a NULL en upgrade NO se restauran.
    """
    op.drop_constraint(op.f(CHECK), 'patients', type_='check')
