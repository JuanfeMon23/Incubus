"""trazabilidad de una prueba: order_test_events (append-only) y columnas de autoria

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-23 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '0011'
down_revision: Union[str, Sequence[str], None] = '0010'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

STEP_FORMAT = r"step ~ '^[a-z]+(\.[a-z_]+)+$'"


def upgrade() -> None:
    op.create_table(
        'order_test_events',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('uuidv7()'), nullable=False),
        sa.Column('order_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('order_test_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('order_sample_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('step', sa.String(length=40), nullable=False),
        sa.Column('occurred_at', sa.DateTime(timezone=True), server_default=sa.text('clock_timestamp()'), nullable=False),
        sa.Column('actor_name', sa.String(length=200), nullable=True),
        sa.Column('actor_user_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('staff_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('summary', sa.String(length=300), nullable=False),
        sa.Column('details', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column('request_id', sa.String(length=64), nullable=True),
        sa.CheckConstraint(STEP_FORMAT, name=op.f('ck_order_test_events_step_format')),
        sa.ForeignKeyConstraint(['order_id'], ['orders.id'], name=op.f('fk_order_test_events_order_id_orders'), ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['order_test_id'], ['order_tests.id'], name=op.f('fk_order_test_events_order_test_id_order_tests'), ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['order_sample_id'], ['order_samples.id'], name=op.f('fk_order_test_events_order_sample_id_order_samples'), ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_order_test_events')),
    )
    op.create_index('ix_order_test_events_order', 'order_test_events', ['order_id', 'occurred_at'], unique=False)
    op.create_index('ix_order_test_events_test', 'order_test_events', ['order_test_id', 'occurred_at'], unique=False)
    op.execute(
        """
        CREATE FUNCTION fn_forbid_update_delete() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'Tabla de solo insercion (%): no se permite % de filas',
                TG_TABLE_NAME, TG_OP USING ERRCODE = 'INC01';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        "CREATE TRIGGER trg_order_test_events_immutable "
        "BEFORE UPDATE OR DELETE ON order_test_events "
        "FOR EACH ROW EXECUTE FUNCTION fn_forbid_update_delete()"
    )

    # order_tests.created_at: backfill desde la orden, luego NOT NULL + default.
    op.add_column('order_tests', sa.Column('created_at', sa.DateTime(timezone=True), nullable=True))
    op.execute(
        "UPDATE order_tests t SET created_at = o.created_at "
        "FROM orders o WHERE o.id = t.order_id"
    )
    op.alter_column('order_tests', 'created_at', server_default=sa.text('now()'), nullable=False)
    op.add_column('order_tests', sa.Column('created_by', sa.String(length=200), nullable=True))
    op.add_column('order_tests', sa.Column('created_by_user_id', postgresql.UUID(as_uuid=True), nullable=True))

    op.add_column('order_samples', sa.Column('labels_printed_by', sa.String(length=200), nullable=True))
    op.add_column('order_samples', sa.Column('labels_printed_by_user_id', postgresql.UUID(as_uuid=True), nullable=True))

    op.add_column('activation_codes', sa.Column('created_by_user_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column('activation_codes', sa.Column('used_by_client', sa.String(length=64), nullable=True))


def downgrade() -> None:
    op.drop_column('activation_codes', 'used_by_client')
    op.drop_column('activation_codes', 'created_by_user_id')
    op.drop_column('order_samples', 'labels_printed_by_user_id')
    op.drop_column('order_samples', 'labels_printed_by')
    op.drop_column('order_tests', 'created_by_user_id')
    op.drop_column('order_tests', 'created_by')
    op.drop_column('order_tests', 'created_at')
    op.execute("DROP TRIGGER IF EXISTS trg_order_test_events_immutable ON order_test_events")
    op.execute("DROP FUNCTION IF EXISTS fn_forbid_update_delete()")
    op.drop_index('ix_order_test_events_test', table_name='order_test_events')
    op.drop_index('ix_order_test_events_order', table_name='order_test_events')
    op.drop_table('order_test_events')
