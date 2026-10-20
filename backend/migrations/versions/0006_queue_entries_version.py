"""queue_entries.version con trigger de incremento

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-20 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0006'
down_revision: Union[str, Sequence[str], None] = '0005'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'queue_entries',
        sa.Column('version', sa.Integer(), server_default=sa.text('0'), nullable=False),
    )
    op.execute(
        """
        CREATE FUNCTION fn_queue_entries_bump_version() RETURNS trigger AS $$
        BEGIN
            NEW.version := OLD.version + 1;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        "CREATE TRIGGER trg_queue_entries_bump_version BEFORE UPDATE ON queue_entries "
        "FOR EACH ROW EXECUTE FUNCTION fn_queue_entries_bump_version()"
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP TRIGGER IF EXISTS trg_queue_entries_bump_version ON queue_entries")
    op.execute("DROP FUNCTION IF EXISTS fn_queue_entries_bump_version()")
    op.drop_column('queue_entries', 'version')
