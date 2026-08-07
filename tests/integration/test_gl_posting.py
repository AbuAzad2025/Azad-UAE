"""
Integration test: GL posting must reject unbalanced journal entries.
"""

import uuid
from decimal import Decimal

import pytest


class TestGLPostingBalancing:
    def test_gl_posting_rejects_unbalanced_entries(self, app, db_session):
        from models import Branch, Tenant
        from services.gl_helpers import get_account
        from services.gl_posting import GlPostingError, assert_balanced_lines
        from services.gl_service import GLService

        tid = str(uuid.uuid4())[:8]
        tenant = Tenant(
            name=f"Test {tid}",
            name_ar=f"Test {tid}",
            slug=f"test-gl-{tid}",
            default_currency="AED",
            base_currency="AED",
        )
        db_session.add(tenant)
        db_session.flush()

        branch = Branch(tenant_id=tenant.id, name=f"Main {tid}", code=f"BR{tid[:4]}")
        db_session.add(branch)
        db_session.flush()

        # Ensure core GL accounts exist
        GLService.ensure_core_accounts(tenant_id=tenant.id)
        db_session.commit()

        # Resolve account codes to verify they exist
        cogs = get_account("5100", tenant.id)
        sales = get_account("4100", tenant.id)
        assert cogs is not None, "COGS GL account (5100) not found"
        assert sales is not None, "Sales GL account (4100) not found"

        # --- Test 1: assert_balanced_lines rejects unbalanced ---
        unbalanced = [
            {"account_code": "5100", "debit": Decimal("100"), "credit": Decimal("0")},
            {"account_code": "4100", "debit": Decimal("0"), "credit": Decimal("50")},
        ]
        with pytest.raises(GlPostingError) as excinfo:
            assert_balanced_lines(unbalanced, currency="AED")
        err_msg = str(excinfo.value)
        assert "unbalanced" in err_msg.lower() or "غير متوازن" in err_msg

        # --- Test 2: create_journal_entry rejects unbalanced via ValueError ---
        with pytest.raises((ValueError, GlPostingError)):
            GLService.create_journal_entry(
                date=None,
                description="Test unbalanced entry",
                lines=unbalanced,
                user_id=None,
                branch_id=branch.id,
                tenant_id=tenant.id,
                currency="AED",
            )
        db_session.rollback()  # clean up dirty session from the failed entry

        # --- Test 3: Balanced entries pass validation ---
        balanced = [
            {"account_code": "5100", "debit": Decimal("100"), "credit": Decimal("0")},
            {"account_code": "4100", "debit": Decimal("0"), "credit": Decimal("100")},
        ]
        assert_balanced_lines(balanced, currency="AED")

        entry = GLService.create_journal_entry(
            date=None,
            description="Test balanced entry",
            lines=balanced,
            user_id=None,
            branch_id=branch.id,
            tenant_id=tenant.id,
            currency="AED",
        )
        assert entry is not None
        assert entry.is_balanced()

    def test_gl_posting_rejects_empty_lines(self, app, db_session):
        from services.gl_posting import GlPostingError, post_or_fail

        with pytest.raises(GlPostingError, match="بدون سطور قيد"):
            post_or_fail(
                [],
                description="Empty entry",
                tenant_id=1,
            )
