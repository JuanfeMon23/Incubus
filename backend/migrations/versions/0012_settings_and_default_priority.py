"""ajustes editables (settings) y prioridad por defecto en BD

`settings` y `settings_history` los crea `leo_sdk.settings_store.migration`
(modo nativo sin FK a usuarios: las personas viven en Leo).
`priorities.is_default`: una sola prioridad por defecto (indice unico parcial);
backfill: la de codigo `media`.

Revision ID: 0012
Revises: 0011
Create Date: 2026-10-23 15:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from leo_sdk.settings_store import migration

# revision identifiers, used by Alembic.
revision: str = "0012"
down_revision: Union[str, Sequence[str], None] = "0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    migration.upgrade(op, users_table=None)

    op.add_column(
        "priorities",
        sa.Column(
            "is_default", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
    )
    op.execute("UPDATE priorities SET is_default = true WHERE code = 'media'")
    op.create_index(
        "uq_priorities_single_default",
        "priorities",
        ["is_default"],
        unique=True,
        postgresql_where=sa.text("is_default"),
    )


def downgrade() -> None:
    op.drop_index("uq_priorities_single_default", table_name="priorities")
    op.drop_column("priorities", "is_default")
    migration.downgrade(op, users_table=None)
