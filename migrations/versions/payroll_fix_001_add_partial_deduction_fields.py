"""add payroll partial deduction fields, tenant_id, and unique constraint

Revision ID: payroll_fix_001
Revises: 2edc56a19e55
Create Date: 2026-06-10

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector

revision = 'payroll_fix_001'
down_revision = '2edc56a19e55'
branch_labels = None
depends_on = None


def _has_column(table, column):
    bind = op.get_context().bind
    inspector = Inspector.from_engine(bind)
    columns = [c['name'] for c in inspector.get_columns(table)]
    return column in columns


def _has_index(table, index_name):
    bind = op.get_context().bind
    inspector = Inspector.from_engine(bind)
    indexes = [i['name'] for i in inspector.get_indexes(table)]
    return index_name in indexes


def _has_fk(table, fk_name):
    bind = op.get_context().bind
    inspector = Inspector.from_engine(bind)
    fks = [fk['name'] for fk in inspector.get_foreign_keys(table)]
    return fk_name in fks


def upgrade():
    # --- SalaryAdvance: add tenant_id ---
    if not _has_column('salary_advances', 'tenant_id'):
        op.add_column('salary_advances', sa.Column('tenant_id', sa.Integer(), nullable=True))
        if not _has_fk('salary_advances', 'fk_salary_advances_tenant_id'):
            op.create_foreign_key('fk_salary_advances_tenant_id', 'salary_advances', 'tenants', ['tenant_id'], ['id'])

    # --- SalaryAdvance: add partial deduction fields ---
    for col, col_type in [
        ('total_amount', sa.Numeric(10, 2)),
        ('deducted_amount', sa.Numeric(10, 2)),
        ('remaining_amount', sa.Numeric(10, 2)),
    ]:
        if not _has_column('salary_advances', col):
            op.add_column('salary_advances', sa.Column(col, col_type, default=0))

    if not _has_column('salary_advances', 'fully_deducted_at'):
        op.add_column('salary_advances', sa.Column('fully_deducted_at', sa.DateTime(), nullable=True))

    if not _has_index('salary_advances', 'ix_salary_advances_tenant_id'):
        op.create_index('ix_salary_advances_tenant_id', 'salary_advances', ['tenant_id'])

    # --- SalaryAdvance: backfill total_amount = amount for old records ---
    bind = op.get_context().bind
    bind.execute(
        sa.text("UPDATE salary_advances SET total_amount = amount WHERE total_amount IS NULL OR total_amount = 0")
    )
    bind.execute(
        sa.text("UPDATE salary_advances SET deducted_amount = 0 WHERE deducted_amount IS NULL")
    )
    bind.execute(
        sa.text("UPDATE salary_advances SET remaining_amount = total_amount - deducted_amount WHERE remaining_amount IS NULL OR remaining_amount = 0")
    )

    # --- SalaryAdvance: backfill tenant_id from employee before NOT NULL ---
    if _has_column('salary_advances', 'tenant_id'):
        bind.execute(
            sa.text(
                "UPDATE salary_advances SET tenant_id = ("
                "  SELECT employees.tenant_id FROM employees"
                "  WHERE employees.id = salary_advances.employee_id"
                ") WHERE tenant_id IS NULL"
            )
        )
        # التحقق من عدم وجود سجلات يتيمة (بدون موظف أو tenant)
        orphans = bind.execute(
            sa.text(
                "SELECT id, employee_id, amount FROM salary_advances WHERE tenant_id IS NULL"
            )
        ).fetchall()
        if orphans:
            raise RuntimeError(
                "Cannot make salary_advances.tenant_id NOT NULL — "
                f"{len(orphans)} record(s) have no matching employee or employee has no tenant:\n" +
                "\n".join(
                    f"  id={r[0]}, employee_id={r[1]}, amount={r[2]}"
                    for r in orphans
                )
            )
        op.alter_column('salary_advances', 'tenant_id', nullable=False)

    # --- PayrollTransaction: detect duplicates before unique constraint ---
    conn = op.get_context().bind
    duplicates = conn.execute(
        sa.text(
            "SELECT tenant_id, employee_id, month, year, COUNT(*) AS cnt"
            " FROM payroll_transactions"
            " WHERE tenant_id IS NOT NULL AND employee_id IS NOT NULL"
            " GROUP BY tenant_id, employee_id, month, year"
            " HAVING COUNT(*) > 1"
        )
    ).fetchall()
    if duplicates:
        raise RuntimeError(
            "Found duplicate payroll_transactions records that must be resolved "
            "before adding unique constraint:\n" +
            "\n".join(
                f"  tenant_id={r[0]}, employee_id={r[1]}, month={r[2]}, year={r[3]} ({r[4]} records)"
                for r in duplicates
            )
        )

    op.create_unique_constraint(
        'uq_payroll_tenant_employee_period',
        'payroll_transactions',
        ['tenant_id', 'employee_id', 'month', 'year']
    )


def downgrade():
    # Remove unique constraint
    try:
        op.drop_constraint('uq_payroll_tenant_employee_period', 'payroll_transactions')
    except Exception:
        pass

    # Drop salary_advance columns
    for col in ['fully_deducted_at', 'remaining_amount', 'deducted_amount', 'total_amount', 'tenant_id']:
        if _has_column('salary_advances', col):
            op.drop_column('salary_advances', col)
