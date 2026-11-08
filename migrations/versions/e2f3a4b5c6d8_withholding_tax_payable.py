"""Register WITHHOLDING_TAX_PAYABLE (2149) as a real GL concept.

routes/expenses.py posts the withholding-tax leg with this concept, but it was
never added to models/_constants.py GL_CONCEPT_CODES, so the resolver refused
it as unknown (caught by test_the_concepts_the_services_post_all_resolve).
This revision rebuilds ck_gl_account_mappings_concept_code from the model's
own list and inserts account 2149 into every tenant that already has a chart.

Revision ID: e2f3a4b5c6d8
Revises: d1e2f3a406
Create Date: 2026-11-08
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "e2f3a4b5c6d8"
down_revision = "d1e2f3a406"
branch_labels = None
depends_on = None

CONSTRAINT_NAME = "ck_gl_account_mappings_concept_code"
TABLE_NAME = "gl_account_mappings"


def _concept_check_expression() -> str:
    """The constraint expression, built from the same list the model uses."""
    from models._constants import GL_CONCEPT_CODES

    return "concept_code IN ({})".format(", ".join(f"'{code}'" for code in GL_CONCEPT_CODES))


def _previous_check_expression() -> str:
    from models._constants import GL_CONCEPT_CODES

    codes = tuple(code for code in GL_CONCEPT_CODES if code != "WITHHOLDING_TAX_PAYABLE")
    return "concept_code IN ({})".format(", ".join(f"'{code}'" for code in codes))


def upgrade() -> None:
    bind = op.get_bind()

    # 1. Account 2149 for every tenant that already has a chart.
    tenant_rows = bind.execute(
        sa.text(
            """
            SELECT DISTINCT t.id AS tenant_id, COALESCE(t.default_currency, 'ILS') AS currency
            FROM tenants t
            WHERE EXISTS (SELECT 1 FROM gl_accounts g WHERE g.tenant_id = t.id)
            """
        )
    ).fetchall()
    for tenant_id, currency in tenant_rows:
        exists = bind.execute(
            sa.text("SELECT 1 FROM gl_accounts WHERE tenant_id = :t AND code = :c LIMIT 1"),
            {"t": tenant_id, "c": "2149"},
        ).first()
        if exists:
            continue
        parent_id = bind.execute(
            sa.text("SELECT id FROM gl_accounts WHERE tenant_id = :t AND code = :p LIMIT 1"),
            {"t": tenant_id, "p": "2100"},
        ).scalar()
        bind.execute(
            sa.text(
                """
                INSERT INTO gl_accounts
                    (tenant_id, code, name, name_ar, type, sub_type,
                     is_header, parent_id, is_active, is_contra,
                     liquidity_kind, is_default_liquidity, is_reconcile,
                     currency, level,
                     created_at, updated_at)
                VALUES
                    (:t, :c, :n, :nar, :ty, :st,
                     false, :pid, true, false,
                     NULL, false, false,
                     :cur, 2,
                     CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """
            ),
            {
                "t": tenant_id,
                "c": "2149",
                "n": "Withholding Tax Payable",
                "nar": "ضريبة استقطاع مستحقة",
                "ty": "liability",
                "st": "payable",
                "pid": parent_id,
                "cur": currency,
            },
        )

    # 2. Widen the concept CHECK constraint — rebuilt from the model registry.
    with op.batch_alter_table(TABLE_NAME) as batch_op:
        batch_op.drop_constraint(CONSTRAINT_NAME, type_="check")
        batch_op.create_check_constraint(CONSTRAINT_NAME, _concept_check_expression())


def downgrade() -> None:
    bind = op.get_bind()
    # Remove the mapping rows first so the shrunk CHECK cannot fail on them.
    bind.execute(sa.text("DELETE FROM gl_account_mappings WHERE concept_code = 'WITHHOLDING_TAX_PAYABLE'"))
    with op.batch_alter_table(TABLE_NAME) as batch_op:
        batch_op.drop_constraint(CONSTRAINT_NAME, type_="check")
        batch_op.create_check_constraint(CONSTRAINT_NAME, _previous_check_expression())
