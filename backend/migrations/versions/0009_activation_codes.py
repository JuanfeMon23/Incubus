"""activation_codes: codigo de activacion de un solo uso por orden

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-22 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '0009'
down_revision: Union[str, Sequence[str], None] = '0008'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'activation_codes',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('uuidv7()'), nullable=False),
        sa.Column('patient_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('order_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('code_hash', sa.String(length=64), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('used_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint('char_length(code_hash) = 64', name=op.f('ck_activation_codes_hash_length')),
        sa.CheckConstraint('expires_at > created_at', name=op.f('ck_activation_codes_expires_after_creation')),
        sa.ForeignKeyConstraint(['order_id'], ['orders.id'], name=op.f('fk_activation_codes_order_id_orders')),
        sa.ForeignKeyConstraint(['patient_id'], ['patients.id'], name=op.f('fk_activation_codes_patient_id_patients')),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_activation_codes')),
        sa.UniqueConstraint('code_hash', name=op.f('uq_activation_codes_code_hash')),
        sa.UniqueConstraint('order_id', name=op.f('uq_activation_codes_order_id')),
    )
    op.create_index(op.f('ix_activation_codes_patient_id'), 'activation_codes', ['patient_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_activation_codes_patient_id'), table_name='activation_codes')
    op.drop_table('activation_codes')
