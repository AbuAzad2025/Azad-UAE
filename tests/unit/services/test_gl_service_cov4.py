"""Coverage-4 for services/gl_service.py (976 stmts) — helper/report arcs.

Targets (production lines):
- posting_line explicit-account + explicit-concept + no-concept arcs (139-149).
- get_payment_debit_concept case/whitespace/None/bank-alias arcs (152-160).
- get_payment_credit_concept cash/bank/cheque/unknown arcs (163-171).
- get_customer_credit_concept merchant/None arcs (174-179).
- ensure_core_accounts idempotency (525+).
- list_active_accounts / list_all_accounts / find_account_by_code(+miss) /
  find_account_by_id(+miss) / list_header_accounts / list_leaf ordered with
  and without type / list_postable_accounts / search_accounts hit+miss /
  count_active_tenants (1775-1913).
- list_active_budgets with/without branch (1916-1922).
- get_gl_period miss + list_gl_periods (1557-1571).
- FiscalYearService.get_fiscal_year_months default + custom start (1933-1949).
- validate_periods_closed raises on open + returns [] when closed (1952-1968).
- calculate_pl_balance shape/zero-lines (1971-2028).
- close_fiscal_year no-lines raise (2047-2048) + missing-retained raise
  (2052-2054).
- paginate_journal_entries branch/None arcs (1546-1554).
- get_trial_balance smoke (1228+) and build_income_statement smoke.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest

from services.gl_service import FiscalYearService, GLService


class TestPostingLineConcepts:
    def test_explicit_account_and_concept(self):
        line = GLService.posting_line("cash", account="7777", concept_code="BANK", debit=3)
        assert line["account"] == "7777"
        assert line["concept_code"] == "BANK"

    def test_no_concept_key(self):
        line = GLService.posting_line("no_such_key_xyz", account="8888", debit=1)
        assert line["account"] == "8888"
        assert "concept_code" not in line

    def test_debit_concept_variants(self):
        assert GLService.get_payment_debit_concept("  CARD ") == "BANK"
        assert GLService.get_payment_debit_concept("bank") == "BANK"
        assert GLService.get_payment_debit_concept("") == "CASH"
        assert GLService.get_payment_debit_concept("weird") == "CASH"

    def test_credit_concept_variants(self):
        assert GLService.get_payment_credit_concept("  CASH ") == "CASH"
        assert GLService.get_payment_credit_concept("card") == "BANK"
        assert GLService.get_payment_credit_concept("BANK") == "BANK"
        assert GLService.get_payment_credit_concept("") is None

    def test_customer_concept_variants(self):
        assert GLService.get_customer_credit_concept(SimpleNamespace(customer_type="merchant")) == "MERCHANT_CURRENT_ACCOUNT"
        assert GLService.get_customer_credit_concept(SimpleNamespace(customer_type=None)) == "AR"
        assert GLService.get_customer_credit_concept(SimpleNamespace()) == "AR"


class TestAccountLists:
    def test_ensure_core_idempotent(self, db_session, sample_tenant):
        GLService.ensure_core_accounts(tenant_id=sample_tenant.id)
        GLService.ensure_core_accounts(tenant_id=sample_tenant.id)
        assert GLService.count_active_tenants() >= 1

    def test_list_and_find(self, db_session, sample_tenant, sample_gl_accounts):
        assert len(GLService.list_active_accounts()) > 0
        assert len(GLService.list_all_accounts()) > 0
        assert len(GLService.list_postable_accounts()) > 0
        first = GLService.list_all_accounts()[0]
        assert GLService.find_account_by_code(first.code).id == first.id
        assert GLService.find_account_by_code("COV4-NOPE-XYZ") is None
        assert GLService.find_account_by_id(first.id).id == first.id
        assert GLService.find_account_by_id(999999999) is None
        assert isinstance(GLService.list_header_accounts(), list)

    def test_leaf_ordered_both_arcs(self, db_session, sample_tenant, sample_gl_accounts):
        assert isinstance(GLService.list_leaf_accounts_ordered(), list)
        assert isinstance(GLService.list_leaf_accounts_ordered("asset"), list)
        assert isinstance(GLService.list_leaf_accounts_ordered("no-such-type"), list)

    def test_search_hit_and_miss(self, db_session, sample_tenant, sample_gl_accounts):
        first = GLService.list_all_accounts()[0]
        assert GLService.search_accounts(first.code[:3])
        assert GLService.search_accounts("COV4-NOPE-ZZZ-999") == []

    def test_budgets_both_arcs(self, db_session, sample_tenant):
        assert GLService.list_active_budgets(sample_tenant.id) == []
        assert GLService.list_active_budgets(sample_tenant.id, branch_id=12345) == []

    def test_period_helpers(self, db_session, sample_tenant):
        assert GLService.get_gl_period(sample_tenant.id, 1999, 1) is None
        assert GLService.list_gl_periods(sample_tenant.id) == []

    def test_paginate_both_arcs(self, db_session, sample_tenant):
        page = GLService.paginate_journal_entries(page=1, per_page=5)
        assert hasattr(page, "items")
        page_b = GLService.paginate_journal_entries(branch_id=999999999, page=1, per_page=5)
        assert page_b.items == []


class TestFiscalYear:
    def test_months_default_start(self, db_session, sample_tenant):
        sample_tenant.fiscal_year_start = 1
        db_session.flush()
        months = FiscalYearService.get_fiscal_year_months(sample_tenant.id, 2026)
        assert len(months) == 12
        assert months[0] == (2026, 1)
        assert months[-1] == (2026, 12)

    def test_months_custom_start_wraps_year(self, db_session, sample_tenant):
        sample_tenant.fiscal_year_start = 7
        db_session.flush()
        months = FiscalYearService.get_fiscal_year_months(sample_tenant.id, 2025)
        assert months[0] == (2025, 7)
        assert months[-1] == (2026, 6)
        db_session.rollback()

    def test_validate_open_raises(self, db_session, sample_tenant):
        with pytest.raises(ValueError, match="السنة المالية"):
            FiscalYearService.validate_periods_closed(sample_tenant.id, 2026)

    def test_validate_closed_returns_empty(self, db_session, sample_tenant, mocker):
        from models.gl import GLPeriod

        periods = []
        for y, m in FiscalYearService.get_fiscal_year_months(sample_tenant.id, 2026):
            p = GLPeriod(tenant_id=sample_tenant.id, year=y, month=m, is_closed=True)
            db_session.add(p)
            periods.append(p)
        db_session.flush()
        assert FiscalYearService.validate_periods_closed(sample_tenant.id, 2026) == []
        db_session.rollback()

    def test_pl_balance_shape(self, db_session, sample_tenant, sample_gl_accounts):
        out = FiscalYearService.calculate_pl_balance(sample_tenant.id, 2026)
        assert out["fiscal_year"] == 2026
        assert out["total_revenue"] >= Decimal("0")
        assert out["total_expense"] >= Decimal("0")
        assert out["net_income"] == out["total_revenue"] - out["total_expense"]
        assert isinstance(out["lines"], list)

    def test_pl_december_end_date_arc(self, db_session, sample_tenant, sample_gl_accounts):
        sample_tenant.fiscal_year_start = 1
        db_session.flush()
        out = FiscalYearService.calculate_pl_balance(sample_tenant.id, 2026)
        assert (out["end_date"].month, out["end_date"].day) == (12, 31)

    def test_pl_non_december_end_date_arc(self, db_session, sample_tenant, sample_gl_accounts):
        sample_tenant.fiscal_year_start = 7
        db_session.flush()
        out = FiscalYearService.calculate_pl_balance(sample_tenant.id, 2025)
        assert (out["end_date"].month, out["end_date"].day) == (7, 1)
        db_session.rollback()

    def test_close_no_lines_raises(self, db_session, sample_tenant, mocker):
        mocker.patch.object(
            FiscalYearService, "validate_periods_closed", return_value=[]
        )
        mocker.patch.object(
            FiscalYearService, "calculate_pl_balance",
            return_value={"lines": [], "net_income": Decimal("0"),
                          "end_date": None},
        )
        with pytest.raises(ValueError, match="لإغلاقها"):
            FiscalYearService.close_fiscal_year(sample_tenant.id, 2026)

    def test_close_missing_retained_raises(self, db_session, sample_tenant, mocker):
        from models.gl import GLAccount

        GLAccount.query.filter_by(
            tenant_id=sample_tenant.id, code=FiscalYearService.RETAINED_EARNINGS_CODE
        ).delete()
        db_session.flush()
        mocker.patch.object(
            FiscalYearService, "validate_periods_closed", return_value=[]
        )
        mocker.patch.object(
            FiscalYearService, "calculate_pl_balance",
            return_value={"lines": [{"account_id": 1, "balance": Decimal("5"),
                                     "account_type": "revenue"}],
                          "net_income": Decimal("5"), "end_date": None},
        )
        with pytest.raises(ValueError, match="مرحلة"):
            FiscalYearService.close_fiscal_year(sample_tenant.id, 2026)
        db_session.rollback()


class TestReportsSmoke:
    def test_trial_balance_smoke(self, db_session, sample_tenant, sample_gl_accounts):
        out = GLService.get_trial_balance(
            tenant_id=sample_tenant.id, date_from=None, date_to=None
        )
        assert out is not None

    def test_income_statement_smoke(self, db_session, sample_tenant, sample_gl_accounts):
        out = GLService.build_income_statement(
            sample_tenant.id, date_from=None, date_to=None, branch_id=None
        )
        assert out is not None

    def test_accounts_tree_smoke(self, db_session, sample_tenant, sample_gl_accounts):
        out = GLService.get_accounts_tree(tenant_id=sample_tenant.id)
        assert out is not None

    def test_validate_tree_smoke(self, db_session, sample_tenant, sample_gl_accounts):
        out = GLService.validate_account_tree(tenant_id=sample_tenant.id)
        assert out is not None

    def test_balance_sheet_smoke(self, db_session, sample_tenant, sample_gl_accounts):
        out = GLService.build_balance_sheet(
            sample_tenant.id, None, date(2026, 12, 31)
        )
        assert out is not None
