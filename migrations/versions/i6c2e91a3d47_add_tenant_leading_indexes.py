"""add tenant-leading composite, partial, functional and GIN indexes

Hot tenant-scoped paths (verified in routes/services) run as
``WHERE tenant_id = ? ORDER BY <col> DESC`` but the existing __table_args__
indexes lead with non-tenant columns (e.g. idx_sale_customer_date leads
with customer_id). This migration adds tenant-LEADING composites matched
to the real query paths:

  - sales list:                routes/sales.py:90   ORDER BY sale_date DESC
  - journal entry list:        routes/ledger.py:131 ORDER BY entry_date DESC
  - product catalog:           routes/products.py:721 filter is_active, ORDER BY name
  - customer list:             routes/customers.py:155 ORDER BY name
  - GL account pickers:        routes/ledger.py:53  filter is_active, ORDER BY code
  - sale/journal line joins:   by sale_id/product_id/entry_id/account_id
  - audit log views/cleanup:   routes/owner/database.py:577 by created_at
  - POS open session lookup:   by tenant+branch with status='open'
  - case-insensitive SKU hits: Product.sku == code (services/stock_sync_service.py:28)
  - product/customer search:   ILIKE-free tsvector search path

Partial indexes: no model in this repo has a deleted_at column, so the
only honest partial target is pos_sessions.status='open' (lowercase —
PosSession.STATUS_OPEN == "open").

GIN notes: Arabic has no built-in PG text-search configuration, so
'simple' is used (language-agnostic tokenization; stopword-free). The
two-argument to_tsvector form is IMMUTABLE and therefore index-safe.

PostgreSQL-only: every statement is guarded by the bind dialect so SQLite
test runs (and offline SQL generation against non-PG URLs) emit nothing.

Revision ID: i6c2e91a3d47
Revises: h5d9e3f18c42
Create Date: 2026-07-26 01:10:00.000000

"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "i6c2e91a3d47"
down_revision = "h5d9e3f18c42"
branch_labels = None
depends_on = None


# (name, table, index tail after the table name) — plain B-tree composites.
_BTREE_INDEXES = [
    ("idx_sales_tenant_date", "sales", "(tenant_id, sale_date DESC)"),
    ("idx_sale_lines_tenant_sale", "sale_lines", "(tenant_id, sale_id)"),
    ("idx_sale_lines_tenant_product", "sale_lines", "(tenant_id, product_id)"),
    ("idx_products_tenant_active_name", "products", "(tenant_id, is_active, name)"),
    ("idx_customers_tenant_name", "customers", "(tenant_id, name)"),
    ("idx_gl_entries_tenant_date", "gl_journal_entries", "(tenant_id, entry_date DESC)"),
    ("idx_gl_lines_tenant_entry", "gl_journal_lines", "(tenant_id, entry_id)"),
    ("idx_gl_lines_tenant_account", "gl_journal_lines", "(tenant_id, account_id)"),
    ("idx_gl_accounts_tenant_active_code", "gl_accounts", "(tenant_id, is_active, code)"),
    ("idx_audit_logs_tenant_created", "audit_logs", "(tenant_id, created_at DESC)"),
]

# (name, table, tail) — partial / functional / GIN, all PG-specific.
_PG_SPECIAL_INDEXES = [
    # POS open-session hot path (one open session per branch per tenant).
    (
        "idx_pos_sessions_tenant_open",
        "pos_sessions",
        "(tenant_id, branch_id) WHERE status = 'open'",
    ),
    # Case-insensitive SKU lookups stay inside the tenant prefix.
    (
        "idx_products_tenant_lower_sku",
        "products",
        "(tenant_id, LOWER(sku))",
    ),
    # Full-text search — 'simple' config (see module docstring).
    (
        "idx_products_fts_gin",
        "products",
        "USING gin (to_tsvector('simple'::regconfig, "
        "coalesce(name, '') || ' ' || coalesce(name_ar, '') || ' ' || "
        "coalesce(commercial_name, '') || ' ' || coalesce(description, '')))",
    ),
    (
        "idx_customers_fts_gin",
        "customers",
        "USING gin (to_tsvector('simple'::regconfig, "
        "coalesce(name, '') || ' ' || coalesce(name_ar, '') || ' ' || "
        "coalesce(phone, '') || ' ' || coalesce(email, '')))",
    ),
]

_ALL_INDEX_NAMES = [name for name, _, _ in _BTREE_INDEXES + _PG_SPECIAL_INDEXES]


def _is_postgres():
    return op.get_bind().dialect.name == "postgresql"


def upgrade():
    if not _is_postgres():
        return
    for name, table, tail in _BTREE_INDEXES + _PG_SPECIAL_INDEXES:
        # CONCURRENTLY is intentionally NOT used — it cannot run inside the
        # migration transaction. IF NOT EXISTS keeps the migration idempotent.
        op.execute(f"CREATE INDEX IF NOT EXISTS {name} ON {table} {tail}")


def downgrade():
    if not _is_postgres():
        return
    for name in _ALL_INDEX_NAMES:
        op.execute(f"DROP INDEX IF EXISTS {name}")
