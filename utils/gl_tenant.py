"""Per-tenant GL query and document helpers."""

from __future__ import annotations

from utils.tenanting import get_active_tenant_id


def active_tenant_id(user=None):
    return get_active_tenant_id(user)


def scope_gl_accounts(query, user=None, tenant_id=None):
    from models import GLAccount

    tid = tenant_id if tenant_id is not None else active_tenant_id(user)
    if tid is not None:
        return query.filter(GLAccount.tenant_id == int(tid))
    return query


def scope_journal_entries(query, user=None, tenant_id=None):
    from models import GLJournalEntry

    tid = tenant_id if tenant_id is not None else active_tenant_id(user)
    if tid is not None:
        return query.filter(GLJournalEntry.tenant_id == int(tid))
    return query


def get_gl_account_by_code(code, tenant_id=None, user=None):
    from models import GLAccount

    tid = tenant_id if tenant_id is not None else active_tenant_id(user)
    q = GLAccount.query.filter_by(code=str(code))
    if tid is not None:
        q = q.filter_by(tenant_id=int(tid))
    return q.first()


def reverse_document_gl(reference_type, reference_id, description, tenant_id=None):
    """Reverse GL entries for a document — raises on failure."""
    from services.gl_service import GLService

    types = (
        reference_type
        if isinstance(reference_type, (list, tuple))
        else [reference_type]
    )
    for ref in types:
        GLService.reverse_entry(
            reference_type=ref,
            reference_id=reference_id,
            description=description,
            tenant_id=tenant_id,
        )


def default_report_date_range(days=90):
    from datetime import date, timedelta

    end = date.today()
    start = end - timedelta(days=days)
    return start.isoformat(), end.isoformat()


def scoped_model_query(model, user=None, tenant_id=None):
    from utils.tenanting import tenant_query, model_has_tenant

    if model_has_tenant(model):
        return tenant_query(model, user)
    return model.query


def gl_account_query(user=None, tenant_id=None):
    from models import GLAccount

    return scope_gl_accounts(GLAccount.query, user=user, tenant_id=tenant_id)


def gl_entry_query(user=None, tenant_id=None):
    from models import GLJournalEntry

    return scope_journal_entries(GLJournalEntry.query, user=user, tenant_id=tenant_id)
