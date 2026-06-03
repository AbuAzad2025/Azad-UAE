"""Tenant-aware GL helpers used by GLService."""
from __future__ import annotations

from datetime import datetime, timezone

from extensions import db
from models import GLAccount, GLJournalEntry


def resolve_tenant_id(branch_id=None, user_id=None):
    """Resolve tenant_id safely in multi-tenant mode.

    Priority:
      1) branch_id → Branch.tenant_id
      2) user_id  → User.tenant_id
      3) active tenant context (session / g)
      4) Exactly ONE active tenant in DB → auto-pick it
      5) Zero or >1 active tenants → raise ValueError (never guess)

    This prevents GL entries from being silently posted to the wrong company.
    """
    tenant_id = None
    if branch_id:
        from models import Branch
        b = Branch.query.get(branch_id)
        tenant_id = getattr(b, 'tenant_id', None) if b else None
    if tenant_id is None and user_id:
        from models import User
        u = User.query.get(user_id)
        tenant_id = getattr(u, 'tenant_id', None) if u else None
    if tenant_id is None:
        try:
            from utils.tenanting import get_active_tenant_id
            tenant_id = get_active_tenant_id()
        except Exception:
            pass

    # ── LAST RESORT: only safe when exactly 1 active tenant exists ──
    if tenant_id is None:
        try:
            from models import Tenant
            active_count = Tenant.query.filter_by(is_active=True).count()
            if active_count == 1:
                t = Tenant.query.filter_by(is_active=True).first()
                tenant_id = t.id if t else None
            elif active_count == 0:
                raise ValueError(
                    "resolve_tenant_id failed: no active tenants in database. "
                    "Cannot create GL entries without a tenant context."
                )
            else:
                raise ValueError(
                    f"resolve_tenant_id failed: {active_count} active tenants found. "
                    "Auto-selecting one would post to the wrong company. "
                    "Please provide an explicit branch_id, user_id, or active tenant context."
                )
        except ValueError:
            raise
        except Exception as e:
            raise RuntimeError(f"resolve_tenant_id database lookup failed: {e}")

    if tenant_id is None:
        raise ValueError("resolve_tenant_id: could not determine tenant_id under any fallback.")

    return int(tenant_id)


import logging

logger = logging.getLogger(__name__)


def get_account(code, tenant_id=None):
    code = str(code)
    if tenant_id is not None:
        return GLAccount.query.filter_by(code=code, tenant_id=int(tenant_id)).first()
    logger.warning("get_account(%s) without tenant_id — first chart match (legacy fallback)", code)
    return GLAccount.query.filter_by(code=code).order_by(GLAccount.id.asc()).first()


def next_entry_number(tenant_id, entry_date=None):
    entry_date = entry_date or datetime.now(timezone.utc)
    y = entry_date.strftime('%Y')
    query = GLJournalEntry.query.filter(GLJournalEntry.entry_number.like(f'JE-{y}-%'))
    if tenant_id is not None:
        query = query.filter(GLJournalEntry.tenant_id == int(tenant_id))
    latest = query.order_by(GLJournalEntry.entry_number.desc()).first()
    last_num = 0
    if latest:
        try:
            last_num = int(latest.entry_number.split('-')[-1])
        except Exception:
            pass
    return f'JE-{y}-{last_num + 1:04d}'


def assert_period_open(entry_date, tenant_id):
    if tenant_id is None:
        return
    dt = entry_date if isinstance(entry_date, datetime) else datetime.now(timezone.utc)
    from models.gl import GLPeriod
    closed = GLPeriod.query.filter_by(
        tenant_id=int(tenant_id), year=dt.year, month=dt.month, is_closed=True,
    ).first()
    if closed:
        raise ValueError(f'الفترة المحاسبية {dt.year}-{dt.month:02d} مقفلة.')
