"""TestGLServiceCov8 — remaining gl_service arcs: dashboard, statement/ledger
filter variants, concept fallbacks, manual-entry validation, liquidity,
dynamic-mapping and entry helpers.

Targets (services/gl_service.py):
- get_admin_dashboard_stats (1818-1858) with ambient tenant, real posted
  lines (incl. a >1000 balance), cheques and a payment vault.
- get_account_statement miss (940), tenant/branch/date variants
  (949-951, 954-957, 957-962, 968-993, 975-977).
- get_general_ledger tenant/branch/date variants + empty-tenant early
  return (1044-1046, 1048, 1054-1056).
- get_partner_ledger branch + tenant-None arcs (1144-1146, 1159-1161).
- get_accounts_tree / build_income_statement / build_balance_sheet /
  get_trial_balance / get_all_account_balances tenant-None + filter arcs
  (1205-1207, 1246-1248, 1264-1266, 1342-1344, 1345, 1365-1367, 1583,
  1674-1676, 1676-1678).
- reverse_entry tenant-None arc (758-760).
- get_account_code_for_concept fallback + no-fallback raise (1413-1426).
- _reconciliation_concept_balance unknown concept (1467).
- create_manual_entry branch/user resolution + header/inactive raises
  (865-875, 870-875, 872-875, 889, 891).
- _resolve_journal_line_account missing-code raise (365) and
  create_journal_entry header raise (474).
- get_default_liquidity_account ambiguous raise (795).
- Dynamic-mapping arcs via flag patch (257-275, 267-275, 326-328,
  333-336, 336-345, 576, 580, 828-836).
- ensure_gl_mappings disabled early return (573).
- get_scoped_account_or_404 / get_entry_or_404 / list_payment_vaults /
  paginate_all_entries (1541-1543, 1790-1792, 1886-1889, 1893-1895).
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest
from flask import g

from models import GLJournalEntry, GLJournalLine
from services.gl_service import GL_ACCOUNTS, GLService


def _pick_account(sample_tenant, code_prefix, account_type):
    from models import GLAccount

    acc = (
        GLAccount.query.filter(
            GLAccount.tenant_id == sample_tenant.id,
            GLAccount.code.startswith(code_prefix),
            GLAccount.type == account_type,
            GLAccount.is_header.is_(False),
            GLAccount.is_active,
        )
        .order_by(GLAccount.code)
        .first()
    )
    assert acc is not None, f"no {account_type} for prefix {code_prefix}"
    return acc


def _seed_posted_lines(db_session, sample_tenant, entry_specs, branch_id=None):
    entries = []
    for idx, specs in enumerate(entry_specs):
        total_debit = sum(d for _, d, _ in specs)
        total_credit = sum(c for _, _, c in specs)
        entry = GLJournalEntry(
            tenant_id=sample_tenant.id,
            entry_number=f"cov8-{idx}",
            entry_date=datetime(2026, 3, 10, 9, 0, 0),
            description="cov8 real gl report",
            total_debit=total_debit,
            total_credit=total_credit,
            status="posted",
            is_posted=True,
            branch_id=branch_id,
        )
        db_session.add(entry)
        db_session.flush()
        for account, debit, credit in specs:
            db_session.add(
                GLJournalLine(
                    tenant_id=sample_tenant.id,
                    entry_id=entry.id,
                    account_id=account.id,
                    debit=debit,
                    credit=credit,
                    amount_aed=debit - credit,
                )
            )
        entries.append(entry)
    db_session.commit()
    return entries


def _cleanup_posted_lines(db_session, entries):
    entry_ids = [e.id for e in entries]
    GLJournalLine.query.filter(GLJournalLine.entry_id.in_(entry_ids)).delete(synchronize_session=False)
    GLJournalEntry.query.filter(GLJournalEntry.id.in_(entry_ids)).delete(synchronize_session=False)
    db_session.commit()


def _posted_specs(sample_tenant):
    asset = _pick_account(sample_tenant, "11", "asset")
    liability = _pick_account(sample_tenant, "21", "liability")
    revenue = _pick_account(sample_tenant, "4", "revenue")
    expense = _pick_account(sample_tenant, "5", "expense")
    equity = _pick_account(sample_tenant, "3", "equity")
    return [
        [(asset, Decimal("500"), Decimal("0")), (equity, Decimal("0"), Decimal("500"))],
        [(asset, Decimal("300"), Decimal("0")), (liability, Decimal("0"), Decimal("300"))],
        [(revenue, Decimal("0"), Decimal("5000")), (asset, Decimal("5000"), Decimal("0"))],
        [(expense, Decimal("200"), Decimal("0")), (asset, Decimal("0"), Decimal("200"))],
    ]


class TestAdminDashboard:
    def test_dashboard_full(self, db_session, sample_tenant, sample_gl_accounts, app):
        from models import Cheque, PaymentVault

        entries = _seed_posted_lines(db_session, sample_tenant, _posted_specs(sample_tenant))
        cheques = [
            Cheque(
                tenant_id=sample_tenant.id,
                cheque_number="COV8-1",
                cheque_bank_number="B1",
                cheque_type="incoming",
                bank_name="Bank",
                amount=Decimal("10"),
                issue_date=date(2026, 3, 1),
                due_date=date(2026, 4, 1),
                status="pending",
            ),
            Cheque(
                tenant_id=sample_tenant.id,
                cheque_number="COV8-2",
                cheque_bank_number="B2",
                cheque_type="outgoing",
                bank_name="Bank",
                amount=Decimal("20"),
                issue_date=date(2026, 3, 1),
                due_date=date(2026, 4, 1),
                status="cleared",
            ),
        ]
        for cheque in cheques:
            db_session.add(cheque)
        vault = PaymentVault(tenant_id=sample_tenant.id, vault_password_hash="x", is_locked=False)
        db_session.add(vault)
        db_session.commit()
        try:
            with app.test_request_context():
                g.active_tenant_id = sample_tenant.id
                stats = GLService.get_admin_dashboard_stats()
            assert stats["total_accounts"] > 0
            assert stats["posted_entries"] >= len(entries)
            assert stats["total_cash"] != 0
            assert len(stats["recent_entries"]) >= 1
            assert len(stats["high_balance_accounts"]) >= 1
            assert stats["total_cheques"] >= 2
            assert stats["pending_cheques"] >= 1
            assert stats["cleared_cheques"] >= 1
            assert stats["total_vaults"] >= 1
            assert stats["active_vaults"] >= 1
        finally:
            _cleanup_posted_lines(db_session, entries)
            for cheque in cheques:
                db_session.delete(cheque)
            db_session.delete(vault)
            db_session.commit()


class TestStatementLedgerFilters:
    def test_statement_miss_and_variants(self, db_session, sample_tenant, sample_gl_accounts):
        assert GLService.get_account_statement(999999999, tenant_id=sample_tenant.id) is None
        entries = _seed_posted_lines(db_session, sample_tenant, _posted_specs(sample_tenant))
        try:
            acc = _pick_account(sample_tenant, "11", "asset")
            bare = GLService.get_account_statement(acc.id, tenant_id=sample_tenant.id)
            assert isinstance(bare, dict)
            assert bare["closing_balance"] != 0
            full = GLService.get_account_statement(
                acc.id,
                date_from=date(2026, 3, 1),
                date_to=date(2026, 3, 31),
                branch_id=999999999,
                tenant_id=sample_tenant.id,
            )
            assert full["transactions"] == []
            dated = GLService.get_account_statement(
                acc.id,
                date_from=date(2026, 3, 1),
                date_to=date(2026, 3, 31),
                tenant_id=sample_tenant.id,
            )
            assert len(dated["transactions"]) >= 1
            assert dated["opening_balance"] == 0
        finally:
            _cleanup_posted_lines(db_session, entries)

    def test_general_ledger_variants(self, db_session, sample_tenant, sample_gl_accounts):
        assert GLService.get_general_ledger(tenant_id=999999999) == []
        entries = _seed_posted_lines(db_session, sample_tenant, _posted_specs(sample_tenant))
        try:
            bare = GLService.get_general_ledger(tenant_id=sample_tenant.id)
            assert isinstance(bare, list) and bare
            filtered = GLService.get_general_ledger(
                date_from=date(2026, 3, 1),
                date_to=date(2026, 3, 31),
                branch_id=999999999,
                tenant_id=sample_tenant.id,
            )
            assert filtered
            assert all(row["transactions"] == [] for row in filtered)
            assert all(row["total_debit"] == 0 and row["total_credit"] == 0 for row in filtered)
        finally:
            _cleanup_posted_lines(db_session, entries)

    def test_partner_ledger_branch(self, db_session, sample_tenant, sample_gl_accounts):
        from models import Partner

        partner_row = Partner(tenant_id=sample_tenant.id, name="Cov8 Partner", code="COV8P1")
        db_session.add(partner_row)
        db_session.flush()
        entries = _seed_posted_lines(db_session, sample_tenant, _posted_specs(sample_tenant))
        GLJournalLine.query.filter_by(entry_id=entries[0].id).update(
            {GLJournalLine.partner_id: partner_row.id}, synchronize_session=False
        )
        db_session.commit()
        try:
            out = GLService.get_partner_ledger(partner_row.id, branch_id=999999999, tenant_id=sample_tenant.id)
            assert out["transactions"] == []
            assert out["opening_balance"] == 0
        finally:
            _cleanup_posted_lines(db_session, entries)
            db_session.delete(partner_row)
            db_session.commit()

    def test_unscoped_and_none_tenant_arcs(self, db_session, sample_tenant, sample_gl_accounts, mocker, app):
        entries = _seed_posted_lines(db_session, sample_tenant, _posted_specs(sample_tenant))
        try:
            with app.test_request_context():
                g.active_tenant_id = sample_tenant.id
                scoped_tree = GLService.get_accounts_tree(tenant_id=sample_tenant.id)
                assert isinstance(scoped_tree, list) and scoped_tree
                income_none = GLService.build_income_statement(None, None, None, None)
                assert "revenues" in income_none
                sheet_none = GLService.build_balance_sheet(None, 999999999, None)
                assert sheet_none["total_assets"] == 0
            mocker.patch("services.gl_service.gl_helpers.resolve_tenant_id", return_value=None)
            tree_none = GLService.get_accounts_tree()
            assert isinstance(tree_none, list) and tree_none
            tb_none = GLService.get_trial_balance()
            assert tb_none["total_debit"] == tb_none["total_credit"]
            bal_none = GLService.get_all_account_balances()
            assert isinstance(bal_none, dict)
            rev_none = GLService.reverse_entry(reference_type="journal", reference_id=999999999)
            assert rev_none == []
            stmt_none = GLService.get_account_statement(
                entries[0].lines[0].account_id,
                date_from=date(2026, 3, 1),
                date_to=date(2026, 3, 31),
            )
            assert isinstance(stmt_none, dict)
            ledger_none = GLService.get_general_ledger()
            assert isinstance(ledger_none, list)
            partner_none = GLService.get_partner_ledger(999999999)
            assert partner_none["transactions"] == []
            output_acc = GLService._resolve_journal_line_account(
                GLService.posting_line("tax_payable"), sample_tenant.id, ensure_core=False, missing_ok=True
            )
            input_acc = GLService._resolve_journal_line_account(
                GLService.posting_line("vat_input"), sample_tenant.id, ensure_core=False, missing_ok=True
            )
            mocker.patch.object(
                GLService,
                "_resolve_journal_line_account",
                side_effect=[output_acc, input_acc, output_acc, input_acc],
            )
            vat_none = GLService.get_vat_report(date_from=date(2026, 3, 1), date_to=date(2026, 3, 31))
            assert vat_none["vat_output"] >= 0
            mocker.patch.object(GLService, "_resolve_journal_line_account", return_value=output_acc)
            recon_none = GLService._reconciliation_concept_balance("AR", tenant_id=None)
            assert recon_none >= 0
            branch_bal_none = GLService.get_account_balance_for_branch(entries[0].lines[0].account_id)
            assert isinstance(branch_bal_none, float)
            fallback_none = GLService.get_account_code_for_concept("NOPE", fallback_key="sales_revenue")
            assert fallback_none == GL_ACCOUNTS["sales_revenue"]
        finally:
            _cleanup_posted_lines(db_session, entries)

    def test_balance_and_trial_variants(self, db_session, sample_tenant, sample_gl_accounts):
        entries = _seed_posted_lines(db_session, sample_tenant, _posted_specs(sample_tenant))
        try:
            dated = GLService.get_all_account_balances(
                start_date=date(2026, 3, 1),
                end_date=date(2026, 3, 31),
                branch_id=999999999,
                tenant_id=sample_tenant.id,
            )
            assert isinstance(dated, dict)
            tb_branch = GLService.get_trial_balance(branch_id=999999999, tenant_id=sample_tenant.id)
            assert tb_branch["total_debit"] == 0
        finally:
            _cleanup_posted_lines(db_session, entries)


class TestConceptsAndReconciliation:
    def test_concept_fallback_and_raise(self, db_session, sample_tenant):
        from services.gl_account_resolver import GLMappingError

        assert (
            GLService.get_account_code_for_concept("NOPE", tenant_id=sample_tenant.id, fallback_key="sales_revenue")
            == GL_ACCOUNTS["sales_revenue"]
        )
        with pytest.raises(GLMappingError):
            GLService.get_account_code_for_concept("NOPE", tenant_id=sample_tenant.id)

    def test_reconciliation_unknown_concept(self, db_session, sample_tenant):
        assert GLService._reconciliation_concept_balance("NOPE", tenant_id=sample_tenant.id) == Decimal("0")


class TestManualEntryValidation:
    def test_header_raise_and_resolution_arcs(self, db_session, sample_tenant, sample_branch, sample_gl_accounts, app):
        with app.test_request_context():
            g.active_tenant_id = sample_tenant.id
            with pytest.raises(ValueError, match="رئيسي"):
                GLService.create_manual_entry("cov8 hdr", [{"account": "1000", "debit": 1, "credit": 0}])
            with pytest.raises(ValueError, match="رئيسي"):
                GLService.create_manual_entry(
                    "cov8 hdr branch",
                    [{"account": "1000", "debit": 1, "credit": 0}],
                    branch_id=sample_branch.id,
                )

    def test_missing_user_and_inactive_raise(self, db_session, sample_tenant, sample_gl_accounts, app):
        from models import GLAccount

        inactive = GLAccount(
            tenant_id=sample_tenant.id,
            code="COV8IN",
            name="Cov8 Inactive",
            type="expense",
            is_active=False,
            is_header=False,
        )
        db_session.add(inactive)
        db_session.commit()
        try:
            with app.test_request_context():
                g.active_tenant_id = sample_tenant.id
                with pytest.raises(ValueError, match="غير نشط"):
                    GLService.create_manual_entry(
                        "cov8 inactive",
                        [{"account": "COV8IN", "debit": 1, "credit": 0}],
                        created_by=999999999,
                    )
        finally:
            db_session.delete(inactive)
            db_session.commit()


class TestLiquidityAndMappings:
    def test_cash_ambiguous_raises(self, db_session, sample_tenant, sample_gl_accounts):
        from models import GLAccount

        cash_accounts = [
            GLAccount(
                tenant_id=sample_tenant.id,
                code=code,
                name=f"Cov8 {code}",
                type="asset",
                liquidity_kind="cash",
                is_active=True,
                is_header=False,
            )
            for code in ("COV8C1", "COV8C2")
        ]
        for account in cash_accounts:
            db_session.add(account)
        db_session.commit()
        try:
            with pytest.raises(ValueError, match="Multiple"):
                GLService.get_default_liquidity_account("cash", tenant_id=sample_tenant.id)
        finally:
            for account in cash_accounts:
                db_session.delete(account)
            db_session.commit()

    def test_bank_none_configured_raises(self, db_session, sample_tenant, sample_gl_accounts):
        with pytest.raises(ValueError, match="No default bank"):
            GLService.get_default_liquidity_account("bank", tenant_id=sample_tenant.id)

    def test_ensure_mappings_disabled(self, db_session, sample_tenant):
        out = GLService.ensure_gl_mappings(sample_tenant.id)
        assert out == {"created_mappings": 0, "skipped_mappings": 0}

    def test_ensure_mappings_enabled_arcs(self, db_session, sample_tenant, sample_gl_accounts, mocker):
        mocker.patch("services.gl_service.is_dynamic_gl_mapping_enabled", return_value=True)
        with pytest.raises(ValueError, match="tenants"):
            GLService.ensure_gl_mappings()
        missing = GLService.ensure_gl_mappings(999999999)
        assert "tenant not found" in missing["errors"]


class TestResolveArcs:
    def test_missing_code_raises(self, db_session, sample_tenant, sample_gl_accounts):
        with pytest.raises(ValueError, match="not found"):
            GLService._resolve_journal_line_account({"account": "COV8-NOPE"}, sample_tenant.id)

    def test_dynamic_mapping_arcs(self, db_session, sample_tenant, sample_gl_accounts, mocker):
        mocker.patch("services.gl_service.is_dynamic_gl_mapping_enabled", return_value=True)
        with pytest.raises(ValueError, match="2121|required|fallback|concept|mapping"):
            GLService._resolve_journal_line_account({"concept_code": "AR"}, sample_tenant.id)
        with pytest.raises(ValueError, match="required"):
            GLService._resolve_journal_line_account({"concept_code": "AR"}, sample_tenant.id, ensure_core=False)
        from models import GLAccount

        cash_acct = GLAccount(
            tenant_id=sample_tenant.id,
            code="COV8CASH",
            name="Cov8 Cash",
            type="asset",
            liquidity_kind="cash",
            is_active=True,
            is_header=False,
        )
        db_session.add(cash_acct)
        db_session.commit()
        try:
            cash = GLService._resolve_journal_line_account(
                {"account": cash_acct.code, "concept_code": "CASH"}, sample_tenant.id
            )
            assert cash.code == cash_acct.code
        finally:
            db_session.delete(cash_acct)
            db_session.commit()

    def test_dynamic_liquidity_branch_arc(self, db_session, sample_tenant, sample_branch, sample_gl_accounts, mocker):
        from models import GLAccount
        from services.gl_account_resolver import GLMappingError

        mocker.patch("services.gl_service.is_dynamic_gl_mapping_enabled", return_value=True)
        branch_acct = GLAccount(
            tenant_id=sample_tenant.id,
            branch_id=sample_branch.id,
            code="COV8B1",
            name="Cov8 Branch Cash",
            type="asset",
            is_active=True,
            is_header=False,
        )
        db_session.add(branch_acct)
        db_session.commit()
        try:
            with pytest.raises(GLMappingError, match="liquidity_kind"):
                GLService._resolve_journal_line_account(
                    {"account": "COV8B1", "concept_code": "CASH"},
                    sample_tenant.id,
                    branch_id=sample_branch.id,
                )
        finally:
            db_session.delete(branch_acct)
            db_session.commit()

    def test_customer_credit_dynamic_raise(self, db_session, sample_tenant, mocker):
        from services.gl_account_resolver import GLMappingError

        mocker.patch("services.gl_service.is_dynamic_gl_mapping_enabled", return_value=True)
        with pytest.raises(GLMappingError):
            GLService.get_customer_credit_account(SimpleNamespace(customer_type="merchant"), tenant_id=sample_tenant.id)
        mocker.patch.object(GLService, "get_customer_credit_concept", return_value="")
        with pytest.raises(GLMappingError):
            GLService.get_customer_credit_account(SimpleNamespace(customer_type="merchant"), tenant_id=sample_tenant.id)

    def test_dynamic_record_branch_arc(self, db_session, sample_tenant, sample_branch, sample_gl_accounts, mocker):
        from models import GLAccount

        mocker.patch("services.gl_service.is_dynamic_gl_mapping_enabled", return_value=True)
        branch_acct = GLAccount(
            tenant_id=sample_tenant.id,
            branch_id=sample_branch.id,
            code="COV8R1",
            name="Cov8 Branch Asset",
            type="asset",
            is_active=True,
            is_header=False,
        )
        db_session.add(branch_acct)
        db_session.commit()
        try:
            resolved = GLService._resolve_journal_line_account(
                {
                    "account": "COV8R1",
                    "concept_code": "FIXED_ASSET_ASSET",
                    "explicit_account_allowed": True,
                },
                sample_tenant.id,
                branch_id=sample_branch.id,
            )
            assert resolved.code == "COV8R1"
        finally:
            db_session.delete(branch_acct)
            db_session.commit()


class TestEntryHelpers:
    def test_scoped_account_and_entry(self, db_session, sample_tenant, sample_gl_accounts):
        acc = _pick_account(sample_tenant, "11", "asset")
        assert GLService.get_scoped_account_or_404(acc.id).id == acc.id
        entries = _seed_posted_lines(db_session, sample_tenant, _posted_specs(sample_tenant))
        try:
            assert GLService.get_entry_or_404(entries[0].id).id == entries[0].id
            from werkzeug.exceptions import NotFound

            with pytest.raises(NotFound):
                GLService.get_entry_or_404(999999999)
        finally:
            _cleanup_posted_lines(db_session, entries)

    def test_vaults_and_pagination(self, db_session, sample_tenant, sample_gl_accounts):
        assert isinstance(GLService.list_payment_vaults(), list)
        page = GLService.paginate_all_entries(1, 5)
        assert hasattr(page, "items")
