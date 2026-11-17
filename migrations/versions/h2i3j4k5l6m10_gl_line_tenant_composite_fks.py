"""Enforce GL tenant isolation in the database, not only in services.

A journal line used to be able to name another tenant's account or entry: the
single-column FKs proved the ids existed but not that they belonged to the
same tenant. Two composite FKs now make that impossible for every writer,
including raw SQL and restored backups.

Existing rows are not re-validated (NOT VALID) so a deploy cannot be blocked by
historical drift; the new constraints apply to every subsequent write. Fresh
databases get the same constraints from the model metadata.

Revision ID: h2i3j4k5l6m10
Revises: h2i3j4k5l6m9
Create Date: 2026-11-17 09:15:00.000000

"""

from alembic import op

revision = "h2i3j4k5l6m10"
down_revision = "h2i3j4k5l6m9"
branch_labels = None
depends_on = None

_UNIQUE_ACCOUNT = "uq_gl_accounts_tenant_id"
_UNIQUE_ENTRY = "uq_gl_entries_tenant_id"
_FK_ENTRY = "fk_gl_lines_tenant_entry_composite"
_FK_ACCOUNT = "fk_gl_lines_tenant_account_composite"


def _constraint_guard(name: str, ddl: str) -> str:
    return (
        f"DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = '{name}') THEN {ddl}; END IF; END $$;"
    )


def upgrade():
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        # SQLite cannot add constraints to an existing table; a fresh SQLite
        # database receives them from db.metadata instead.
        return

    op.execute(
        _constraint_guard(
            _UNIQUE_ACCOUNT,
            "ALTER TABLE gl_accounts ADD CONSTRAINT uq_gl_accounts_tenant_id UNIQUE (tenant_id, id)",
        )
    )
    op.execute(
        _constraint_guard(
            _UNIQUE_ENTRY,
            "ALTER TABLE gl_journal_entries ADD CONSTRAINT uq_gl_entries_tenant_id UNIQUE (tenant_id, id)",
        )
    )
    op.execute(
        _constraint_guard(
            _FK_ENTRY,
            "ALTER TABLE gl_journal_lines ADD CONSTRAINT fk_gl_lines_tenant_entry_composite "
            "FOREIGN KEY (tenant_id, entry_id) REFERENCES gl_journal_entries (tenant_id, id) "
            "ON DELETE RESTRICT NOT VALID",
        )
    )
    op.execute(
        _constraint_guard(
            _FK_ACCOUNT,
            "ALTER TABLE gl_journal_lines ADD CONSTRAINT fk_gl_lines_tenant_account_composite "
            "FOREIGN KEY (tenant_id, account_id) REFERENCES gl_accounts (tenant_id, id) "
            "ON DELETE RESTRICT NOT VALID",
        )
    )


def downgrade():
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    for name in (_FK_ACCOUNT, _FK_ENTRY, _UNIQUE_ENTRY, _UNIQUE_ACCOUNT):
        op.execute(
            f"DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname = '{name}') "
            f"THEN ALTER TABLE gl_journal_lines DROP CONSTRAINT IF EXISTS {name}; "
            f"ALTER TABLE gl_journal_entries DROP CONSTRAINT IF EXISTS {name}; "
            f"ALTER TABLE gl_accounts DROP CONSTRAINT IF EXISTS {name}; END IF; END $$;"
        )
