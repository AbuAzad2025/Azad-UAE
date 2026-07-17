from __future__ import annotations

from datetime import datetime, timezone, date
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from extensions import db
from models import GLAccount, GLJournalLine
from services.gl_account_resolver import GLMappingError
from services.gl_service import GLService, GL_ACCOUNTS


def _balanced_lines(amount=Decimal("100")):
    return [
        {
            "account": "1111",
            "debit": amount,
            "credit": Decimal("0"),
            "description": "cash",
        },
        {
            "account": "4101",
            "debit": Decimal("0"),
            "credit": amount,
            "description": "revenue",
        },
    ]


def _post_entry(entry_id, *, user_id=1):
    """Validate and post a draft journal entry so read methods can find it."""
    from services.advanced_journal_manager import AdvancedJournalEntryManager

    AdvancedJournalEntryManager.validate_entry(
        entry_id=entry_id, validated_by=user_id, commit=False
    )
    AdvancedJournalEntryManager.post_entry(
        entry_id=entry_id, posted_by=user_id, commit=False
    )
    db.session.flush()


class TestPostingHelpers:
    def test_posting_line_with_key(self):
        line = GLService.posting_line("cash", debit=50, description="test")
        assert line["account"] == GL_ACCOUNTS["cash"]
        assert line["concept_code"] == "CASH"
        assert line["debit"] == 50

    def test_posting_line_explicit_account(self):
        line = GLService.posting_line("cash", account="9999", debit=1)
        assert line["account"] == "9999"

    def test_payment_debit_concept(self):
        assert GLService.get_payment_debit_concept("cash") == "CASH"
        assert GLService.get_payment_debit_concept("bank_transfer") == "BANK"
        assert (
            GLService.get_payment_debit_concept("cheque") == "CHEQUES_UNDER_COLLECTION"
        )
        assert GLService.get_payment_debit_concept(None) == "CASH"

    def test_payment_credit_concept(self):
        assert (
            GLService.get_payment_credit_concept("cheque") == "DEFERRED_CHEQUES_PAYABLE"
        )
        assert GLService.get_payment_credit_concept("unknown") is None

    def test_customer_credit_concept(self):
        partner = MagicMock(customer_type="partner")
        merchant = MagicMock(customer_type="merchant")
        regular = MagicMock(customer_type="retail")
        assert (
            GLService.get_customer_credit_concept(partner) == "PARTNER_CURRENT_ACCOUNT"
        )
        assert (
            GLService.get_customer_credit_concept(merchant)
            == "MERCHANT_CURRENT_ACCOUNT"
        )
        assert GLService.get_customer_credit_concept(regular) == "AR"
        assert GLService.get_customer_credit_concept(None) == "AR"


class TestResolveJournalLineAccount:
    def test_missing_account_code_raises(self, sample_tenant):
        with pytest.raises(ValueError, match="required"):
            GLService._resolve_journal_line_account({}, sample_tenant.id)

    def test_unknown_concept_raises(self, sample_tenant):
        with pytest.raises(GLMappingError, match="Unknown GL concept"):
            GLService._resolve_journal_line_account(
                {"concept_code": "NOT_A_REAL_CONCEPT_XYZ"},
                sample_tenant.id,
            )

    def test_legacy_account_resolution(
        self, db_session, sample_tenant, sample_gl_accounts
    ):
        acct = GLService._resolve_journal_line_account(
            {"account": "1111"},
            sample_tenant.id,
        )
        assert acct.code == "1111"

    def test_inactive_account_raises(
        self, db_session, sample_tenant, sample_gl_accounts
    ):
        acct = GLAccount.query.filter_by(
            tenant_id=sample_tenant.id, code="1111"
        ).first()
        acct.is_active = False
        db_session.flush()
        with pytest.raises(ValueError, match="inactive"):
            GLService._resolve_journal_line_account(
                {"account": "1111"}, sample_tenant.id
            )

    def test_header_account_raises(self, db_session, sample_tenant, sample_gl_accounts):
        header = GLAccount(
            tenant_id=sample_tenant.id,
            code="1999",
            name="Header",
            type="asset",
            is_header=True,
            is_active=True,
        )
        db_session.add(header)
        db_session.flush()
        with pytest.raises(ValueError, match="header"):
            GLService._resolve_journal_line_account(
                {"account": "1999"}, sample_tenant.id
            )

    def test_missing_ok_returns_none(self, sample_tenant):
        result = GLService._resolve_journal_line_account(
            {"account": "9999999"},
            sample_tenant.id,
            ensure_core=False,
            missing_ok=True,
        )
        assert result is None


class TestCreateJournalEntry:
    def test_balanced_entry_created(
        self, db_session, sample_tenant, sample_gl_accounts, mocker
    ):
        mocker.patch("services.gl_helpers.assert_period_open")
        entry = GLService.create_journal_entry(
            datetime(2026, 6, 15, tzinfo=timezone.utc),
            "Test entry",
            _balanced_lines(),
            tenant_id=sample_tenant.id,
            user_id=1,
        )
        assert entry.total_debit == entry.total_credit
        assert entry.is_posted is False
        assert entry.status == "draft"
        lines = GLJournalLine.query.filter_by(entry_id=entry.id).all()
        assert len(lines) == 2

    def test_unbalanced_raises(
        self, db_session, sample_tenant, sample_gl_accounts, mocker
    ):
        from services.gl_posting import UnbalancedJournalEntryError

        mocker.patch("services.gl_helpers.assert_period_open")
        bad_lines = [
            {"account": "1111", "debit": Decimal("100"), "credit": Decimal("0")},
            {"account": "4101", "debit": Decimal("0"), "credit": Decimal("50")},
        ]
        with pytest.raises(UnbalancedJournalEntryError):
            GLService.create_journal_entry(
                datetime(2026, 6, 15, tzinfo=timezone.utc),
                "Bad",
                bad_lines,
                tenant_id=sample_tenant.id,
            )

    def test_wrong_branch_tenant_raises(
        self, db_session, sample_tenant, sample_branch, sample_gl_accounts, mocker
    ):
        from models import Tenant, Branch

        other = Tenant(
            name="Other",
            name_ar="Other",
            slug="other-gl-test",
            email="other@test.com",
            country="AE",
            is_active=True,
        )
        db_session.add(other)
        db_session.flush()
        foreign = Branch(tenant_id=other.id, name="Foreign", code="FRN", is_main=True)
        db_session.add(foreign)
        db_session.flush()
        mocker.patch("services.gl_helpers.assert_period_open")
        with pytest.raises(GLMappingError, match="belongs to tenant"):
            GLService.create_journal_entry(
                datetime(2026, 6, 1, tzinfo=timezone.utc),
                "Cross tenant",
                _balanced_lines(),
                tenant_id=sample_tenant.id,
                branch_id=foreign.id,
            )


class TestPostEntry:
    def test_converts_with_exchange_rate(
        self, db_session, sample_tenant, sample_gl_accounts, mocker
    ):
        mocker.patch("services.gl_helpers.assert_period_open")
        lines = [
            {"account": "1111", "debit": Decimal("10"), "credit": Decimal("0")},
            {"account": "4101", "debit": Decimal("0"), "credit": Decimal("10")},
        ]
        entry = GLService.post_entry(
            lines,
            description="FX test",
            tenant_id=sample_tenant.id,
            currency="USD",
            exchange_rate=Decimal("3.67"),
        )
        assert entry is not None
        assert entry.exchange_rate == Decimal("3.67")


class TestVatReport:
    def test_tax_disabled_returns_flag(self, db_session, sample_tenant, mocker):
        mocker.patch("utils.tax_settings.is_tax_enabled", return_value=False)
        result = GLService.get_vat_report(tenant_id=sample_tenant.id)
        assert result["tax_disabled"] is True
        assert result["vat_output"] == 0.0

    def test_vat_report_with_postings(
        self, db_session, sample_tenant, sample_gl_accounts, mocker
    ):
        mocker.patch("services.gl_helpers.assert_period_open")
        mocker.patch("utils.tax_settings.is_tax_enabled", return_value=True)
        entry = GLService.create_journal_entry(
            datetime(2026, 6, 1, tzinfo=timezone.utc),
            "VAT out",
            [
                {"account": "2121", "debit": Decimal("0"), "credit": Decimal("50")},
                {"account": "1111", "debit": Decimal("50"), "credit": Decimal("0")},
            ],
            tenant_id=sample_tenant.id,
        )
        _post_entry(entry.id)
        result = GLService.get_vat_report(tenant_id=sample_tenant.id)
        assert result["vat_output"] >= 0.0


class TestReverseEntry:
    def test_reverse_by_reference(
        self, db_session, sample_tenant, sample_gl_accounts, mocker
    ):
        mocker.patch("services.gl_helpers.assert_period_open")
        GLService.create_journal_entry(
            datetime(2026, 6, 1, tzinfo=timezone.utc),
            "Reversible",
            _balanced_lines(Decimal("75")),
            tenant_id=sample_tenant.id,
            reference_type="sale",
            reference_id=42,
        )
        db_session.commit()
        reversed_entries = GLService.reverse_entry(
            "sale", 42, tenant_id=sample_tenant.id
        )
        assert reversed_entries is not None
        assert len(reversed_entries) >= 1

    def test_reverse_missing_ref_returns_none(self):
        assert GLService.reverse_entry(None, None) is None


class TestLiquidityAccounts:
    def test_get_default_cash(
        self, db_session, sample_tenant, sample_branch, sample_gl_accounts
    ):
        code = GLService.get_default_liquidity_account(
            "cash",
            tenant_id=sample_tenant.id,
            branch_id=sample_branch.id,
        )
        assert code is not None

    def test_unsupported_kind_raises(self, sample_tenant):
        with pytest.raises(ValueError, match="Unsupported"):
            GLService.get_default_liquidity_account(
                "crypto", tenant_id=sample_tenant.id
            )

    def test_payment_debit_account_cash(
        self, db_session, sample_tenant, sample_branch, sample_gl_accounts
    ):
        code = GLService.get_payment_debit_account(
            "cash",
            tenant_id=sample_tenant.id,
            branch_id=sample_branch.id,
        )
        assert code is not None

    def test_payment_debit_cheque_legacy(self, sample_tenant, mocker):
        mocker.patch(
            "services.gl_service.is_dynamic_gl_mapping_enabled", return_value=False
        )
        assert (
            GLService.get_payment_debit_account("cheque", tenant_id=sample_tenant.id)
            == "1150"
        )

    def test_customer_credit_legacy_codes(self, sample_tenant, mocker):
        mocker.patch(
            "services.gl_service.is_dynamic_gl_mapping_enabled", return_value=False
        )
        partner = MagicMock(customer_type="partner")
        merchant = MagicMock(customer_type="merchant")
        assert (
            GLService.get_customer_credit_account(partner, tenant_id=sample_tenant.id)
            == "2150"
        )
        assert (
            GLService.get_customer_credit_account(merchant, tenant_id=sample_tenant.id)
            == "2115"
        )
        assert (
            GLService.get_customer_credit_account(None, tenant_id=sample_tenant.id)
            == "1130"
        )

    def test_payment_credit_account_cheque(
        self, db_session, sample_tenant, sample_gl_accounts, mocker
    ):
        mocker.patch(
            "services.gl_service.is_dynamic_gl_mapping_enabled", return_value=False
        )
        code = GLService.get_payment_credit_account(
            "cheque", tenant_id=sample_tenant.id
        )
        assert code == GL_ACCOUNTS["deferred_cheques"]


class TestManualEntry:
    def test_create_manual_entry(
        self, db_session, sample_tenant, sample_user, sample_gl_accounts, mocker
    ):
        mocker.patch("services.gl_helpers.assert_period_open")
        entry = GLService.create_manual_entry(
            "Manual test",
            _balanced_lines(Decimal("25")),
            created_by=sample_user.id,
            branch_id=sample_user.branch_id,
        )
        assert entry.entry_type == "manual"

    def test_create_manual_invalid_account(
        self, db_session, sample_tenant, sample_user, mocker
    ):
        mocker.patch("services.gl_helpers.assert_period_open")
        with pytest.raises(ValueError, match="غير موجود"):
            GLService.create_manual_entry(
                "Bad manual",
                [{"account": "ZZZZZZ", "debit": 1, "credit": 0}],
                created_by=sample_user.id,
            )


class TestBalancesAndStatements:
    def test_account_balance_for_branch(
        self, db_session, sample_tenant, sample_gl_accounts, mocker
    ):
        mocker.patch("services.gl_helpers.assert_period_open")
        cash = GLAccount.query.filter_by(
            tenant_id=sample_tenant.id, code="1111"
        ).first()
        entry = GLService.create_journal_entry(
            datetime(2026, 6, 1, tzinfo=timezone.utc),
            "Balance test",
            _balanced_lines(Decimal("200")),
            tenant_id=sample_tenant.id,
        )
        _post_entry(entry.id)
        balance = GLService.get_account_balance_for_branch(
            cash.id, tenant_id=sample_tenant.id
        )
        assert balance is not None

    def test_missing_account_returns_none(self, mocker):
        mocker.patch("services.gl_service.db.session.get", return_value=None)
        assert GLService.get_account_balance_for_branch(999999) is None

    def test_account_statement(
        self, db_session, sample_tenant, sample_gl_accounts, mocker
    ):
        mocker.patch("services.gl_helpers.assert_period_open")
        cash = GLAccount.query.filter_by(
            tenant_id=sample_tenant.id, code="1111"
        ).first()
        entry = GLService.create_journal_entry(
            datetime(2026, 6, 10, tzinfo=timezone.utc),
            "Statement",
            _balanced_lines(Decimal("150")),
            tenant_id=sample_tenant.id,
        )
        _post_entry(entry.id)
        stmt = GLService.get_account_statement(
            cash.id,
            date_from=date(2026, 6, 1),
            date_to=date(2026, 6, 30),
            tenant_id=sample_tenant.id,
        )
        assert "transactions" in stmt
        assert stmt["closing_balance"] is not None

    def test_general_ledger(
        self, db_session, sample_tenant, sample_gl_accounts, mocker
    ):
        mocker.patch("services.gl_helpers.assert_period_open")
        entry = GLService.create_journal_entry(
            datetime(2026, 6, 5, tzinfo=timezone.utc),
            "GL",
            _balanced_lines(),
            tenant_id=sample_tenant.id,
        )
        _post_entry(entry.id)
        ledger = GLService.get_general_ledger(
            date_from=date(2026, 6, 1),
            date_to=date(2026, 6, 30),
            tenant_id=sample_tenant.id,
        )
        assert isinstance(ledger, list)
        assert any(item["account_code"] == "1111" for item in ledger)

    def test_partner_ledger(
        self, db_session, sample_tenant, sample_gl_accounts, mocker
    ):
        from models import Partner

        mocker.patch("services.gl_helpers.assert_period_open")
        partner = Partner(tenant_id=sample_tenant.id, name="Ledger Partner", code="LP1")
        db_session.add(partner)
        db_session.flush()
        lines = [
            {
                "account": "1131",
                "debit": Decimal("50"),
                "credit": Decimal("0"),
                "partner_id": partner.id,
            },
            {"account": "4101", "debit": Decimal("0"), "credit": Decimal("50")},
        ]
        entry = GLService.create_journal_entry(
            datetime(2026, 6, 8, tzinfo=timezone.utc),
            "Partner",
            lines,
            tenant_id=sample_tenant.id,
        )
        _post_entry(entry.id)
        result = GLService.get_partner_ledger(partner.id, tenant_id=sample_tenant.id)
        assert result["partner_id"] == partner.id
        assert len(result["transactions"]) >= 1


class TestTrialBalanceAndTree:
    def test_trial_balance(self, db_session, sample_tenant, sample_gl_accounts, mocker):
        mocker.patch("services.gl_helpers.assert_period_open")
        entry = GLService.create_journal_entry(
            datetime(2026, 6, 1, tzinfo=timezone.utc),
            "TB",
            _balanced_lines(Decimal("300")),
            tenant_id=sample_tenant.id,
        )
        _post_entry(entry.id)
        tb = GLService.get_trial_balance(tenant_id=sample_tenant.id)
        assert tb["total_debit"] == tb["total_credit"]

    def test_accounts_tree(self, db_session, sample_tenant, sample_gl_accounts):
        tree = GLService.get_accounts_tree(tenant_id=sample_tenant.id)
        assert isinstance(tree, list)

    def test_ensure_core_accounts(self, db_session, sample_tenant):
        report = GLService.ensure_core_accounts(tenant_id=sample_tenant.id)
        assert "created" in report

    def test_validate_account_tree(self, db_session, sample_tenant, sample_gl_accounts):
        result = GLService.validate_account_tree(tenant_id=sample_tenant.id)
        assert result is not None


class TestAccountCodeForConcept:
    def test_fallback_key(self, sample_tenant, mocker):
        mocker.patch("services.gl_service.resolve_gl_account", return_value=None)
        code = GLService.get_account_code_for_concept(
            "SALES_REVENUE",
            tenant_id=sample_tenant.id,
            fallback_key="sales_revenue",
        )
        assert code == GL_ACCOUNTS["sales_revenue"]

    def test_no_mapping_raises(self, sample_tenant, mocker):
        mocker.patch("services.gl_service.resolve_gl_account", return_value=None)
        with pytest.raises(GLMappingError):
            GLService.get_account_code_for_concept(
                "UNKNOWN_XYZ", tenant_id=sample_tenant.id
            )


class TestReconciliationCheck:
    def test_reconciliation_returns_structure(
        self,
        db_session,
        sample_tenant,
        sample_gl_accounts,
        sample_customer,
        sample_supplier,
    ):
        result = GLService.reconciliation_check(tenant_id=sample_tenant.id)
        assert "ar_gl_balance" in result
        assert "ap_gl_balance" in result
        assert "ar_difference" in result


class TestPaymentConceptsExtended:
    def test_payment_credit_bank(self):
        assert GLService.get_payment_credit_concept("bank_transfer") == "BANK"
        assert GLService.get_payment_credit_concept("card") == "BANK"

    def test_payment_debit_bank_methods(self):
        assert GLService.get_payment_debit_concept("bank") == "BANK"
        assert GLService.get_payment_debit_concept("card") == "BANK"


class TestDynamicMappingPaths:
    def test_resolve_with_dynamic_mapping_account_code_only_raises(
        self, sample_tenant, mocker
    ):
        mocker.patch(
            "services.gl_service.is_dynamic_gl_mapping_enabled", return_value=True
        )
        mocker.patch("services.gl_service.resolve_gl_account", return_value=None)
        with pytest.raises(GLMappingError, match="No approved GL concept"):
            GLService._resolve_journal_line_account(
                {"account": "1111"},
                sample_tenant.id,
            )

    def test_get_customer_credit_dynamic_mapping(self, sample_tenant, mocker):
        mocker.patch(
            "services.gl_service.is_dynamic_gl_mapping_enabled", return_value=True
        )
        acct = MagicMock(code="1131")
        mocker.patch("services.gl_service.resolve_gl_account", return_value=acct)
        code = GLService.get_customer_credit_account(None, tenant_id=sample_tenant.id)
        assert code == "1131"

    def test_get_customer_credit_dynamic_missing_raises(self, sample_tenant, mocker):
        mocker.patch(
            "services.gl_service.is_dynamic_gl_mapping_enabled", return_value=True
        )
        mocker.patch("services.gl_service.resolve_gl_account", return_value=None)
        with pytest.raises(GLMappingError):
            GLService.get_customer_credit_account(None, tenant_id=sample_tenant.id)

    def test_cheque_debit_dynamic_mapping(self, sample_tenant, mocker):
        mocker.patch(
            "services.gl_service.is_dynamic_gl_mapping_enabled", return_value=True
        )
        acct = MagicMock(code="1150")
        mocker.patch("services.gl_service.resolve_gl_account", return_value=acct)
        assert (
            GLService.get_payment_debit_account("cheque", tenant_id=sample_tenant.id)
            == "1150"
        )

    def test_cheque_debit_dynamic_missing_raises(self, sample_tenant, mocker):
        mocker.patch(
            "services.gl_service.is_dynamic_gl_mapping_enabled", return_value=True
        )
        mocker.patch("services.gl_service.resolve_gl_account", return_value=None)
        with pytest.raises(GLMappingError):
            GLService.get_payment_debit_account("cheque", tenant_id=sample_tenant.id)


class TestManualEntryNotes:
    def test_manual_entry_with_notes_commits(
        self, db_session, sample_tenant, sample_user, sample_gl_accounts, mocker
    ):
        mocker.patch("services.gl_helpers.assert_period_open")
        entry = GLService.create_manual_entry(
            "Noted entry",
            _balanced_lines(Decimal("10")),
            created_by=sample_user.id,
            branch_id=sample_user.branch_id,
            notes="audit note",
        )
        assert entry.notes == "audit note"


class TestVatAndTrialFilters:
    def test_vat_report_with_branch_filter(
        self, db_session, sample_tenant, sample_branch, sample_gl_accounts, mocker
    ):
        mocker.patch("services.gl_helpers.assert_period_open")
        mocker.patch("utils.tax_settings.is_tax_enabled", return_value=True)
        entry = GLService.create_journal_entry(
            datetime(2026, 6, 2, tzinfo=timezone.utc),
            "Branch VAT",
            [
                {"account": "2121", "debit": Decimal("0"), "credit": Decimal("20")},
                {"account": "1111", "debit": Decimal("20"), "credit": Decimal("0")},
            ],
            tenant_id=sample_tenant.id,
            branch_id=sample_branch.id,
        )
        _post_entry(entry.id)
        result = GLService.get_vat_report(
            tenant_id=sample_tenant.id, branch_id=sample_branch.id
        )
        assert "vat_output" in result

    def test_trial_balance_with_date_range(
        self, db_session, sample_tenant, sample_gl_accounts, mocker
    ):
        mocker.patch("services.gl_helpers.assert_period_open")
        entry = GLService.create_journal_entry(
            datetime(2026, 5, 1, tzinfo=timezone.utc),
            "Dated TB",
            _balanced_lines(Decimal("40")),
            tenant_id=sample_tenant.id,
        )
        _post_entry(entry.id)
        tb = GLService.get_trial_balance(
            date_from=date(2026, 5, 1),
            date_to=date(2026, 5, 31),
            tenant_id=sample_tenant.id,
        )
        assert tb["total_debit"] >= 0


class TestLiquidityEdgeCases:
    def test_multiple_cash_accounts_requires_branch(
        self, db_session, sample_tenant, sample_gl_accounts
    ):
        cash_accounts = GLAccount.query.filter_by(
            tenant_id=sample_tenant.id,
            liquidity_kind="cash",
            is_active=True,
            is_header=False,
        ).all()
        if len(cash_accounts) > 1:
            with pytest.raises(ValueError, match="branch_id is required"):
                GLService.get_default_liquidity_account(
                    "cash", tenant_id=sample_tenant.id
                )
        else:
            with pytest.raises(ValueError):
                GLService.get_default_liquidity_account(
                    "cash", tenant_id=sample_tenant.id
                )

    def test_payment_credit_bank_path(
        self, db_session, sample_tenant, sample_branch, sample_gl_accounts, mocker
    ):
        mocker.patch(
            "services.gl_service.is_dynamic_gl_mapping_enabled", return_value=False
        )
        code = GLService.get_payment_credit_account(
            "bank_transfer", tenant_id=sample_tenant.id, branch_id=sample_branch.id
        )
        assert code is not None


class TestEnsureCoreLogging:
    def test_ensure_core_accounts_logs_changes(self, db_session, sample_tenant, mocker):
        mocker.patch(
            "services.gl_service.GLTreeBuilder.build",
            return_value={
                "created": [{"code": "9999"}],
                "updated": [],
                "converted": [],
                "deactivated": [],
            },
        )
        mock_logger = mocker.patch("flask.current_app.logger")
        GLService.ensure_core_accounts(tenant_id=sample_tenant.id)
        mock_logger.info.assert_called_once()


class TestGlServiceCoverageGaps:
    def test_payment_credit_concept_cash_and_bank(self):
        assert GLService.get_payment_credit_concept("cash") == "CASH"
        assert GLService.get_payment_credit_concept("bank") == "BANK"

    def test_ensure_core_and_validate_tree_resolve_tenant(self, sample_tenant, mocker):
        mocker.patch(
            "services.gl_helpers.resolve_tenant_id", return_value=sample_tenant.id
        )
        mocker.patch(
            "services.gl_service.GLTreeBuilder.build",
            return_value={
                "created": [],
                "updated": [],
                "converted": [],
                "deactivated": [],
            },
        )
        mocker.patch(
            "services.gl_service.GLTreeBuilder.validate_tree", return_value={"ok": True}
        )
        assert GLService.ensure_core_accounts(tenant_id=None)["created"] == []
        assert GLService.validate_account_tree(tenant_id=None) == {"ok": True}

    def test_resolve_non_posting_concept_raises(self, sample_tenant, mocker):
        mocker.patch(
            "services.gl_service.is_dynamic_gl_mapping_enabled", return_value=True
        )
        with pytest.raises(GLMappingError, match="Non-posting"):
            GLService._resolve_journal_line_account(
                {"concept_code": "LANDED_COST"},
                sample_tenant.id,
            )

    def test_resolve_liquidity_missing_account_code(self, sample_tenant, mocker):
        mocker.patch(
            "services.gl_service.is_dynamic_gl_mapping_enabled", return_value=True
        )
        with pytest.raises(GLMappingError, match="explicit GL account"):
            GLService._resolve_journal_line_account(
                {"concept_code": "CASH"},
                sample_tenant.id,
                branch_id=1,
            )

    def test_resolve_liquidity_wrong_kind(
        self, db_session, sample_tenant, sample_branch, sample_gl_accounts, mocker
    ):
        mocker.patch(
            "services.gl_service.is_dynamic_gl_mapping_enabled", return_value=True
        )
        acct = GLAccount(
            tenant_id=sample_tenant.id,
            branch_id=sample_branch.id,
            code="LCASH1",
            name="Cash Branch",
            type="asset",
            liquidity_kind="bank",
            is_active=True,
            is_header=False,
        )
        db_session.add(acct)
        db_session.flush()
        with pytest.raises(GLMappingError, match="liquidity_kind"):
            GLService._resolve_journal_line_account(
                {"concept_code": "CASH", "account_code": "LCASH1"},
                sample_tenant.id,
                branch_id=sample_branch.id,
            )

    def test_resolve_liquidity_success(
        self, db_session, sample_tenant, sample_branch, mocker
    ):
        mocker.patch(
            "services.gl_service.is_dynamic_gl_mapping_enabled", return_value=True
        )
        acct = GLAccount(
            tenant_id=sample_tenant.id,
            branch_id=sample_branch.id,
            code="LCASH2",
            name="Cash OK",
            type="asset",
            liquidity_kind="cash",
            is_active=True,
            is_header=False,
        )
        db_session.add(acct)
        db_session.flush()
        resolved = GLService._resolve_journal_line_account(
            {"concept_code": "CASH", "account_code": "LCASH2"},
            sample_tenant.id,
            branch_id=sample_branch.id,
        )
        assert resolved.code == "LCASH2"

    def test_resolve_record_requires_explicit_flag(self, sample_tenant, mocker):
        mocker.patch(
            "services.gl_service.is_dynamic_gl_mapping_enabled", return_value=True
        )
        with pytest.raises(GLMappingError, match="explicit_account_allowed"):
            GLService._resolve_journal_line_account(
                {"concept_code": "FIXED_ASSET_ASSET", "account_code": "1240"},
                sample_tenant.id,
            )

    def test_resolve_record_missing_account_code(self, sample_tenant, mocker):
        mocker.patch(
            "services.gl_service.is_dynamic_gl_mapping_enabled", return_value=True
        )
        with pytest.raises(GLMappingError, match="explicit GL account code"):
            GLService._resolve_journal_line_account(
                {"concept_code": "FIXED_ASSET_ASSET", "explicit_account_allowed": True},
                sample_tenant.id,
            )

    def test_resolve_record_explicit_not_found(self, sample_tenant, mocker):
        mocker.patch(
            "services.gl_service.is_dynamic_gl_mapping_enabled", return_value=True
        )
        with pytest.raises(GLMappingError, match="does not exist"):
            GLService._resolve_journal_line_account(
                {
                    "concept_code": "FIXED_ASSET_ASSET",
                    "account_code": "NOPE999",
                    "explicit_account_allowed": True,
                },
                sample_tenant.id,
            )

    def test_resolve_explicit_inactive_header_branch_errors(
        self,
        db_session,
        sample_tenant,
        sample_branch,
        mocker,
    ):
        mocker.patch(
            "services.gl_service.is_dynamic_gl_mapping_enabled", return_value=True
        )
        inactive = GLAccount(
            tenant_id=sample_tenant.id,
            code="INACT1",
            name="Inactive",
            type="asset",
            is_active=False,
            is_header=False,
        )
        header = GLAccount(
            tenant_id=sample_tenant.id,
            code="HEAD1",
            name="Header",
            type="asset",
            is_active=True,
            is_header=True,
        )
        branched = GLAccount(
            tenant_id=sample_tenant.id,
            branch_id=sample_branch.id,
            code="BRAC1",
            name="Branched",
            type="asset",
            is_active=True,
            is_header=False,
        )
        db_session.add_all([inactive, header, branched])
        db_session.flush()
        with pytest.raises(GLMappingError, match="inactive"):
            GLService._resolve_journal_line_account(
                {
                    "concept_code": "FIXED_ASSET_ASSET",
                    "account_code": "INACT1",
                    "explicit_account_allowed": True,
                },
                sample_tenant.id,
            )
        with pytest.raises(GLMappingError, match="header"):
            GLService._resolve_journal_line_account(
                {
                    "concept_code": "FIXED_ASSET_ASSET",
                    "account_code": "HEAD1",
                    "explicit_account_allowed": True,
                },
                sample_tenant.id,
            )
        with pytest.raises(GLMappingError, match="does not exist"):
            GLService._resolve_journal_line_account(
                {
                    "concept_code": "FIXED_ASSET_ASSET",
                    "account_code": "BRAC1",
                    "explicit_account_allowed": True,
                },
                sample_tenant.id,
                branch_id=99999,
            )

    def test_resolve_explicit_branch_tenant_mismatch(
        self,
        db_session,
        sample_tenant,
        sample_branch,
        mocker,
    ):
        from models import Tenant, Branch

        mocker.patch(
            "services.gl_service.is_dynamic_gl_mapping_enabled", return_value=True
        )
        other = Tenant(
            name="Other GL",
            name_ar="Other",
            slug="other-gl-cov",
            email="o@gl.test",
            country="AE",
            is_active=True,
        )
        db_session.add(other)
        db_session.flush()
        foreign = Branch(tenant_id=other.id, name="Foreign", code="FGN", is_main=True)
        db_session.add(foreign)
        db_session.flush()
        acct = GLAccount(
            tenant_id=sample_tenant.id,
            code="REC1",
            name="Record",
            type="asset",
            is_active=True,
            is_header=False,
        )
        db_session.add(acct)
        db_session.flush()
        with pytest.raises(GLMappingError, match="different tenant"):
            GLService._resolve_journal_line_account(
                {
                    "concept_code": "FIXED_ASSET_ASSET",
                    "account_code": "REC1",
                    "explicit_account_allowed": True,
                },
                sample_tenant.id,
                branch_id=foreign.id,
            )

    def test_resolve_record_branch_mismatch_and_no_branch(
        self,
        db_session,
        sample_tenant,
        sample_branch,
        mocker,
    ):
        from models import Branch

        mocker.patch(
            "services.gl_service.is_dynamic_gl_mapping_enabled", return_value=True
        )
        other_branch = Branch(
            tenant_id=sample_tenant.id,
            name="Other Br",
            code="OBR2",
            is_main=False,
        )
        db_session.add(other_branch)
        db_session.flush()
        rec_acct = GLAccount(
            tenant_id=sample_tenant.id,
            branch_id=sample_branch.id,
            code="REC2",
            name="Record Br",
            type="asset",
            is_active=True,
            is_header=False,
        )
        db_session.add(rec_acct)
        db_session.flush()
        with pytest.raises(GLMappingError, match="record mode"):
            GLService._resolve_journal_line_account(
                {
                    "concept_code": "FIXED_ASSET_ASSET",
                    "account_code": "REC2",
                    "explicit_account_allowed": True,
                },
                sample_tenant.id,
                branch_id=other_branch.id,
            )
        with pytest.raises(GLMappingError, match="branch_id is required to be None"):
            GLService._resolve_journal_line_account(
                {
                    "concept_code": "FIXED_ASSET_ASSET",
                    "account_code": "REC2",
                    "explicit_account_allowed": True,
                },
                sample_tenant.id,
            )

    def test_resolve_liquidity_branch_mismatch(
        self,
        db_session,
        sample_tenant,
        sample_branch,
        mocker,
    ):
        from models import Branch

        mocker.patch(
            "services.gl_service.is_dynamic_gl_mapping_enabled", return_value=True
        )
        other_branch = Branch(
            tenant_id=sample_tenant.id,
            name="Liq Other",
            code="LBR2",
            is_main=False,
        )
        db_session.add(other_branch)
        db_session.flush()
        liq = GLAccount(
            tenant_id=sample_tenant.id,
            branch_id=sample_branch.id,
            code="LIQ3",
            name="Liq",
            type="asset",
            liquidity_kind="cash",
            is_active=True,
            is_header=False,
        )
        db_session.add(liq)
        db_session.flush()
        with pytest.raises(GLMappingError, match="liquidity mode"):
            GLService._resolve_journal_line_account(
                {"concept_code": "CASH", "account_code": "LIQ3"},
                sample_tenant.id,
                branch_id=other_branch.id,
            )

    def test_resolve_mapping_dynamic_enabled(self, sample_tenant, mocker):
        mocker.patch(
            "services.gl_service.is_dynamic_gl_mapping_enabled", return_value=True
        )
        acct = MagicMock(code="4100")
        mocker.patch("services.gl_service.resolve_gl_account", return_value=acct)
        resolved = GLService._resolve_journal_line_account(
            {"concept_code": "SALES_REVENUE"},
            sample_tenant.id,
        )
        assert resolved.code == "4100"

    def test_resolve_dynamic_disabled_concept_resolves(self, sample_tenant, mocker):
        mocker.patch(
            "services.gl_service.is_dynamic_gl_mapping_enabled", return_value=False
        )
        acct = MagicMock(code="4100", is_header=False, is_active=True)
        mocker.patch("services.gl_service.resolve_gl_account", return_value=acct)
        resolved = GLService._resolve_journal_line_account(
            {"concept_code": "SALES_REVENUE"},
            sample_tenant.id,
        )
        assert resolved.code == "4100"

    def test_resolve_legacy_ensure_core_creates_account(
        self, db_session, sample_tenant, mocker
    ):
        mocker.patch(
            "services.gl_service.is_dynamic_gl_mapping_enabled", return_value=False
        )
        mocker.patch("services.gl_service.resolve_gl_account", return_value=None)
        orphan = GLAccount(
            tenant_id=sample_tenant.id,
            code="8888",
            name="Orphan",
            type="asset",
            is_active=True,
            is_header=False,
        )
        db_session.add(orphan)
        db_session.flush()
        mocker.patch("services.gl_helpers.get_account", side_effect=[None, orphan])
        mocker.patch.object(GLService, "ensure_core_accounts", return_value={})
        resolved = GLService._resolve_journal_line_account(
            {"account": "8888"},
            sample_tenant.id,
            ensure_core=True,
        )
        assert resolved.code == "8888"

    def test_create_journal_entry_missing_branch(
        self, db_session, sample_tenant, sample_gl_accounts, mocker
    ):
        mocker.patch("services.gl_helpers.assert_period_open")
        with pytest.raises(GLMappingError, match="does not exist"):
            GLService.create_journal_entry(
                datetime(2026, 6, 1, tzinfo=timezone.utc),
                "No branch",
                _balanced_lines(),
                tenant_id=sample_tenant.id,
                branch_id=99999,
            )

    def test_create_journal_entry_currency_exception_fallback(
        self,
        db_session,
        sample_tenant,
        sample_gl_accounts,
        mocker,
    ):
        mocker.patch("services.gl_helpers.assert_period_open")

        def _get(model, pk):
            if model.__name__ == "Tenant":
                raise RuntimeError("tenant lookup failed")
            return None

        mocker.patch("services.gl_service.db.session.get", side_effect=_get)
        mocker.patch(
            "services.gl_service.resolve_tenant_base_currency", return_value="AED"
        )
        entry = GLService.create_journal_entry(
            datetime(2026, 6, 1, tzinfo=timezone.utc),
            "Currency fallback",
            _balanced_lines(),
            tenant_id=sample_tenant.id,
        )
        assert entry.currency == "AED"

    def test_create_journal_entry_line_branch_errors(
        self,
        db_session,
        sample_tenant,
        sample_branch,
        sample_gl_accounts,
        mocker,
    ):
        from models import Tenant, Branch

        mocker.patch("services.gl_helpers.assert_period_open")
        other = Tenant(
            name="Line Other",
            name_ar="O",
            slug="line-other-gl",
            email="l@t.test",
            country="AE",
            is_active=True,
        )
        db_session.add(other)
        db_session.flush()
        foreign = Branch(
            tenant_id=other.id, name="Line Foreign", code="LFR", is_main=True
        )
        db_session.add(foreign)
        db_session.flush()
        lines_missing = [
            {
                "account": "1111",
                "debit": Decimal("10"),
                "credit": Decimal("0"),
                "branch_id": 88888,
            },
            {"account": "4101", "debit": Decimal("0"), "credit": Decimal("10")},
        ]
        with pytest.raises(GLMappingError, match="Line branch"):
            GLService.create_journal_entry(
                datetime(2026, 6, 1, tzinfo=timezone.utc),
                "Bad line branch",
                lines_missing,
                tenant_id=sample_tenant.id,
            )
        lines_cross = [
            {
                "account": "1111",
                "debit": Decimal("10"),
                "credit": Decimal("0"),
                "branch_id": foreign.id,
            },
            {"account": "4101", "debit": Decimal("0"), "credit": Decimal("10")},
        ]
        with pytest.raises(GLMappingError, match="belongs to tenant"):
            GLService.create_journal_entry(
                datetime(2026, 6, 1, tzinfo=timezone.utc),
                "Cross line branch",
                lines_cross,
                tenant_id=sample_tenant.id,
            )

    def test_post_entry_negative_rate_foreign_currency(
        self, db_session, sample_tenant, sample_gl_accounts, mocker
    ):
        mocker.patch("services.gl_helpers.assert_period_open")
        mocker.patch(
            "services.gl_service.resolve_tenant_base_currency", return_value="AED"
        )
        entry = GLService.post_entry(
            _balanced_lines(Decimal("5")),
            description="Negative rate",
            tenant_id=sample_tenant.id,
            currency="USD",
            exchange_rate=-1,
        )
        assert entry.exchange_rate == Decimal("1")

    def test_vat_report_partial_accounts(self, sample_tenant, mocker):
        mocker.patch("utils.tax_settings.is_tax_enabled", return_value=True)
        mocker.patch(
            "services.gl_service.GLService._resolve_journal_line_account",
            side_effect=[None, MagicMock(id=1)],
        )
        result = GLService.get_vat_report(tenant_id=sample_tenant.id)
        assert result["vat_output"] == 0.0

    def test_vat_report_with_date_filters(
        self,
        db_session,
        sample_tenant,
        sample_gl_accounts,
        mocker,
    ):
        mocker.patch("services.gl_helpers.assert_period_open")
        mocker.patch("utils.tax_settings.is_tax_enabled", return_value=True)
        entry = GLService.create_journal_entry(
            datetime(2026, 6, 3, tzinfo=timezone.utc),
            "VAT dated",
            [
                {"account": "2121", "debit": Decimal("0"), "credit": Decimal("15")},
                {"account": "1111", "debit": Decimal("15"), "credit": Decimal("0")},
            ],
            tenant_id=sample_tenant.id,
        )
        _post_entry(entry.id)
        result = GLService.get_vat_report(
            tenant_id=sample_tenant.id,
            date_from=date(2026, 6, 1),
            date_to=date(2026, 6, 30),
        )
        assert result["vat_output"] >= 0.0

    def test_vat_report_both_accounts_missing(self, sample_tenant, mocker):
        mocker.patch("utils.tax_settings.is_tax_enabled", return_value=True)
        mocker.patch(
            "services.gl_service.GLService._resolve_journal_line_account",
            return_value=None,
        )
        result = GLService.get_vat_report(tenant_id=sample_tenant.id)
        assert result["vat_output"] == 0.0

    def test_reverse_entry_resolves_tenant(
        self, db_session, sample_tenant, sample_gl_accounts, mocker
    ):
        mocker.patch("services.gl_helpers.assert_period_open")
        mocker.patch(
            "services.gl_helpers.resolve_tenant_id", return_value=sample_tenant.id
        )
        GLService.create_journal_entry(
            datetime(2026, 6, 1, tzinfo=timezone.utc),
            "Rev",
            _balanced_lines(Decimal("30")),
            tenant_id=sample_tenant.id,
            reference_type="sale",
            reference_id=77,
        )
        db_session.commit()
        reversed_entries = GLService.reverse_entry("sale", 77)
        assert reversed_entries is not None

    def test_default_liquidity_single_account(self, db_session, sample_tenant, mocker):
        mocker.patch.object(GLService, "ensure_core_accounts", return_value={})
        solo = GLAccount(
            tenant_id=sample_tenant.id,
            code="SOLO1",
            name="Solo Cash",
            type="asset",
            liquidity_kind="cash",
            is_active=True,
            is_header=False,
            is_default_liquidity=True,
        )
        db_session.add(solo)
        db_session.flush()
        assert (
            GLService.get_default_liquidity_account("cash", tenant_id=sample_tenant.id)
            == "SOLO1"
        )

    def test_default_liquidity_branch_missing(
        self, db_session, sample_tenant, sample_branch, mocker
    ):
        mocker.patch.object(GLService, "ensure_core_accounts", return_value={})
        with pytest.raises(ValueError, match="branch_id"):
            GLService.get_default_liquidity_account(
                "cash",
                tenant_id=sample_tenant.id,
                branch_id=sample_branch.id,
            )

    def test_payment_debit_bank_and_default(
        self, db_session, sample_tenant, sample_branch, mocker
    ):
        mocker.patch(
            "services.gl_service.is_dynamic_gl_mapping_enabled", return_value=False
        )
        mocker.patch.object(
            GLService, "get_default_liquidity_account", return_value="1120"
        )
        assert (
            GLService.get_payment_debit_account(
                "bank_transfer", tenant_id=sample_tenant.id
            )
            == "1120"
        )
        assert (
            GLService.get_payment_debit_account("card", tenant_id=sample_tenant.id)
            == "1120"
        )
        assert (
            GLService.get_payment_debit_account("wire", tenant_id=sample_tenant.id)
            == "1120"
        )

    def test_manual_entry_branch_from_user_and_current_user(
        self,
        db_session,
        sample_tenant,
        sample_user,
        sample_gl_accounts,
        mocker,
    ):
        mocker.patch("services.gl_helpers.assert_period_open")
        entry = GLService.create_manual_entry(
            "User branch",
            _balanced_lines(Decimal("12")),
            created_by=sample_user.id,
        )
        assert entry.branch_id == sample_user.branch_id

        mock_user = MagicMock()
        mock_user.is_authenticated = True
        mock_user.id = sample_user.id
        mock_user.branch_id = sample_user.branch_id
        mocker.patch("flask_login.current_user", mock_user)
        entry2 = GLService.create_manual_entry(
            "Current user branch",
            _balanced_lines(Decimal("8")),
        )
        assert entry2.branch_id == sample_user.branch_id

    def test_account_balance_branch_and_liability(
        self,
        db_session,
        sample_tenant,
        sample_branch,
        sample_gl_accounts,
        mocker,
    ):
        mocker.patch("services.gl_helpers.assert_period_open")
        payable = GLAccount.query.filter_by(
            tenant_id=sample_tenant.id, code="2111"
        ).first()
        entry = GLService.create_journal_entry(
            datetime(2026, 6, 4, tzinfo=timezone.utc),
            "Payable",
            [
                {"account": "2111", "debit": Decimal("0"), "credit": Decimal("100")},
                {"account": "1111", "debit": Decimal("100"), "credit": Decimal("0")},
            ],
            tenant_id=sample_tenant.id,
            branch_id=sample_branch.id,
        )
        _post_entry(entry.id)
        balance = GLService.get_account_balance_for_branch(
            payable.id, branch_id=sample_branch.id
        )
        assert balance is not None
        assert balance != 0

    def test_account_statement_branch_and_liability(
        self,
        db_session,
        sample_tenant,
        sample_branch,
        sample_gl_accounts,
        mocker,
    ):
        mocker.patch("services.gl_helpers.assert_period_open")
        payable = GLAccount.query.filter_by(
            tenant_id=sample_tenant.id, code="2111"
        ).first()
        entry = GLService.create_journal_entry(
            datetime(2026, 6, 6, tzinfo=timezone.utc),
            "Stmt payable",
            [
                {"account": "2111", "debit": Decimal("0"), "credit": Decimal("60")},
                {"account": "1111", "debit": Decimal("60"), "credit": Decimal("0")},
            ],
            tenant_id=sample_tenant.id,
            branch_id=sample_branch.id,
        )
        _post_entry(entry.id)
        stmt = GLService.get_account_statement(
            payable.id,
            date_from=date(2026, 6, 1),
            date_to=date(2026, 6, 30),
            branch_id=sample_branch.id,
        )
        assert stmt["transactions"]
        assert stmt["closing_balance"] is not None

    def test_general_ledger_branch_filter(
        self,
        db_session,
        sample_tenant,
        sample_branch,
        sample_gl_accounts,
        mocker,
    ):
        mocker.patch("services.gl_helpers.assert_period_open")
        entry = GLService.create_journal_entry(
            datetime(2026, 6, 7, tzinfo=timezone.utc),
            "GL branch",
            _balanced_lines(Decimal("45")),
            tenant_id=sample_tenant.id,
            branch_id=sample_branch.id,
        )
        _post_entry(entry.id)
        ledger = GLService.get_general_ledger(
            branch_id=sample_branch.id,
            tenant_id=sample_tenant.id,
        )
        assert isinstance(ledger, list)

    def test_partner_ledger_filters(
        self,
        db_session,
        sample_tenant,
        sample_branch,
        sample_gl_accounts,
        mocker,
    ):
        from models import Partner

        mocker.patch("services.gl_helpers.assert_period_open")
        partner = Partner(tenant_id=sample_tenant.id, name="Filter Partner", code="FP1")
        db_session.add(partner)
        db_session.flush()
        entry = GLService.create_journal_entry(
            datetime(2026, 6, 9, tzinfo=timezone.utc),
            "Partner filt",
            [
                {
                    "account": "1131",
                    "debit": Decimal("25"),
                    "credit": Decimal("0"),
                    "partner_id": partner.id,
                },
                {"account": "4101", "debit": Decimal("0"), "credit": Decimal("25")},
            ],
            tenant_id=sample_tenant.id,
            branch_id=sample_branch.id,
        )
        _post_entry(entry.id)
        result = GLService.get_partner_ledger(
            partner.id,
            date_from=date(2026, 6, 1),
            date_to=date(2026, 6, 30),
            branch_id=sample_branch.id,
            tenant_id=sample_tenant.id,
        )
        assert result["partner_id"] == partner.id

    def test_trial_balance_branch_filter(
        self,
        db_session,
        sample_tenant,
        sample_branch,
        sample_gl_accounts,
        mocker,
    ):
        mocker.patch("services.gl_helpers.assert_period_open")
        entry = GLService.create_journal_entry(
            datetime(2026, 6, 11, tzinfo=timezone.utc),
            "TB branch",
            _balanced_lines(Decimal("55")),
            tenant_id=sample_tenant.id,
            branch_id=sample_branch.id,
        )
        _post_entry(entry.id)
        tb = GLService.get_trial_balance(
            branch_id=sample_branch.id, tenant_id=sample_tenant.id
        )
        assert tb["total_debit"] >= 0

    def test_account_code_for_concept_mapping_error_fallback(
        self, sample_tenant, mocker
    ):
        mocker.patch(
            "services.gl_service.resolve_gl_account",
            side_effect=GLMappingError(
                tenant_id=sample_tenant.id,
                concept_code="X",
                branch_id=None,
                issue="fail",
            ),
        )
        code = GLService.get_account_code_for_concept(
            "SALES_REVENUE",
            tenant_id=sample_tenant.id,
            fallback_key="sales_revenue",
        )
        assert code == GL_ACCOUNTS["sales_revenue"]

    def test_resolve_record_mode_branch_id_none_on_account(
        self,
        db_session,
        sample_tenant,
        sample_branch,
        mocker,
    ):
        from models import Branch

        mocker.patch(
            "services.gl_service.is_dynamic_gl_mapping_enabled", return_value=True
        )
        other_branch = Branch(
            tenant_id=sample_tenant.id,
            name="Rec Other",
            code="RBR3",
            is_main=False,
        )
        db_session.add(other_branch)
        db_session.flush()
        rec_acct = GLAccount(
            tenant_id=sample_tenant.id,
            branch_id=other_branch.id,
            code="REC3",
            name="Record Other Br",
            type="asset",
            is_active=True,
            is_header=False,
        )
        db_session.add(rec_acct)
        db_session.flush()
        with pytest.raises(GLMappingError, match="record mode"):
            GLService._resolve_journal_line_account(
                {
                    "concept_code": "FIXED_ASSET_ASSET",
                    "account_code": "REC3",
                    "explicit_account_allowed": True,
                },
                sample_tenant.id,
                branch_id=sample_branch.id,
            )

    def test_post_entry_clamps_zero_rate(
        self, db_session, sample_tenant, sample_gl_accounts, mocker
    ):
        mocker.patch("services.gl_helpers.assert_period_open")
        mocker.patch(
            "services.gl_service.resolve_tenant_base_currency", return_value="AED"
        )
        entry = GLService.post_entry(
            _balanced_lines(Decimal("7")),
            description="Clamp rate",
            tenant_id=sample_tenant.id,
            currency="USD",
            exchange_rate=Decimal("0"),
        )
        assert entry.exchange_rate == Decimal("1")

    def test_account_code_for_concept_resolves_mapping(self, sample_tenant, mocker):
        acct = MagicMock(code="4100")
        mocker.patch("services.gl_service.resolve_gl_account", return_value=acct)
        code = GLService.get_account_code_for_concept(
            "SALES_REVENUE", tenant_id=sample_tenant.id
        )
        assert code == "4100"

    def test_reconciliation_dynamic_concept_line(
        self, db_session, sample_tenant, sample_gl_accounts, mocker
    ):
        mocker.patch(
            "services.gl_account_resolver.is_dynamic_gl_mapping_enabled",
            return_value=True,
        )
        acct = GLAccount.query.filter_by(
            tenant_id=sample_tenant.id, code="1131"
        ).first()
        mocker.patch("services.gl_service.resolve_gl_account", return_value=acct)
        result = GLService.reconciliation_check(tenant_id=sample_tenant.id)
        assert result["ar_gl_balance"] >= 0.0

    def test_reconciliation_legacy_missing_account_returns_zero(
        self,
        db_session,
        sample_tenant,
        mocker,
    ):
        mocker.patch(
            "services.gl_account_resolver.is_dynamic_gl_mapping_enabled",
            return_value=False,
        )
        mocker.patch("services.gl_helpers.get_account", return_value=None)
        result = GLService.reconciliation_check(tenant_id=sample_tenant.id)
        assert result["ar_gl_balance"] == 0.0
        assert result["ap_gl_balance"] == 0.0

    def test_reconciliation_dynamic_with_account(
        self,
        db_session,
        sample_tenant,
        sample_branch,
        sample_gl_accounts,
        sample_customer,
        sample_supplier,
        mocker,
    ):
        mocker.patch(
            "services.gl_account_resolver.is_dynamic_gl_mapping_enabled",
            return_value=True,
        )
        acct = GLAccount.query.filter_by(
            tenant_id=sample_tenant.id, code="1131"
        ).first()
        mocker.patch("services.gl_service.resolve_gl_account", return_value=acct)
        result = GLService.reconciliation_check(
            tenant_id=sample_tenant.id,
            branch_id=sample_branch.id,
        )
        assert "ap_difference" in result

    def test_payment_credit_cash_and_default(
        self,
        db_session,
        sample_tenant,
        sample_branch,
        mocker,
    ):
        mocker.patch.object(
            GLService, "get_default_liquidity_account", return_value="1110"
        )
        assert (
            GLService.get_payment_credit_account("cash", tenant_id=sample_tenant.id)
            == "1110"
        )
        assert (
            GLService.get_payment_credit_account("wire", tenant_id=sample_tenant.id)
            == "1110"
        )

    def test_reconciliation_legacy_path(
        self,
        db_session,
        sample_tenant,
        sample_branch,
        sample_gl_accounts,
        sample_customer,
        sample_supplier,
        mocker,
    ):
        mocker.patch(
            "services.gl_account_resolver.is_dynamic_gl_mapping_enabled",
            return_value=False,
        )
        result = GLService.reconciliation_check(
            tenant_id=sample_tenant.id, branch_id=sample_branch.id
        )
        assert "ar_difference" in result

    def test_resolve_record_success(
        self,
        db_session,
        sample_tenant,
        sample_branch,
        mocker,
    ):
        mocker.patch(
            "services.gl_service.is_dynamic_gl_mapping_enabled", return_value=True
        )
        rec = GLAccount(
            tenant_id=sample_tenant.id,
            branch_id=sample_branch.id,
            code="FA1",
            name="Fixed Asset",
            type="asset",
            is_active=True,
            is_header=False,
        )
        db_session.add(rec)
        db_session.flush()
        resolved = GLService._resolve_journal_line_account(
            {
                "concept_code": "FIXED_ASSET_ASSET",
                "account_code": "FA1",
                "explicit_account_allowed": True,
            },
            sample_tenant.id,
            branch_id=sample_branch.id,
        )
        assert resolved.code == "FA1"
