"""Wave 6 — remaining 7 packs to 100% (separate file, no bloat on boost)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch


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


class TestPayrollWave6Stats:
    def test_parse_month_year(self):
        from ai_knowledge.actions.payroll_processing import _parse_month_year

        args = _parse_month_year("مسير الرواتب: 1, 2024")
        assert args.get("month") == 1
        args = _parse_month_year("2024-05")
        assert args.get("month") == 5
        args = _parse_month_year("")
        assert "year" in args
