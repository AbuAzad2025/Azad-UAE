import logging
from sqlalchemy import text

logger = logging.getLogger(__name__)


def _branch_liquidity_account_code(parent_code, branch_id):
    return f"{parent_code}-B{int(branch_id)}"


def ensure_branch_liquidity_account(connection, branch, parent_code, liquidity_kind, name_prefix, name_prefix_ar):
    parent = connection.execute(
        text("SELECT id FROM gl_accounts WHERE tenant_id = :tenant_id AND code = :code LIMIT 1"),
        {"tenant_id": branch.tenant_id, "code": parent_code},
    ).fetchone()
    if not parent:
        logger.debug("Skipped %s liquidity account for branch %s: parent %s is missing", liquidity_kind, branch.id, parent_code)
        return
    code = _branch_liquidity_account_code(parent_code, branch.id)
    existing = connection.execute(
        text("SELECT id FROM gl_accounts WHERE tenant_id = :tenant_id AND code = :code LIMIT 1"),
        {"tenant_id": branch.tenant_id, "code": code},
    ).fetchone()
    params = {
        "tenant_id": branch.tenant_id,
        "code": code,
        "name": f"{name_prefix} - {branch.name}",
        "name_ar": f"{name_prefix_ar} {branch.name}",
        "parent_id": parent[0],
        "branch_id": branch.id,
        "liquidity_kind": liquidity_kind,
    }
    if existing:
        connection.execute(
            text("""
                UPDATE gl_accounts SET name = :name, name_ar = :name_ar, parent_id = :parent_id,
                branch_id = :branch_id, type = 'asset', currency = 'AED', is_active = TRUE,
                is_header = FALSE, level = 3, liquidity_kind = :liquidity_kind,
                is_default_liquidity = TRUE, updated_at = CURRENT_TIMESTAMP
                WHERE id = :id
            """),
            {**params, "id": existing[0]},
        )
        return
    connection.execute(
        text("""
            INSERT INTO gl_accounts (tenant_id, code, name, name_ar, parent_id, branch_id,
                type, currency, is_active, is_header, level, liquidity_kind, is_default_liquidity,
                is_reconcile, created_at, updated_at)
            VALUES (:tenant_id, :code, :name, :name_ar, :parent_id, :branch_id,
                'asset', 'AED', TRUE, FALSE, 3, :liquidity_kind, TRUE,
                FALSE, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """),
        params,
    )


def register_branch_event_listeners():
    from models import Branch
    from sqlalchemy import event

    @event.listens_for(Branch, 'after_insert')
    @event.listens_for(Branch, 'after_update')
    def _handler(mapper, connection, target):
        if not target.id or not target.tenant_id or not target.is_active:
            return
        try:
            ensure_branch_liquidity_account(connection, target, "1110", "cash", "Cashbox", "\u0635\u0646\u062f\u0648\u0642")
            ensure_branch_liquidity_account(connection, target, "1120", "bank", "Bank", "\u0628\u0646\u0643")
        except Exception as e:
            logger.error("Failed to ensure financial accounts for branch %s: %s", target.id, e)
            raise
