"""add branch-aware liquidity metadata to GL accounts

Revision ID: treasury_gl_accounts_001
Revises: f8a2c1d5e9ab
"""
from alembic import op
import sqlalchemy as sa


revision = "treasury_gl_accounts_001"
down_revision = "f8a2c1d5e9ab"
branch_labels = None
depends_on = None


def _has_column(inspector, table_name, column_name):
    return column_name in {c["name"] for c in inspector.get_columns(table_name)}


def _branch_account_code(prefix, branch_id):
    return f"{prefix}-B{int(branch_id)}"


def _ensure_branch_liquidity_accounts(conn):
    branches = conn.execute(
        sa.text(
            """
            SELECT id, tenant_id, name
              FROM branches
             WHERE is_active = TRUE
             ORDER BY tenant_id ASC, is_main DESC, id ASC
            """
        )
    ).mappings().all()

    for branch in branches:
        for parent_code, kind, name_prefix_ar, name_prefix_en in (
            ("1110", "cash", "صندوق", "Cashbox"),
            ("1120", "bank", "بنك", "Bank"),
        ):
            parent = conn.execute(
                sa.text(
                    """
                    SELECT id
                      FROM gl_accounts
                     WHERE tenant_id = :tenant_id AND code = :code
                     LIMIT 1
                    """
                ),
                {"tenant_id": branch["tenant_id"], "code": parent_code},
            ).fetchone()
            if not parent:
                continue

            code = _branch_account_code(parent_code, branch["id"])
            existing = conn.execute(
                sa.text(
                    """
                    SELECT id
                      FROM gl_accounts
                     WHERE tenant_id = :tenant_id AND code = :code
                     LIMIT 1
                    """
                ),
                {"tenant_id": branch["tenant_id"], "code": code},
            ).fetchone()

            params = {
                "tenant_id": branch["tenant_id"],
                "code": code,
                "name": f"{name_prefix_en} - {branch['name']}",
                "name_ar": f"{name_prefix_ar} {branch['name']}",
                "parent_id": parent[0],
                "branch_id": branch["id"],
                "liquidity_kind": kind,
            }

            if existing:
                conn.execute(
                    sa.text(
                        """
                        UPDATE gl_accounts
                           SET name = :name,
                               name_ar = :name_ar,
                               parent_id = :parent_id,
                               branch_id = :branch_id,
                               type = 'asset',
                               currency = 'AED',
                               is_active = TRUE,
                               is_header = FALSE,
                               level = 3,
                               liquidity_kind = :liquidity_kind,
                               is_default_liquidity = TRUE,
                               updated_at = CURRENT_TIMESTAMP
                         WHERE id = :id
                        """
                    ),
                    {**params, "id": existing[0]},
                )
            else:
                conn.execute(
                    sa.text(
                        """
                        INSERT INTO gl_accounts (
                            tenant_id, code, name, name_ar, parent_id, branch_id,
                            type, currency, is_active, is_header, level,
                            liquidity_kind, is_default_liquidity,
                            is_reconcile, created_at, updated_at
                        ) VALUES (
                            :tenant_id, :code, :name, :name_ar, :parent_id, :branch_id,
                            'asset', 'AED', TRUE, FALSE, 3,
                            :liquidity_kind, TRUE,
                            FALSE, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                        )
                        """
                    ),
                    params,
                )


def _default_branch_by_tenant(conn):
    rows = conn.execute(
        sa.text(
            """
            SELECT id, tenant_id
              FROM branches
             WHERE is_active = TRUE
             ORDER BY tenant_id ASC, is_main DESC, id ASC
            """
        )
    ).mappings().all()
    defaults = {}
    for row in rows:
        defaults.setdefault(row["tenant_id"], row["id"])
    return defaults


def _line_ids_for_header_account(conn, tenant_id, parent_account_id, branch_id=None):
    if branch_id is None:
        query = """
            SELECT l.id
              FROM gl_journal_lines l
              JOIN gl_journal_entries e ON e.id = l.entry_id
             WHERE l.account_id = :parent_account_id
               AND e.tenant_id = :tenant_id
               AND e.branch_id IS NULL
        """
        params = {"tenant_id": tenant_id, "parent_account_id": parent_account_id}
    else:
        query = """
            SELECT l.id
              FROM gl_journal_lines l
              JOIN gl_journal_entries e ON e.id = l.entry_id
             WHERE l.account_id = :parent_account_id
               AND e.tenant_id = :tenant_id
               AND e.branch_id = :branch_id
        """
        params = {
            "tenant_id": tenant_id,
            "parent_account_id": parent_account_id,
            "branch_id": branch_id,
        }
    return list(conn.execute(sa.text(query), params).scalars())


def _remap_legacy_header_postings(conn):
    defaults = _default_branch_by_tenant(conn)
    branches = conn.execute(
        sa.text(
            """
            SELECT id, tenant_id
              FROM branches
             WHERE is_active = TRUE
             ORDER BY tenant_id ASC, is_main DESC, id ASC
            """
        )
    ).mappings().all()

    for branch in branches:
        for parent_code in ("1110", "1120"):
            parent = conn.execute(
                sa.text(
                    """
                    SELECT id
                      FROM gl_accounts
                     WHERE tenant_id = :tenant_id AND code = :code
                     LIMIT 1
                    """
                ),
                {"tenant_id": branch["tenant_id"], "code": parent_code},
            ).fetchone()
            child = conn.execute(
                sa.text(
                    """
                    SELECT id
                      FROM gl_accounts
                     WHERE tenant_id = :tenant_id AND code = :code
                     LIMIT 1
                    """
                ),
                {
                    "tenant_id": branch["tenant_id"],
                    "code": _branch_account_code(parent_code, branch["id"]),
                },
            ).fetchone()
            if not parent or not child:
                continue

            line_ids = _line_ids_for_header_account(conn, branch["tenant_id"], parent[0], branch["id"])
            if branch["id"] == defaults.get(branch["tenant_id"]):
                line_ids.extend(_line_ids_for_header_account(conn, branch["tenant_id"], parent[0], None))
            if not line_ids:
                continue

            conn.execute(
                sa.text("UPDATE gl_journal_lines SET account_id = :account_id WHERE id IN :line_ids").bindparams(
                    sa.bindparam("line_ids", expanding=True)
                ),
                {"account_id": child[0], "line_ids": sorted(set(line_ids))},
            )


def upgrade():
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    with op.batch_alter_table("gl_accounts", schema=None) as batch_op:
        if not _has_column(inspector, "gl_accounts", "branch_id"):
            batch_op.add_column(sa.Column("branch_id", sa.Integer(), nullable=True))
            batch_op.create_index(batch_op.f("ix_gl_accounts_branch_id"), ["branch_id"], unique=False)
            batch_op.create_foreign_key("fk_gl_accounts_branch_id", "branches", ["branch_id"], ["id"])

        if not _has_column(inspector, "gl_accounts", "liquidity_kind"):
            batch_op.add_column(sa.Column("liquidity_kind", sa.String(length=20), nullable=True))
            batch_op.create_index(batch_op.f("ix_gl_accounts_liquidity_kind"), ["liquidity_kind"], unique=False)

        if not _has_column(inspector, "gl_accounts", "is_default_liquidity"):
            batch_op.add_column(
                sa.Column(
                    "is_default_liquidity",
                    sa.Boolean(),
                    nullable=False,
                    server_default=sa.text("false"),
                )
            )

        if not _has_column(inspector, "gl_accounts", "bank_name"):
            batch_op.add_column(sa.Column("bank_name", sa.String(length=200), nullable=True))

        if not _has_column(inspector, "gl_accounts", "bank_account_number"):
            batch_op.add_column(sa.Column("bank_account_number", sa.String(length=100), nullable=True))

        if not _has_column(inspector, "gl_accounts", "bank_iban"):
            batch_op.add_column(sa.Column("bank_iban", sa.String(length=50), nullable=True))

        if not _has_column(inspector, "gl_accounts", "bank_swift_code"):
            batch_op.add_column(sa.Column("bank_swift_code", sa.String(length=20), nullable=True))

    _ensure_branch_liquidity_accounts(conn)
    _remap_legacy_header_postings(conn)

    op.execute(
        sa.text(
            """
            UPDATE gl_accounts
               SET is_header = TRUE,
                   liquidity_kind = NULL,
                   is_default_liquidity = FALSE
             WHERE code IN ('1110', '1120')
            """
        )
    )


def downgrade():
    with op.batch_alter_table("gl_accounts", schema=None) as batch_op:
        batch_op.drop_column("bank_swift_code")
        batch_op.drop_column("bank_iban")
        batch_op.drop_column("bank_account_number")
        batch_op.drop_column("bank_name")
        batch_op.drop_column("is_default_liquidity")
        batch_op.drop_index(batch_op.f("ix_gl_accounts_liquidity_kind"))
        batch_op.drop_column("liquidity_kind")
        batch_op.drop_constraint("fk_gl_accounts_branch_id", type_="foreignkey")
        batch_op.drop_index(batch_op.f("ix_gl_accounts_branch_id"))
        batch_op.drop_column("branch_id")
