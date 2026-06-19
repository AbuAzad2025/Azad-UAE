"""Add tenant_id to DepreciationSchedule

Revision ID: fb38b4dfe43b
Revises: perf_001
Create Date: 2026-06-19 23:28:45.795031

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'fb38b4dfe43b'
down_revision = 'perf_001'
branch_labels = None
depends_on = None

def upgrade():
    # 1. Add column as nullable
    with op.batch_alter_table('depreciation_schedules', schema=None) as batch_op:
        batch_op.add_column(sa.Column('tenant_id', sa.Integer(), nullable=True))

    # 2. Backfill via asset_id
    op.execute('''
        UPDATE depreciation_schedules
        SET tenant_id = fixed_assets.tenant_id
        FROM fixed_assets
        WHERE depreciation_schedules.asset_id = fixed_assets.id
    ''')

    # 3. Detect orphans
    connection = op.get_bind()
    orphans = connection.execute(sa.text("SELECT count(*) FROM depreciation_schedules WHERE tenant_id IS NULL")).scalar()
    if orphans > 0:
        raise ValueError(f"Found {orphans} orphaned depreciation_schedules. Cannot safely set tenant_id NOT NULL.")

    # 4. Alter column to NOT NULL and add index/foreign key
    with op.batch_alter_table('depreciation_schedules', schema=None) as batch_op:
        batch_op.alter_column('tenant_id', existing_type=sa.Integer(), nullable=False)
        batch_op.create_index(batch_op.f('ix_depreciation_schedules_tenant_id'), ['tenant_id'], unique=False)
        batch_op.create_foreign_key('fk_depreciation_schedules_tenant_id_tenants', 'tenants', ['tenant_id'], ['id'], ondelete='CASCADE')


def downgrade():
    with op.batch_alter_table('depreciation_schedules', schema=None) as batch_op:
        batch_op.drop_constraint('fk_depreciation_schedules_tenant_id_tenants', type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_depreciation_schedules_tenant_id'))
        batch_op.drop_column('tenant_id')
