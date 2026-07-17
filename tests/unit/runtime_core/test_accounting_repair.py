from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from app.runtime.accounting_repair import repair_accounting_data


class TestRepairAccountingData:
    def _base_patches(self, mocker, tenant_id=1):
        mocker.patch("utils.tenanting.get_active_tenant_id", return_value=tenant_id)
        mocker.patch("services.gl_service.GLService.ensure_core_accounts")
        merchant = MagicMock(id=5)
        Customer = mocker.patch("models.Customer")
        Customer.query.filter_by.return_value.order_by.return_value.first.return_value = merchant
        inv_acct = MagicMock(id=10)
        eq_acct = MagicMock(id=20)
        mocker.patch(
            "services.gl_helpers.get_account",
            side_effect=lambda code, tid: inv_acct if code == "1140" else eq_acct,
        )
        mocker.patch(
            "models.gl.GLJournalLine"
        ).query.filter.return_value.all.return_value = []
        product = MagicMock(
            current_stock=10,
            cost_price=Decimal("5"),
            merchant_customer_id=None,
            tenant_id=tenant_id,
        )
        Product = MagicMock()
        Product.query.filter.return_value.all.return_value = [product]
        import models as models_mod

        models_mod.Product = Product
        tenant_q = MagicMock()
        tenant_q.all.return_value = [product]
        mocker.patch("utils.tenant_orm.tenant_query", return_value=tenant_q)
        mocker.patch(
            "models.gl.GLJournalEntry"
        ).query.filter.return_value.all.return_value = []
        mocker.patch(
            "models.gl.GLJournalEntry"
        ).query.filter_by.return_value.first.return_value = None
        branch = MagicMock(id=3)
        Branch = mocker.patch("models.Branch")
        Branch.query.filter_by.return_value.first.return_value = branch
        mock_db = mocker.patch("app.runtime.accounting_repair.db")
        return mock_db, merchant, product

    def test_creates_merchant_when_missing(self, mocker):
        mocker.patch("utils.tenanting.get_active_tenant_id", return_value=1)
        mocker.patch("services.gl_service.GLService.ensure_core_accounts")
        Customer = mocker.patch("models.Customer")
        Customer.query.filter_by.return_value.order_by.return_value.first.return_value = None
        new_merchant = MagicMock(id=9)
        Customer.return_value = new_merchant
        mocker.patch(
            "services.gl_helpers.get_account", side_effect=lambda c, t: MagicMock(id=1)
        )
        mocker.patch(
            "models.gl.GLJournalLine"
        ).query.filter.return_value.all.return_value = []
        mocker.patch("utils.tenant_orm.tenant_query").all.return_value = []
        mocker.patch(
            "models.gl.GLJournalEntry"
        ).query.filter.return_value.all.return_value = []
        mocker.patch(
            "models.gl.GLJournalEntry"
        ).query.filter_by.return_value.first.return_value = None
        mocker.patch(
            "models.Branch"
        ).query.filter_by.return_value.first.return_value = MagicMock(id=1)
        mock_db = mocker.patch("app.runtime.accounting_repair.db")
        result = repair_accounting_data()
        assert result["merchant_id"] == 9
        mock_db.session.add.assert_called()

    def test_backfills_legacy_cheque_entries(self, app, mocker):
        mock_db, merchant, product = self._base_patches(mocker)
        entry = MagicMock(
            description="استلام شيك وارد رقم CH-001",
            reference_type=None,
            reference_id=None,
        )
        mocker.patch(
            "models.gl.GLJournalEntry"
        ).query.filter.return_value.all.return_value = [entry]
        cheque = MagicMock(id=42)
        mocker.patch(
            "models.Cheque"
        ).query.filter.return_value.first.return_value = cheque
        result = repair_accounting_data()
        assert entry.reference_type == "cheque_receive"
        assert entry.reference_id == 42
        assert result["legacy_cheque_refs"] == 1

    def test_cheque_issue_bounce_cancel_patterns(self, app, mocker):
        self._base_patches(mocker)
        cases = [
            ("إصدار شيك صادر رقم OUT-1", "cheque_issue"),
            ("ارتداد شيك رقم BNK-2", "cheque_bounce"),
            ("إلغاء شيك رقم C-3", "cheque_cancel"),
        ]
        for desc, expected in cases:
            entry = MagicMock(description=desc, reference_type=None, reference_id=None)
            mocker.patch(
                "models.gl.GLJournalEntry"
            ).query.filter.return_value.all.return_value = [entry]
            mocker.patch(
                "models.Cheque"
            ).query.filter.return_value.first.return_value = MagicMock(id=1)
            repair_accounting_data()
            assert entry.reference_type == expected

    def test_skips_entries_without_cheque_match(self, app, mocker):
        self._base_patches(mocker)
        entry = MagicMock(description="استلام شيك وارد رقم X", reference_type=None)
        mocker.patch(
            "models.gl.GLJournalEntry"
        ).query.filter.return_value.all.return_value = [entry]
        mocker.patch(
            "models.Cheque"
        ).query.filter.return_value.first.return_value = None
        result = repair_accounting_data()
        assert result["legacy_cheque_refs"] == 0

    def test_posts_positive_inventory_adjustment(self, app, mocker):
        self._base_patches(mocker)
        tenant_q = MagicMock()
        tenant_q.all.return_value = [
            MagicMock(current_stock=100, cost_price=Decimal("2"))
        ]
        mocker.patch("utils.tenant_orm.tenant_query", return_value=tenant_q)
        post = mocker.patch("services.gl_service.GLService.post_entry")
        result = repair_accounting_data()
        post.assert_called_once()
        assert result["inventory_adjustment"] == Decimal("200")

    def test_posts_negative_inventory_adjustment(self, app, mocker):
        self._base_patches(mocker)
        line = MagicMock(debit=Decimal("500"), credit=Decimal("0"))
        mocker.patch(
            "models.gl.GLJournalLine"
        ).query.filter.return_value.all.return_value = [line]
        tenant_q = MagicMock()
        tenant_q.all.return_value = [
            MagicMock(current_stock=10, cost_price=Decimal("10"))
        ]
        mocker.patch("utils.tenant_orm.tenant_query", return_value=tenant_q)
        post = mocker.patch("services.gl_service.GLService.post_entry")
        repair_accounting_data()
        post.assert_called_once()

    def test_skips_migration_when_existing(self, app, mocker):
        self._base_patches(mocker)
        mocker.patch(
            "models.gl.GLJournalEntry"
        ).query.filter_by.return_value.first.return_value = MagicMock()
        post = mocker.patch("services.gl_service.GLService.post_entry")
        result = repair_accounting_data()
        post.assert_not_called()
        assert result["inventory_adjustment"] == Decimal("0")

    def test_raises_when_no_tenant_for_inventory(self, app, mocker):
        mocker.patch("utils.tenanting.get_active_tenant_id", return_value=None)
        Tenant = mocker.patch("models.Tenant")
        Tenant.query.filter_by.return_value.order_by.return_value.first.return_value = (
            None
        )
        mocker.patch("services.gl_service.GLService.ensure_core_accounts")
        mocker.patch(
            "models.Customer"
        ).query.filter_by.return_value.order_by.return_value.first.return_value = (
            MagicMock(id=1)
        )
        mocker.patch("models.Product").query.filter.return_value.all.return_value = []
        mocker.patch(
            "models.gl.GLJournalEntry"
        ).query.filter.return_value.all.return_value = []
        with pytest.raises(RuntimeError, match="inventory migration"):
            repair_accounting_data()

    def test_raises_when_gl_accounts_missing(self, app, mocker):
        mocker.patch("utils.tenanting.get_active_tenant_id", return_value=1)
        mocker.patch("services.gl_service.GLService.ensure_core_accounts")
        mocker.patch(
            "models.Customer"
        ).query.filter_by.return_value.order_by.return_value.first.return_value = (
            MagicMock(id=1)
        )
        mocker.patch("models.Product").query.filter.return_value.all.return_value = []
        mocker.patch(
            "models.gl.GLJournalEntry"
        ).query.filter.return_value.all.return_value = []
        mocker.patch("services.gl_helpers.get_account", return_value=None)
        with pytest.raises(RuntimeError, match="1140"):
            repair_accounting_data()

    def test_resolves_tenant_from_default(self, mocker):
        mocker.patch("utils.tenanting.get_active_tenant_id", return_value=None)
        tenant = MagicMock(id=7)
        Tenant = mocker.patch("models.Tenant")
        Tenant.query.filter_by.return_value.order_by.return_value.first.return_value = (
            tenant
        )
        ensure = mocker.patch("services.gl_service.GLService.ensure_core_accounts")
        mocker.patch(
            "models.Customer"
        ).query.filter_by.return_value.order_by.return_value.first.return_value = (
            MagicMock(id=1)
        )
        mocker.patch("models.Product").query.filter.return_value.all.return_value = []
        mocker.patch(
            "models.gl.GLJournalEntry"
        ).query.filter.return_value.all.return_value = []
        mocker.patch(
            "services.gl_helpers.get_account", side_effect=lambda c, t: MagicMock(id=1)
        )
        mocker.patch(
            "models.gl.GLJournalLine"
        ).query.filter.return_value.all.return_value = []
        mocker.patch("utils.tenant_orm.tenant_query").all.return_value = []
        mocker.patch(
            "models.gl.GLJournalEntry"
        ).query.filter_by.return_value.first.return_value = None
        mocker.patch(
            "models.Branch"
        ).query.filter_by.return_value.first.return_value = MagicMock(id=1)
        mocker.patch("app.runtime.accounting_repair.db")
        repair_accounting_data()
        ensure.assert_called_with(tenant_id=7)

    def test_skips_entry_without_cheque_number_pattern(self, app, mocker):
        self._base_patches(mocker)
        entry = MagicMock(description="generic journal without id", reference_type=None)
        mocker.patch(
            "models.gl.GLJournalEntry"
        ).query.filter.return_value.all.return_value = [entry]
        result = repair_accounting_data()
        assert result["legacy_cheque_refs"] == 0

    def test_skips_unrecognized_cheque_description(self, app, mocker):
        self._base_patches(mocker)
        entry = MagicMock(
            description="رقم CH-9 without known action", reference_type=None
        )
        mocker.patch(
            "models.gl.GLJournalEntry"
        ).query.filter.return_value.all.return_value = [entry]
        mocker.patch(
            "models.Cheque"
        ).query.filter.return_value.first.return_value = MagicMock(id=1)
        result = repair_accounting_data()
        assert entry.reference_type is None
        assert result["legacy_cheque_refs"] == 0

    def test_commit_rollback_on_failure(self, app, mocker):
        mock_db, merchant, product = self._base_patches(mocker)
        mocker.patch("services.gl_service.GLService.post_entry")
        mocker.patch(
            "app.runtime.accounting_repair.atomic_transaction",
            side_effect=RuntimeError("commit fail"),
        )
        with pytest.raises(RuntimeError):
            repair_accounting_data()
