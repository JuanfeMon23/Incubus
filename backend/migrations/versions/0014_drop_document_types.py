"""drop local document_types (Leo owns the catalog)

Revision ID: 0014
Revises: 0013
Create Date: 2026-11-09 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0014'
down_revision: Union[str, Sequence[str], None] = '0013'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_document_types_forbid_delete ON document_types")
    op.drop_table('document_types')


def downgrade() -> None:
    op.create_table('document_types',
    sa.Column('code', sa.String(length=64), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
    sa.Column('id', sa.UUID(), server_default=sa.text('uuidv7()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_document_types')),
    sa.UniqueConstraint('code', name=op.f('uq_document_types_code'))
    )
    op.execute(
        "CREATE TRIGGER trg_document_types_forbid_delete BEFORE DELETE ON document_types "
        "FOR EACH ROW EXECUTE FUNCTION fn_forbid_delete()"
    )
    op.execute(
        """
        INSERT INTO document_types (code, name) VALUES
          ('CC', 'Cédula de ciudadanía'),
          ('TI', 'Tarjeta de identidad'),
          ('CE', 'Cédula de extranjería'),
          ('PA', 'Pasaporte'),
          ('RC', 'Registro civil'),
          ('PEP', 'Permiso especial de permanencia'),
          ('PPT', 'Permiso por protección temporal'),
          ('MS', 'Menor sin identificación'),
          ('AS', 'Adulto sin identificación')
        """
    )
