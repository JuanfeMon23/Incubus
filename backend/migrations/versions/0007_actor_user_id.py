"""id de usuario de Leo junto al nombre del actor (*_user_id)

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-20 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '0007'
down_revision: Union[str, Sequence[str], None] = '0006'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# (tabla, columna): sin FK (Leo es otro sistema); filas anteriores quedan NULL.
COLUMNS = (
    ('queue_entries', 'claimed_by_user_id'),
    ('queue_status_history', 'actor_user_id'),
    ('order_tests', 'validated_by_user_id'),
    ('order_preconditions', 'reception_checked_by_user_id'),
    ('order_preconditions', 'sampling_checked_by_user_id'),
    ('order_samples', 'collected_by_user_id'),
    ('order_samples', 'received_by_user_id'),
    ('order_results', 'entered_by_user_id'),
)
INDEX = 'ix_queue_status_history_actor_user_id_changed_at'


def upgrade() -> None:
    """Upgrade schema."""
    for table, column in COLUMNS:
        op.add_column(table, sa.Column(column, postgresql.UUID(as_uuid=True), nullable=True))
    op.create_index(INDEX, 'queue_status_history', ['actor_user_id', 'changed_at'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(INDEX, table_name='queue_status_history')
    for table, column in reversed(COLUMNS):
        op.drop_column(table, column)
