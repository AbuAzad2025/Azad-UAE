"""Tenant-aware GL helpers used by GLService."""
from __future__ import annotations

from datetime import datetime, timezone

from extensions import db
from models import GLAccount, GLJournalEntry


def resolve_tenant_id(branch_id=None, user_id=None):
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
    return int(tenant_id) if tenant_id else None


def get_account(code, tenant_id=None):
    code = str(code)
    if tenant_id is not None:
        return GLAccount.query.filter_by(code=code, tenant_id=int(tenant_id)).first()
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
