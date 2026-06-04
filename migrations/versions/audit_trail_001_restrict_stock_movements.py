"""restrict_stock_movement_deletion

Revision ID: audit_trail_001
Revises: tenant_scope_003
Create Date: 2026-06-03 23:59:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'audit_trail_001'
down_revision = 'tenant_scope_003'
branch_labels = None
depends_on = None


def upgrade():
    # 1. Protect Physical Stock Audit Trail
    # Drop existing foreign key that may have default NO ACTION or implicit CASCADE
    # Explicitly recreate it with RESTRICT
    op.drop_constraint('fk_stock_movements_product_id_products', 'stock_movements', type_='foreignkey')
    op.create_foreign_key(
        'fk_stock_movements_product_id_products', 
        'stock_movements', 'products', 
        ['product_id'], ['id'], 
        ondelete='RESTRICT'
    )


def downgrade():
    # Restore to default NO ACTION (implied by omitting ondelete)
    op.drop_constraint('fk_stock_movements_product_id_products', 'stock_movements', type_='foreignkey')
    op.create_foreign_key(
        'fk_stock_movements_product_id_products', 
        'stock_movements', 'products', 
        ['product_id'], ['id']
    )
