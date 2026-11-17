"""Tenant isolation in the GL is a database invariant, not a service convention."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError


def test_a_line_cannot_name_another_tenants_account_or_entry(
    db_session, sample_tenant, sample_gl_accounts, sample_user
):
    from models import GLAccount, GLJournalEntry, GLJournalLine, Tenant
    from utils.tenanting import without_tenant_scope

    cash = GLAccount.query.filter_by(tenant_id=sample_tenant.id, code="1111").first()
    assert cash is not None

    entry = GLJournalEntry(
        tenant_id=sample_tenant.id,
        entry_number="ISO-TEST-ENTRY",
        entry_date=datetime.now(UTC),
        description="tenant isolation test",
        reference_type="manual",
        currency="AED",
        exchange_rate=Decimal("1"),
        total_debit=Decimal("10"),
        total_credit=Decimal("10"),
        status="posted",
        is_posted=True,
    )
    db_session.add(entry)
    db_session.flush()

    with without_tenant_scope():
        other = Tenant(
            name="Isolation Other",
            name_ar="آخر",
            slug="gl-iso-other",
            country="AE",
            vat_country="AE",
            base_currency="AED",
            default_currency="AED",
            default_tax_rate=5,
            prices_include_vat=False,
            is_active=True,
        )
        db_session.add(other)
        db_session.flush()

        # Both ids exist, so the single-column FKs are satisfied. Only the
        # composite (tenant_id, account_id/entry_id) FKs can reject this row.
        db_session.add(
            GLJournalLine(
                tenant_id=other.id,
                entry_id=entry.id,
                account_id=cash.id,
                debit=Decimal("10"),
                credit=Decimal("0"),
            )
        )
        with pytest.raises(IntegrityError):
            db_session.flush()
