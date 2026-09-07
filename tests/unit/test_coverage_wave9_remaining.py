"""Wave 9 — precise line closure for all remaining action packs (separate file)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from sqlalchemy.exc import OperationalError


class TestParsersWave9:
    def test_cheque_parsers(self):
        from ai_knowledge.actions.cheques import _parse_cheque_command, _parse_list_cheques

        r = _parse_cheque_command("CH001, 1000, incoming, ENBD, 2026-12-31")
        assert r[0] == "create_cheque"
        assert r[1]["amount"] == 1000.0
        assert r[1]["cheque_type"] == "incoming"
        r = _parse_cheque_command("CH001")
        assert r[1]["amount"] == 0
        r = _parse_cheque_command("CH001, 100, outgoing, BANK")
        assert r[1]["cheque_type"] == "outgoing"
        assert _parse_list_cheques(MagicMock())[0] == "list_cheques"

    def test_purchase_return_parsers(self):
        from ai_knowledge.actions.purchase_returns import (
            _parse_list_purchase_returns,
            _parse_purchase_return,
            _parse_return_details,
        )

        r = _parse_purchase_return("P001, Voc, 5, damaged")
        assert r[0] == "create_purchase_return"
        assert r[1]["reason"] == "damaged"
        r = _parse_purchase_return("7, Produkt, 2")
        assert r[1]["purchase_id"] == 7
        r = _parse_purchase_return("X")
        assert r[1]["quantity"] == 1
        assert _parse_return_details("12")[1]["return_id"] == 12
        assert _parse_return_details("R1")[1]["return_number"] == "R1"
        assert _parse_list_purchase_returns(MagicMock())[0] == "purchase_return_details"

    def test_return_parsers(self):
        from ai_knowledge.actions.returns import _parse_list_returns, _parse_return_command

        damaged = _parse_return_command("123, Produkt, 2, damaged")
        assert damaged[1]["sale_id"] == 123
        assert damaged[1]["condition"] == "damaged"
        numeric = _parse_return_command("S100, P, 3")
        assert numeric[1]["sale_number"] == "S100"
        default_qty = _parse_return_command("S100, P")
        assert default_qty[1]["quantity"] == 1
        assert _parse_list_returns(MagicMock())[0] == "list_returns"

    def test_quotation_parsers(self):
        from ai_knowledge.actions.quotations import _parse_list_quotations, _parse_quotation_advance

        r = _parse_quotation_advance(MagicMock(group=lambda i: "accept" if i == 1 else "Q1"))
        assert r is not None
        assert _parse_list_quotations(MagicMock())[0] == "list_quotations"


class TestCatalogClosure:
    def test_customer_guard_and_missing(self, mocker):
        from ai_knowledge.actions.catalog import _update_customer

        mocker.patch("ai_knowledge.actions.catalog.tenant_guard", return_value=(None, SimpleNamespace(success=False)))
        assert not _update_customer({"name": "C"}).success
        mocker.patch("ai_knowledge.actions.catalog.tenant_guard", return_value=(1, None))
        mocker.patch("ai_knowledge.actions.catalog.resolve_customer", return_value=None)
        assert not _update_customer({"name": "Nope"}).success
        mocker.patch("ai_knowledge.actions.catalog.resolve_customer", side_effect=RuntimeError("boom"))
        assert not _update_customer({"name": "C"}).success

    def test_update_product_new_name_and_except(self, mocker):
        from ai_knowledge.actions.catalog import _update_product

        mocker.patch("ai_knowledge.actions.catalog.tenant_guard", return_value=(1, None))
        prod = MagicMock(id=1, name="Old")
        mock_q = mocker.patch("models.Product.query")
        mock_q.filter_by.return_value.first.return_value = prod
        mocker.patch("ai_knowledge.actions.catalog.resolve_product", return_value=prod)
        with patch("ai_knowledge.actions.catalog.atomic_transaction"), patch("ai_knowledge.actions.catalog.audit"):
            r = _update_product({"sku": "S", "new_name": "New"})
            assert r.success
        mocker.patch("ai_knowledge.actions.catalog.tenant_guard", side_effect=RuntimeError("boom"))
        assert not _update_product({"sku": "S"}).success

    def test_adjust_stock_closure(self, mocker):
        from ai_knowledge.actions.catalog import _adjust_stock

        mocker.patch("ai_knowledge.actions.catalog.tenant_guard", return_value=(None, SimpleNamespace(success=False)))
        assert not _adjust_stock({"product_name": "P", "reason": "r"}).success
        mocker.patch("ai_knowledge.actions.catalog.tenant_guard", return_value=(1, None))
        mocker.patch("ai_knowledge.actions.catalog.resolve_product", return_value=None)
        assert not _adjust_stock({"product_name": "Nope", "reason": "r"}).success
        prod = MagicMock(id=1, name="P")
        mocker.patch("ai_knowledge.actions.catalog.resolve_product", return_value=prod)
        mocker.patch("ai_knowledge.actions.catalog.resolve_warehouse", return_value=None)
        assert not _adjust_stock({"product_name": "P", "reason": "r", "warehouse_id": 99}).success
        mocker.patch("services.stock_service.StockService.adjust_stock", side_effect=RuntimeError("boom"))
        with patch("ai_knowledge.actions.catalog.atomic_transaction"), patch("ai_knowledge.actions.catalog.audit"):
            assert not _adjust_stock({"product_name": "P", "reason": "r", "quantity_delta": 2}).success

    def test_register(self):
        from ai_knowledge.actions.catalog import register

        reg = MagicMock()
        register(reg)
        assert reg.call_count == 3


class TestChequesClosure:
    def test_create_edge_and_except(self, mocker):
        import ai_knowledge.actions.cheques as ch

        mocker.patch("ai_knowledge.actions.cheques.tenant_guard", return_value=(None, SimpleNamespace(success=False)))
        assert not ch._create_cheque({"cheque_number": "CH", "amount": "10"}).success
        mocker.patch("ai_knowledge.actions.cheques.tenant_guard", side_effect=RuntimeError("boom"))
        assert not ch._create_cheque({"cheque_number": "CH", "amount": "10"}).success

    def test_list_filters_partial_and_except(self, mocker):
        import ai_knowledge.actions.cheques as ch

        mocker.patch("ai_knowledge.actions.cheques.tenant_guard", return_value=(1, None))
        mock_r = MagicMock(id=1, cheque_number="CH1", cheque_type="incoming", amount=10, bank_name="B", status="pending", due_date=None)
        base_query = MagicMock()
        base_query.filter.return_value = base_query
        base_query.order_by.return_value = base_query
        base_query.limit.return_value = base_query
        base_query.all.return_value = [mock_r]
        mocker.patch("services.cheque_service.ChequeService.scoped_cheques_query", return_value=base_query)
        r = ch._list_cheques({"search": "CH"})
        assert r.success
        r = ch._list_cheques({"status": "pending"})
        assert r.success
        r = ch._list_cheques({"cheque_type": "incoming"})
        assert r.success
        mocker.patch("services.cheque_service.ChequeService.scoped_cheques_query", side_effect=RuntimeError("boom"))
        assert not ch._list_cheques({}).success

    def test_register(self):
        from ai_knowledge.actions.cheques import register

        reg = MagicMock()
        register(reg)
        assert reg.call_count == 2


class TestChequeLifecycleClosure:
    def test_parse_variants(self):
        import ai_knowledge.actions.cheque_lifecycle as cl

        assert cl._parse_deposit("CH001")[1]["cheque_number"] == "CH001"
        assert "deposit_date" not in cl._parse_deposit("CH001")[1]
        assert "clearance_exchange_rate" not in cl._parse_clear("CH001,2026-01-01")[1]
        assert "bounce_fee" not in cl._parse_bounce("CH001,NSF")[1]
        assert "clearance_date" not in cl._parse_clear("CH001")[1]

    def test_deposit_invalid_date(self, mocker):
        import ai_knowledge.actions.cheque_lifecycle as cl

        mocker.patch("ai_knowledge.actions.cheque_lifecycle.tenant_guard", return_value=(1, None))
        mocker.patch(
            "ai_knowledge.actions.cheque_lifecycle._resolve_cheque",
            return_value=MagicMock(id=1, cheque_number="CH1"),
        )
        assert not cl._deposit_cheque({"cheque_number": "CH1", "deposit_date": "bad"}).success
        assert not cl._clear_cheque({"cheque_number": "CH1", "clearance_date": "bad"}).success

    def test_value_error_and_not_found(self, mocker):
        import ai_knowledge.actions.cheque_lifecycle as cl

        mocker.patch("ai_knowledge.actions.cheque_lifecycle.tenant_guard", return_value=(1, None))
        mocker.patch(
            "ai_knowledge.actions.cheque_lifecycle._resolve_cheque",
            return_value=MagicMock(id=1, cheque_number="CH1"),
        )
        mocker.patch("services.cheque_service.process_cheque_deposit", side_effect=ValueError("state"))
        with patch("ai_knowledge.actions.cheque_lifecycle.atomic_transaction"):
            assert not cl._deposit_cheque({"cheque_number": "CH1"}).success
        mocker.patch("services.cheque_service.process_cheque_clear", side_effect=ValueError("state"))
        with patch("ai_knowledge.actions.cheque_lifecycle.atomic_transaction"):
            assert not cl._clear_cheque({"cheque_number": "CH1"}).success
        mocker.patch("ai_knowledge.actions.cheque_lifecycle._resolve_cheque", return_value=None)
        assert not cl._bounce_cheque({"cheque_number": "NOPE", "reason": "NSF"}).success
        mocker.patch(
            "ai_knowledge.actions.cheque_lifecycle._resolve_cheque",
            return_value=MagicMock(id=1, cheque_number="CH1"),
        )
        mocker.patch("services.cheque_service.process_cheque_bounce", side_effect=ValueError("state"))
        with patch("ai_knowledge.actions.cheque_lifecycle.atomic_transaction"):
            assert not cl._bounce_cheque({"cheque_number": "CH1", "reason": "NSF"}).success

    def test_guard_and_generic_excepts(self, mocker):
        import ai_knowledge.actions.cheque_lifecycle as cl

        mocker.patch("ai_knowledge.actions.cheque_lifecycle.tenant_guard", return_value=(None, SimpleNamespace(success=False)))
        assert not cl._bounce_cheque({"cheque_number": "CH1", "reason": "NSF"}).success
        mocker.patch("ai_knowledge.actions.cheque_lifecycle.tenant_guard", side_effect=RuntimeError("boom"))
        with patch("ai_knowledge.actions.cheque_lifecycle.atomic_transaction"):
            assert not cl._deposit_cheque({"cheque_number": "CH1"}).success
            assert not cl._clear_cheque({"cheque_number": "CH1"}).success
            assert not cl._bounce_cheque({"cheque_number": "CH1", "reason": "NSF"}).success

    def test_register(self):
        from ai_knowledge.actions.cheque_lifecycle import register

        reg = MagicMock()
        register(reg)
        assert reg.call_count == 3


class TestPayrollClosure:
    def test_parse_month_year_multi(self):
        from ai_knowledge.actions.payroll_processing import _parse_month_year

        args = _parse_month_year("1, 2024, 5")
        assert args.get("month") == 1
        assert args.get("year") == 2024

    def test_calculate_branches(self, mocker):
        from ai_knowledge.actions.payroll_processing import _calculate_monthly_payroll

        mocker.patch("ai_knowledge.actions.payroll_processing.tenant_guard", return_value=(1, None))
        mocker.patch("ai_knowledge.actions.payroll_processing._resolve_branch", return_value=None)
        emp = SimpleNamespace(id=1, name="Ali", basic_salary=1000, employment_type="salary", iban="x", bank_code="y")
        mocker.patch("services.payroll_service.PayrollService.list_active_employees", return_value=[emp])
        mocker.patch("ai_knowledge.actions.payroll_processing._already_posted", return_value=True)
        mocker.patch(
            "ai_knowledge.actions.payroll_processing._preview_employee",
            return_value={"name": "Ali", "net": 900, "wps_eligible": True},
        )
        r = _calculate_monthly_payroll({"month": 1, "year": 2024, "employee_name": "ALi"})
        assert r.success
        r = _calculate_monthly_payroll({"month": 1, "year": 2024})
        assert r.data["rows"][0]["status"] == "posted"
        mocker.patch("ai_knowledge.actions.payroll_processing._already_posted", return_value=False)
        mocker.patch(
            "ai_knowledge.actions.payroll_processing._preview_employee",
            return_value={"name": "Ali", "status": "skipped", "skipped": True, "reason": "needs days"},
        )
        r = _calculate_monthly_payroll({"month": 1, "year": 2024})
        assert r.data["rows"][0]["status"] == "needs_days"
        mocker.patch(
            "ai_knowledge.actions.payroll_processing._preview_employee",
            return_value={"name": "Ali", "net": 900, "wps_eligible": True},
        )
        r = _calculate_monthly_payroll({"month": 1, "year": 2024})
        assert r.success
        mocker.patch("services.payroll_service.PayrollService.list_active_employees", side_effect=RuntimeError("boom"))
        assert not _calculate_monthly_payroll({"month": 1, "year": 2024}).success

    def test_approve_branches(self, mocker):
        from ai_knowledge.actions.payroll_processing import _approve_and_post_payroll

        mocker.patch("ai_knowledge.actions.payroll_processing.tenant_guard", return_value=(1, None))
        user = MagicMock(id=7)
        mocker.patch("ai_knowledge.actions.payroll_processing.actor", return_value=user)
        mocker.patch("ai_knowledge.actions.payroll_processing._resolve_branch", return_value=None)
        assert not _approve_and_post_payroll({}).success
        assert not _approve_and_post_payroll({"month": 1, "year": 2024, "branch_id": 99}).success
        mocker.patch("services.payroll_service.PayrollService.list_active_employees", return_value=[])
        assert not _approve_and_post_payroll({"month": 1, "year": 2024}).success
        hourly = SimpleNamespace(id=2, name="Karim", employment_type="hourly")
        mocker.patch("services.payroll_service.PayrollService.list_active_employees", return_value=[hourly])
        mocker.patch("ai_knowledge.actions.payroll_processing._already_posted", return_value=False)
        mocker.patch("ai_knowledge.actions.payroll_processing._match_adjustment", return_value={})
        with patch("ai_knowledge.actions.payroll_processing.atomic_transaction"):
            r = _approve_and_post_payroll({"month": 1, "year": 2024})
            assert r.data["failed"][0]["error"]
        txn = MagicMock(net_salary=700)
        mocker.patch("ai_knowledge.actions.payroll_processing._match_adjustment", return_value={"days_worked": 20})
        mocker.patch("services.payroll_service.PayrollService.process_payroll", return_value=txn)
        mocker.patch("services.payroll_service.PayrollService.get_wps_rows", return_value=[])
        with patch("ai_knowledge.actions.payroll_processing.atomic_transaction"), patch(
            "ai_knowledge.actions.payroll_processing.audit"
        ):
            r = _approve_and_post_payroll({"month": 1, "year": 2024})
            assert r.success
            assert len(r.data["posted"]) == 1
        salary = SimpleNamespace(id=1, name="Ali", employment_type="salary")
        mocker.patch("services.payroll_service.PayrollService.list_active_employees", return_value=[salary])
        mocker.patch("ai_knowledge.actions.payroll_processing._already_posted", return_value=False)
        mocker.patch(
            "services.payroll_service.PayrollService.process_payroll",
            side_effect=ValueError("dup"),
        )
        mocker.patch("services.payroll_service.PayrollService.get_wps_rows", return_value=[])
        with patch("ai_knowledge.actions.payroll_processing.atomic_transaction"), patch(
            "ai_knowledge.actions.payroll_processing.audit"
        ):
            r = _approve_and_post_payroll({"month": 1, "year": 2024})
            assert r.success
            assert len(r.data["failed"]) == 1
        mocker.patch("services.payroll_service.PayrollService.list_active_employees", side_effect=RuntimeError("boom"))
        assert not _approve_and_post_payroll({"month": 1, "year": 2024}).success

    def test_register(self):
        from ai_knowledge.actions.payroll_processing import register

        reg = MagicMock()
        register(reg)
        assert reg.call_count == 2


class TestPurchaseReturnsClosure:
    def test_unit_cost_fallback_and_excepts(self, mocker):
        from ai_knowledge.actions.purchase_returns import _create_purchase_return, _purchase_return_details

        mocker.patch("ai_knowledge.actions.purchase_returns.tenant_guard", return_value=(1, None))
        user = MagicMock(id=7)
        mocker.patch("ai_knowledge.actions.purchase_returns.actor", return_value=user)
        mocker.patch("ai_knowledge.actions.purchase_returns.escape_like", return_value="p")
        purchase = MagicMock(purchase_number="P001", status="draft")
        line = MagicMock(id=1, product_id=2, unit_cost=None)
        line.product = SimpleNamespace(name="Prod")
        purchase.lines = [line]
        mocker.patch("ai_knowledge.actions.purchase_returns._resolve_purchase", return_value=purchase)
        pr = MagicMock(id=1, return_number="PR001", total_amount=60)
        mocker.patch("services.purchase_service.PurchaseService.create_purchase_return", return_value=pr)
        with patch("ai_knowledge.actions.purchase_returns.atomic_transaction"), patch(
            "ai_knowledge.actions.purchase_returns.audit"
        ):
            r = _create_purchase_return({"product_name": "Prod", "purchase_number": "P001", "quantity": 2})
            assert r.success
            r = _create_purchase_return(
                {"product_name": "Prod", "purchase_number": "P001", "quantity": 2, "unit_cost": 7}
            )
            assert r.success
        mocker.patch(
            "services.purchase_service.PurchaseService.create_purchase_return",
            side_effect=ValueError("qty"),
        )
        assert not _create_purchase_return({"product_name": "Prod", "purchase_number": "P001", "quantity": 2}).success
        mocker.patch(
            "services.purchase_service.PurchaseService.create_purchase_return",
            side_effect=RuntimeError("boom"),
        )
        assert not _create_purchase_return({"product_name": "Prod", "purchase_number": "P001", "quantity": 2}).success
        mocker.patch("ai_knowledge.actions.purchase_returns.tenant_guard", side_effect=RuntimeError("boom"))
        assert not _purchase_return_details({}).success

    def test_register(self):
        from ai_knowledge.actions.purchase_returns import register

        reg = MagicMock()
        register(reg)
        assert reg.call_count == 2


class TestReturnsClosure:
    def test_guard_and_excepts(self, mocker):
        from ai_knowledge.actions.returns import _create_sale_return, _list_returns

        mocker.patch("ai_knowledge.actions.returns.tenant_guard", return_value=(None, SimpleNamespace(success=False)))
        assert not _create_sale_return({"product_name": "P"}).success
        mocker.patch("ai_knowledge.actions.returns.tenant_guard", return_value=(1, None))
        sale = MagicMock(sale_number="S1", status="completed")
        sale_line = MagicMock(id=5)
        sale_line.product = SimpleNamespace(name="Prod")
        sale.lines = [sale_line]
        mocker.patch("ai_knowledge.actions.returns._resolve_sale", return_value=sale)
        mocker.patch("ai_knowledge.actions.returns.escape_like", return_value="prod")
        mocker.patch("services.return_service.ReturnService.create_return", side_effect=ValueError("qty"))
        assert not _create_sale_return({"product_name": "P", "sale_number": "S1", "quantity": 1}).success
        mocker.patch("services.return_service.ReturnService.create_return", side_effect=RuntimeError("boom"))
        assert not _create_sale_return({"product_name": "P", "sale_number": "S1", "quantity": 1}).success
        mocker.patch("ai_knowledge.actions.returns.tenant_guard", return_value=(1, None))
        mock_q = mocker.patch("models.ProductReturn.query")
        mock_q.filter_by.return_value.order_by.return_value.limit.return_value.all.return_value = []
        r = _list_returns({})
        assert r.success
        mock_q.filter_by.return_value.order_by.return_value.limit.return_value.all.side_effect = RuntimeError("boom")
        assert not _list_returns({}).success

    def test_register(self):
        from ai_knowledge.actions.returns import register

        reg = MagicMock()
        register(reg)
        assert reg.call_count == 2


class TestSchemasClosure:
    def test_validator_branches(self):
        from pydantic import ValidationError

        from ai_knowledge.actions import schemas

        with _raises(ValidationError):
            schemas.UpdateCustomerArgs(name="x", phone="abc")
        with _raises(ValidationError):
            schemas.UpdateCustomerArgs(name="x", email="badd")
        with _raises(ValidationError):
            schemas.CreatePurchaseReturnArgs(product_name="p", quantity=1)
        ok = schemas.UpdateCustomerArgs(name="x", phone="+971501111111", email="ok@example.com")
        assert ok.phone == "+971501111111"


class _raises:
    def __init__(self, exc):
        self.exc = exc

    def __enter__(self):
        return self

    def __exit__(self, typ, val, tb):
        if typ is None or not issubclass(typ, self.exc):
            raise AssertionError(f"expected {self.exc.__name__} to be raised")
        return True


class TestRestoreDrillClosure:
    def test_resolve_more_branches(self, mocker, monkeypatch):
        from services.restore_drill import RestoreDrillService as S

        monkeypatch.setenv("RESTORE_DRILL_DB", "drill")
        monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@h/drill")
        assert S.resolve_scratch_database_url()[1]
        monkeypatch.setenv("RESTORE_DRILL_DB", "scratch")
        monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@localhost:5432/azad_uae")
        url, err = S.resolve_scratch_database_url()
        assert err == "" and "127.0.0.1" in url
        monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@db.example.com:5432/official")
        url, err = S.resolve_scratch_database_url()
        assert err == "" and "db.example.com" in url and url.endswith("/scratch")
        mocker.patch("sqlalchemy.engine.url.make_url", side_effect=Exception("bad url"))
        monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@h/db")
        assert S.resolve_scratch_database_url()[1]

    def test_offsite_exception_fallback(self, mocker, tmp_path):
        from services.restore_drill import RestoreDrillService as S

        p = tmp_path / "f.bak"
        p.write_text("x")
        mocker.patch(
            "utils.offsite_backup.download_latest_offsite_artifact",
            side_effect=RuntimeError("net down"),
        )
        mocker.patch("services.backup_service.BackupService.list_backups", return_value=[{"filename": "f.bak", "path": str(p)}])
        art, err = S.acquire_artifact(source="auto")
        assert art and art["origin"] == "local"

    def test_restore_invalid_verify(self, mocker, tmp_path):
        from services.restore_drill import RestoreDrillService as S

        p = tmp_path / "a.bak"
        p.write_text("d")
        verify = {"valid": False, "manifest": {}, "errors": ["corrupt"]}
        mocker.patch("services.backup_service.BackupService.verify_backup", return_value=verify)
        mocker.patch(
            "services.backup_service.BackupService.restore_backup_to_target_db",
            return_value={"ok": False, "errors": ["failed"]},
        )
        out = S.restore_into_scratch(str(p), "postgresql://x/scratch")
        assert not out.get("ok")

    def test_row_count_sanity_transient(self, mocker):
        from services.restore_drill import RestoreDrillService as S

        op_err = OperationalError("select", {}, OSError("server closed the connection"))
        conn = MagicMock()
        engine = MagicMock()
        engine.connect.return_value.__enter__.side_effect = [op_err, conn]
        mocker.patch("sqlalchemy.create_engine", return_value=engine)
        mocker.patch("services.restore_drill.RestoreDrillService._count_table", return_value=5)
        out = S.row_count_sanity("url")
        assert out["ok"]

    def test_row_count_users_zero(self, mocker):
        from services.restore_drill import RestoreDrillService as S

        engine = MagicMock()
        engine.connect.return_value.__enter__.return_value = MagicMock()
        mocker.patch("sqlalchemy.create_engine", return_value=engine)
        mocker.patch("services.restore_drill.RestoreDrillService._count_table", return_value=0)
        out = S.row_count_sanity("url")
        assert not out["ok"]
        assert any("users" in e for e in out["errors"])

    def test_row_count_non_transient_error(self, mocker):
        from services.restore_drill import RestoreDrillService as S

        op_err = OperationalError("select", {}, OSError("hard failure"))
        engine = MagicMock()
        engine.connect.return_value.__enter__.side_effect = op_err
        mocker.patch("sqlalchemy.create_engine", return_value=engine)
        out = S.row_count_sanity("url")
        assert not out["ok"]
        assert any("row-count" in e for e in out["errors"])

    def test_row_count_transient_twice(self, mocker):
        from services.restore_drill import RestoreDrillService as S

        transient = OperationalError("select", {}, Exception("server closed the connection unexpectedly"))
        engine = MagicMock()
        engine.connect.return_value.__enter__.side_effect = transient
        mocker.patch("sqlalchemy.create_engine", return_value=engine)
        mocker.patch("time.sleep")
        out = S.row_count_sanity("url")
        assert not out["ok"]
        assert any("server closed" in e for e in out["errors"])

    def test_run_drill_error_paths(self, mocker, monkeypatch, tmp_path):
        from services.restore_drill import RestoreDrillService as S

        monkeypatch.setattr("services.restore_drill.DRILL_LOG_PATH", str(tmp_path / "r.log"))
        workdir = tmp_path / "wd"
        workdir.mkdir(exist_ok=True)
        mocker.patch("services.restore_drill.RestoreDrillService.resolve_scratch_database_url", return_value=("url", ""))
        mocker.patch(
            "services.restore_drill.RestoreDrillService.acquire_artifact",
            return_value=({"path": str(tmp_path / "a.bak"), "origin": "local", "workdir": str(workdir)}, ""),
        )
        mocker.patch(
            "services.restore_drill.RestoreDrillService.restore_into_scratch",
            return_value={"ok": False, "errors": ["boom"]},
        )
        r = S.run_drill()
        assert not r["ok"]
        assert any("restore:" in e for e in r["errors"])
        mocker.patch(
            "services.restore_drill.RestoreDrillService.restore_into_scratch",
            return_value={"ok": True, "errors": []},
        )
        mocker.patch(
            "services.restore_drill.RestoreDrillService.row_count_sanity",
            return_value={"counts": {}, "errors": ["sanity: fail"]},
        )
        r = S.run_drill()
        assert not r["ok"]
        assert any("sanity:" in e for e in r["errors"])


class TestQuotationsClosure:
    def test_register(self):
        from ai_knowledge.actions.quotations import register

        reg = MagicMock()
        register(reg)
        assert reg.call_count == 3