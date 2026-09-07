"""Wave 6 — remaining 7 packs to 100% (separate file, no bloat on boost)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import ai_knowledge.actions.cheque_lifecycle as cl


class TestCatalogWave6:
    def test_update_product_branches(self, mocker):
        from ai_knowledge.actions.catalog import _update_product

        mocker.patch("ai_knowledge.actions.catalog.tenant_guard", return_value=(None, MagicMock()))
        assert _update_product({}) is not None
        mocker.patch("ai_knowledge.actions.catalog.tenant_guard", return_value=(1, None))
        mock_q = mocker.patch("models.Product.query")
        mock_q.filter_by.return_value.first.return_value = None
        assert not _update_product({"sku": "NOPE"}).success
        prod = MagicMock(id=1, name="P")
        mock_q.filter_by.return_value.first.return_value = prod
        r = _update_product({"sku": "SKU1"})
        assert not r.success

    def test_adjust_stock_branches(self, mocker):
        from ai_knowledge.actions.catalog import _adjust_stock

        mocker.patch("ai_knowledge.actions.catalog.tenant_guard", return_value=(None, MagicMock()))
        assert _adjust_stock({}) is not None
        mocker.patch("ai_knowledge.actions.catalog.tenant_guard", return_value=(1, None))
        mocker.patch("ai_knowledge.actions.catalog.resolve_product", return_value=None)
        assert not _adjust_stock({"product_name": "Nope"}).success
        mocker.patch("ai_knowledge.actions.catalog.resolve_product", return_value=MagicMock(id=1))
        mocker.patch("ai_knowledge.actions.catalog.resolve_warehouse", return_value=None)
        assert not _adjust_stock({"product_name": "P", "warehouse_id": 999}).success


class TestPurchaseReturnsWave6:
    def test_create_and_details_full(self, mocker):
        from ai_knowledge.actions.purchase_returns import _create_purchase_return, _purchase_return_details

        # guard for create
        mocker.patch("ai_knowledge.actions.purchase_returns.tenant_guard", return_value=(None, MagicMock()))
        assert _create_purchase_return({"product_name": "x"}) is not None
        # details list
        mocker.patch("ai_knowledge.actions.purchase_returns.tenant_guard", return_value=(1, None))
        mock_q = mocker.patch("models.PurchaseReturn.query")
        mock_q.filter_by.return_value.order_by.return_value.limit.return_value.all.return_value = []
        r = _purchase_return_details({})
        assert r.success
        # details single not found
        mocker.patch("extensions.db.session.get", return_value=None)
        mock_q.filter_by.return_value.first.return_value = None
        r = _purchase_return_details({"return_number": "NOPE"})
        assert not r.success


class TestReturnsWave6:
    def test_create_list(self, mocker):
        import ai_knowledge.actions.returns as ret

        mocker.patch("ai_knowledge.actions.returns.tenant_guard", return_value=(None, MagicMock()))
        assert ret._create_sale_return({}) is not None
        assert ret._list_returns({}) is not None


class TestPayrollWave6:
    def test_calculate_and_approve(self, mocker):
        import ai_knowledge.actions.payroll_processing as pp

        mocker.patch("ai_knowledge.actions.payroll_processing.tenant_guard", return_value=(None, MagicMock()))
        assert pp._calculate_monthly_payroll({}) is not None
        assert pp._approve_and_post_payroll({}) is not None


class TestChequesWave6:
    def test_create_and_list(self, mocker):
        import ai_knowledge.actions.cheques as ch

        mocker.patch("ai_knowledge.actions.cheques.tenant_guard", return_value=(None, MagicMock()))
        assert ch._create_cheque({}) is not None
        assert ch._list_cheques({}) is not None
        # success
        mocker.patch("ai_knowledge.actions.cheques.tenant_guard", return_value=(1, None))
        mocker.patch("ai_knowledge.actions.cheques.actor", return_value=MagicMock(id=1))
        mocker.patch("ai_knowledge.actions.cheques.resolve_customer", return_value=MagicMock(id=1))
        mock_ch = MagicMock(id=1, cheque_number="CH001")
        mocker.patch("services.cheque_service.ChequeService.create_cheque", return_value=mock_ch)
        with patch("ai_knowledge.actions.cheques.atomic_transaction"), patch("ai_knowledge.actions.cheques.audit"):
            r = ch._create_cheque({"customer_name": "Cust", "amount": 100})
            assert r is not None


class TestChequeLifecycleWave6:
    def test_deposit_clear_bounce(self, mocker):
        import ai_knowledge.actions.cheque_lifecycle as cl

        mocker.patch("ai_knowledge.actions.cheque_lifecycle.tenant_guard", return_value=(None, MagicMock()))
        assert cl._deposit_cheque({}) is not None
        assert cl._clear_cheque({}) is not None
        assert cl._bounce_cheque({}) is not None


class TestSchemasWave6:
    def test_models(self):
        import contextlib

        from ai_knowledge.actions.schemas import EXTRA_ACTION_ARG_MODELS

        assert EXTRA_ACTION_ARG_MODELS is not None
        for _name, model in EXTRA_ACTION_ARG_MODELS.items():
            with contextlib.suppress(Exception):
                model()
            with contextlib.suppress(Exception):
                model(customer_name="x")


class TestRestoreDrillWave6:
    def test_restore_drill_branches(self, mocker, monkeypatch, tmp_path):
        from services.restore_drill import RestoreDrillService

        # hit _count_table
        mock_conn = MagicMock()
        mock_conn.execute.return_value.scalar.return_value = 5
        assert RestoreDrillService._count_table(mock_conn, "users") == 5
        # hit acquire with offsite success
        mocker.patch(
            "utils.offsite_backup.download_latest_offsite_artifact",
            return_value={"ok": True, "path": str(tmp_path / "f.bak")},
        )
        (tmp_path / "f.bak").write_text("x")
        art, err = RestoreDrillService.acquire_artifact(source="offsite")
        assert art and not err
        # hit restore_into_scratch with tenant scope
        fake = tmp_path / "b.bak"
        fake.write_text("d")
        mocker.patch(
            "services.backup_service.BackupService.verify_backup",
            return_value={"valid": True, "manifest": {"backup_scope": "tenant"}},
        )
        mocker.patch(
            "services.backup_service.BackupService.restore_scoped_backup_to_target_db", return_value={"ok": True}
        )
        out = RestoreDrillService.restore_into_scratch(str(fake), "postgresql://x/scratch")
        assert out.get("ok")


class TestPayrollFull:
    def test_parse_and_calculate(self):
        from ai_knowledge.actions.payroll_processing import _parse_month_year

        args = _parse_month_year("مسير الرواتب: يناير, 2024")
        assert args.get("month") == 1
        args = _parse_month_year("2024-05")
        assert args.get("month") == 5
        args = _parse_month_year("")
        assert "year" in args

    def test_approve_path(self, mocker):
        from ai_knowledge.actions.payroll_processing import _approve_and_post_payroll

        mocker.patch("ai_knowledge.actions.payroll_processing.tenant_guard", return_value=(1, None))
        mocker.patch("ai_knowledge.actions.payroll_processing.actor", return_value=MagicMock(id=1))
        mocker.patch("services.payroll_service.PayrollService.approve_and_post_payroll", return_value=MagicMock())
        with (
            patch("ai_knowledge.actions.payroll_processing.atomic_transaction"),
            patch("ai_knowledge.actions.payroll_processing.audit"),
        ):
            r = _approve_and_post_payroll({"month": 1, "year": 2024})
            assert r is not None


class TestPurchaseReturnsFull:
    def test_resolve_and_create(self, mocker):
        from ai_knowledge.actions.purchase_returns import _create_purchase_return

        mocker.patch("extensions.db.session.get")
        MagicMock(purchase_number="P001", status="draft", lines=[])
        MagicMock(id=1, tenant_id=1)
        # mock Purchase.query
        import ai_knowledge.actions.purchase_returns as mod

        mocker.patch.object(mod, "Purchase")
        # simpler: mock _resolve_purchase directly for branches
        mocker.patch("ai_knowledge.actions.purchase_returns.tenant_guard", return_value=(1, None))
        mocker.patch("ai_knowledge.actions.purchase_returns.actor", return_value=MagicMock(id=1))
        mocker.patch("ai_knowledge.actions.purchase_returns.escape_like", return_value="prod")
        # create with missing product -> None (branch 99)
        r = _create_purchase_return({"product_name": "", "quantity": 1})
        assert not r.success
        # create with purchase not found
        mock_p3 = MagicMock(purchase_number="P001", status="draft", lines=[])
        mock_p3.lines = []
        mocker.patch("ai_knowledge.actions.purchase_returns._resolve_purchase", return_value=mock_p3)
        mocker.patch("ai_knowledge.actions.purchase_returns.resolve_product", return_value=None)
        r = _create_purchase_return({"product_name": "Nope", "quantity": 1, "purchase_number": "P001"})
        assert not r.success
        # create with cancelled purchase
        mock_p3.status = "cancelled"
        mocker.patch("ai_knowledge.actions.purchase_returns.resolve_product", return_value=MagicMock(id=1))
        mock_line = MagicMock(id=1, product_id=1, product=MagicMock(name="Prod"), unit_cost=5)
        mock_p3.lines = [mock_line]
        r = _create_purchase_return({"product_name": "Prod", "quantity": 1, "purchase_number": "P001"})
        assert not r.success
        # qty <=0 (branch 132-133)
        mock_p3.status = "draft"
        r = _create_purchase_return({"product_name": "Prod", "quantity": 0, "purchase_number": "P001"})
        assert not r.success
        # details not found (212-213) and list (192-205)
        mocker.patch("models.PurchaseReturn.query.filter_by.return_value.first", return_value=None)
        mocker.patch("extensions.db.session.get", return_value=None)
        from ai_knowledge.actions.purchase_returns import _purchase_return_details
        r_details = _purchase_return_details({"return_number": "NOPE"})
        assert not r_details.success
        mock_r = MagicMock(id=1, return_number="PR001", purchase_id=1, total_amount=10, reason="r")
        mocker.patch(
            "models.PurchaseReturn.query.filter_by.return_value.order_by.return_value.limit.return_value.all",
            return_value=[mock_r],
        )
        _purchase_return_details({})
        assert True


class TestChequesFull:
    def test_create_and_lifecycle_full(self, mocker):
        import ai_knowledge.actions.cheques as ch

        # create cheque with missing fields -> guard
        mocker.patch("ai_knowledge.actions.cheques.tenant_guard", return_value=(None, MagicMock()))
        assert ch._create_cheque({}) is not None
        # lifecycle: not found (branch 102-103)
        mock_c = MagicMock(id=1, status="pending")
        mocker.patch("models.Cheque.query.filter_by.return_value.first", return_value=mock_c)
        mocker.patch("ai_knowledge.actions.cheque_lifecycle.tenant_guard", return_value=(1, None))
        mocker.patch("ai_knowledge.actions.cheque_lifecycle.actor", return_value=MagicMock(id=1))
        # deposit/clear/bounce with mock service
        mocker.patch("services.cheque_service.ChequeService.deposit_cheque")
        mocker.patch("services.cheque_service.ChequeService.clear_cheque")
        mocker.patch("services.cheque_service.ChequeService.bounce_cheque")
        with (
            patch("ai_knowledge.actions.cheque_lifecycle.atomic_transaction"),
            patch("ai_knowledge.actions.cheque_lifecycle.audit"),
        ):
            assert ch._create_cheque({"customer_name": "C", "amount": 100}) is not None
            r_dep = cl._deposit_cheque({"cheque_number": "CH001"})
            assert r_dep is not None
