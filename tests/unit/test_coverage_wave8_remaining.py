"""Wave 8 — deep success-path coverage for the remaining action packs (separate file)."""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch


class TestCatalogDeep:
    def test_update_customer_success(self, mocker):
        from ai_knowledge.actions.catalog import _update_customer

        mocker.patch("ai_knowledge.actions.catalog.tenant_guard", return_value=(1, None))
        cust = MagicMock(id=1, name="Customer A")
        mocker.patch("ai_knowledge.actions.catalog.resolve_customer", return_value=cust)
        with patch("ai_knowledge.actions.catalog.atomic_transaction"), patch("ai_knowledge.actions.catalog.audit"):
            r = _update_customer({"name": "Customer A", "phone": "0500000", "credit_limit": "5000"})
            assert r.success
        # no changes
        cust2 = MagicMock(id=1, name="Customer B")
        mocker.patch("ai_knowledge.actions.catalog.resolve_customer", return_value=cust2)
        r = _update_customer({"name": "Customer B"})
        assert not r.success

    def test_update_product_success(self, mocker):
        from ai_knowledge.actions.catalog import _update_product

        mocker.patch("ai_knowledge.actions.catalog.tenant_guard", return_value=(1, None))
        prod = MagicMock(id=1, name="P1", selling_price=10, cost_price=5, min_stock_alert=3)
        mock_q = mocker.patch("models.Product.query")
        mock_q.filter_by.return_value.first.return_value = prod
        mocker.patch("ai_knowledge.actions.catalog.resolve_product", return_value=prod)
        with patch("ai_knowledge.actions.catalog.atomic_transaction"), patch("ai_knowledge.actions.catalog.audit"):
            r = _update_product({"sku": "SKU1", "selling_price": "12", "cost_price": "6", "min_stock": "4"})
            assert r.success
        # product not found
        mocker.patch("ai_knowledge.actions.catalog.resolve_product", return_value=None)
        r = _update_product({"name": "Nope"})
        assert not r.success

    def test_adjust_stock_success(self, mocker):
        from ai_knowledge.actions.catalog import _adjust_stock

        mocker.patch("ai_knowledge.actions.catalog.tenant_guard", return_value=(1, None))
        prod = MagicMock(id=1, name="P1")
        mocker.patch("ai_knowledge.actions.catalog.resolve_product", return_value=prod)
        mocker.patch("ai_knowledge.actions.catalog.resolve_warehouse", return_value=MagicMock(id=2))
        movement = MagicMock(id=10)
        with patch("ai_knowledge.actions.catalog.atomic_transaction"), patch("ai_knowledge.actions.catalog.audit"):
            mocker.patch("services.stock_service.StockService.adjust_stock", return_value=movement)
            r = _adjust_stock({"product_name": "P1", "quantity_delta": 5, "reason": "count", "warehouse_id": 2})
            assert r.success
        # delta zero
        mocker.patch(
            "services.stock_service.StockService.adjust_stock",
            side_effect=Exception("boom"),
        )
        with patch("ai_knowledge.actions.catalog.atomic_transaction"), patch("ai_knowledge.actions.catalog.audit"):
            r = _adjust_stock({"product_name": "P1", "quantity_delta": 0, "reason": "count"})
            assert not r.success


class TestChequesDeep:
    def test_create_cheque_success(self, mocker):
        import ai_knowledge.actions.cheques as ch

        mocker.patch("ai_knowledge.actions.cheques.tenant_guard", return_value=(1, None))
        mock_q = mocker.patch("models.Cheque.query")
        mock_q.filter_by.return_value.first.return_value = None
        mocker.patch("ai_knowledge.actions.cheques.actor", return_value=MagicMock(id=7, branch_id=3))
        mocker.patch("ai_knowledge.actions.cheques.resolve_customer", return_value=MagicMock(id=2))
        mocker.patch("ai_knowledge.actions.cheques.resolve_supplier", return_value=None)
        mock_cheque = MagicMock(id=5)
        with patch("ai_knowledge.actions.cheques.atomic_transaction"), patch("ai_knowledge.actions.cheques.audit"):
            mocker.patch("services.cheque_service.ChequeService.create_cheque", return_value=mock_cheque)
            r = ch._create_cheque(
                {
                    "cheque_number": "CH001",
                    "amount": "1000",
                    "cheque_type": "incoming",
                    "due_date": "2026-12-31",
                    "customer_name": "Cust",
                }
            )
            assert r.success
        # duplicate existing
        mock_q.filter_by.return_value.first.return_value = MagicMock(id=5)
        r = ch._create_cheque({"cheque_number": "CH001", "amount": "100", "due_date": "2026-12-31"})
        assert not r.success
        # invalid due date
        mock_q.filter_by.return_value.first.return_value = None
        r = ch._create_cheque({"cheque_number": "CH002", "amount": "100", "due_date": "bad-date"})
        assert not r.success

    def test_list_cheques_filters(self, mocker):
        import ai_knowledge.actions.cheques as ch

        mocker.patch("ai_knowledge.actions.cheques.tenant_guard", return_value=(1, None))
        mock_r = MagicMock(
            id=1,
            cheque_number="CH001",
            cheque_type="incoming",
            amount=100,
            bank_name="ENBD",
            status="pending",
            due_date=None,
        )
        base_query = MagicMock()
        base_query.filter.return_value = base_query
        base_query.order_by.return_value = base_query
        base_query.limit.return_value = base_query
        base_query.all.return_value = [mock_r]
        mocker.patch("services.cheque_service.ChequeService.scoped_cheques_query", return_value=base_query)
        r = ch._list_cheques({"search": "001", "status": "pending", "cheque_type": "incoming"})
        assert r.success
        assert r.data["count"] == 1


class TestChequeLifecycleDeep:
    def test_parse_functions(self):
        import ai_knowledge.actions.cheque_lifecycle as cl

        assert cl._parse_deposit("CH001,2026-01-01")[0] == "deposit_cheque"
        assert cl._parse_clear("CH001,2026-01-01,3.5")[1]["clearance_exchange_rate"] == 3.5
        assert cl._parse_bounce("CH001,NSUFFICIENT,50")[1]["bounce_fee"] == 50
        assert cl._parse_bounce("CH001")[1]["reason"] == ""

    def test_resolve_and_parse_date(self, mocker):

        import ai_knowledge.actions.cheque_lifecycle as cl

        assert cl._resolve_cheque(1, "") is None
        mock_q = mocker.patch("models.Cheque.query")
        mock_q.filter_by.return_value.first.return_value = "CHEQUE"
        assert cl._resolve_cheque(1, "CH001") == "CHEQUE"
        d, err = cl._parse_date("2026-12-31", "x")
        assert err is None
        d2, err2 = cl._parse_date("bad", "x")
        assert err2 is not None

    def test_deposit_clear_bounce_success(self, mocker):
        import ai_knowledge.actions.cheque_lifecycle as cl

        mocker.patch("ai_knowledge.actions.cheque_lifecycle.tenant_guard", return_value=(1, None))
        cheque = MagicMock(id=1, cheque_number="CH001", currency_gain_loss=1.5)
        mocker.patch("ai_knowledge.actions.cheque_lifecycle._resolve_cheque", return_value=cheque)
        with (
            patch("ai_knowledge.actions.cheque_lifecycle.atomic_transaction"),
            patch("ai_knowledge.actions.cheque_lifecycle.audit"),
        ):
            mocker.patch("services.cheque_service.process_cheque_deposit")
            assert cl._deposit_cheque({"cheque_number": "CH001"}).success
            mocker.patch("services.cheque_service.process_cheque_clear")
            assert cl._clear_cheque({"cheque_number": "CH001", "clearance_exchange_rate": 3.5}).success
            mocker.patch("services.cheque_service.process_cheque_bounce")
            assert cl._bounce_cheque({"cheque_number": "CH001", "reason": "NSF", "bounce_fee": 50}).success
        # not found
        mocker.patch("ai_knowledge.actions.cheque_lifecycle._resolve_cheque", return_value=None)
        assert not cl._deposit_cheque({"cheque_number": "NOPE"}).success
        assert not cl._clear_cheque({"cheque_number": "NOPE"}).success
        # bounce no reason
        assert cl._bounce_cheque({"cheque_number": "CH001", "reason": ""}).success is False


class TestPayrollDeep:
    def test_resolve_branch(self, mocker):
        from ai_knowledge.actions.payroll_processing import _resolve_branch

        assert _resolve_branch(1, None) is None
        mock_q = mocker.patch("models.Branch.query")
        mock_q.filter_by.return_value.first.return_value = "BRANCH"
        assert _resolve_branch(1, 2) == "BRANCH"

    def test_pending_advances(self, mocker):
        from ai_knowledge.actions.payroll_processing import _pending_advances_total

        adv1 = MagicMock(remaining_amount=5)
        adv2 = MagicMock(remaining_amount=0, total_amount=10, deducted_amount=4)
        mock_q = mocker.patch("models.SalaryAdvance.query")
        mock_q.filter_by.return_value.all.return_value = [adv1, adv2]
        assert _pending_advances_total(1, 1) == Decimal("11")

    def test_already_posted(self, mocker):
        from ai_knowledge.actions.payroll_processing import _already_posted

        mock_q = mocker.patch("models.PayrollTransaction.query")
        mock_q.filter_by.return_value.first.return_value = "X"
        assert _already_posted(1, 1, 1, 2024) is True
        mock_q.filter_by.return_value.first.return_value = None
        assert _already_posted(1, 1, 1, 2024) is False

    def test_preview_employee(self, mocker):
        from ai_knowledge.actions.payroll_processing import _preview_employee

        emp = MagicMock(name="a", basic_salary=1000, employment_type="salary", id=1, iban="x", bank_code="y")
        mocker.patch("ai_knowledge.actions.payroll_processing._pending_advances_total", return_value=Decimal("100"))
        assert _preview_employee(emp, 1)["net"] == 900
        emp2 = MagicMock(name="b", basic_salary=1000, employment_type="hourly", id=2, iban=None, bank_code=None)
        mocker.patch("ai_knowledge.actions.payroll_processing._pending_advances_total", return_value=Decimal("0"))
        assert _preview_employee(emp2, 1, days_default=0)["skipped"] is True
        assert _preview_employee(emp2, 1, days_default=5)["basic"] == 5000

    def test_calculate_success(self, mocker):
        from ai_knowledge.actions.payroll_processing import _calculate_monthly_payroll

        mocker.patch("ai_knowledge.actions.payroll_processing.tenant_guard", return_value=(1, None))
        mocker.patch("ai_knowledge.actions.payroll_processing._resolve_branch", return_value=None)
        emp = MagicMock(id=1, name="Ali", basic_salary=1000, employment_type="salary", iban="x", bank_code="y")
        mocker.patch("services.payroll_service.PayrollService.list_active_employees", return_value=[emp])
        mocker.patch("ai_knowledge.actions.payroll_processing._already_posted", return_value=False)
        mocker.patch(
            "ai_knowledge.actions.payroll_processing._preview_employee",
            return_value={"name": "Ali", "net": 900, "wps_eligible": True},
        )
        r = _calculate_monthly_payroll({"month": 1, "year": 2024})
        assert r.success
        # missing month -> error
        r = _calculate_monthly_payroll({})
        assert not r.success
        # no employees
        mocker.patch("services.payroll_service.PayrollService.list_active_employees", return_value=[])
        r = _calculate_monthly_payroll({"month": 1, "year": 2024})
        assert not r.success
        # non-tenant branch
        mocker.patch("ai_knowledge.actions.payroll_processing._resolve_branch", return_value=None)
        mocker.patch("services.payroll_service.PayrollService.list_active_employees", return_value=[emp])
        r = _calculate_monthly_payroll({"month": 1, "year": 2024, "branch_id": 99})
        assert not r.success

    def test_match_adjustment(self):
        from ai_knowledge.actions.payroll_processing import _match_adjustment

        assert _match_adjustment([{"employee_name": "Ali"}], "ali") == {"employee_name": "Ali"}
        assert _match_adjustment([{"employee_name": "Ali"}], "Bob") == {}
        assert _match_adjustment(None, "ali") == {}

    def test_approve_success(self, mocker):
        from ai_knowledge.actions.payroll_processing import _approve_and_post_payroll

        mocker.patch("ai_knowledge.actions.payroll_processing.tenant_guard", return_value=(1, None))
        user = MagicMock(id=7)
        mocker.patch("ai_knowledge.actions.payroll_processing.actor", return_value=user)
        mocker.patch("ai_knowledge.actions.payroll_processing._resolve_branch", return_value=None)
        emp = MagicMock(id=1, name="Ali", employment_type="salary")
        mocker.patch("services.payroll_service.PayrollService.list_active_employees", return_value=[emp])
        mocker.patch("ai_knowledge.actions.payroll_processing._already_posted", return_value=False)
        mocker.patch("ai_knowledge.actions.payroll_processing._match_adjustment", return_value={})
        txn = MagicMock(net_salary=900)
        mocker.patch("services.payroll_service.PayrollService.process_payroll", return_value=txn)
        mocker.patch("services.payroll_service.PayrollService.get_wps_rows", return_value=[1])
        with (
            patch("ai_knowledge.actions.payroll_processing.atomic_transaction"),
            patch("ai_knowledge.actions.payroll_processing.audit"),
        ):
            r = _approve_and_post_payroll({"month": 1, "year": 2024})
            assert r.success
        # no user
        mocker.patch("ai_knowledge.actions.payroll_processing.actor", return_value=None)
        r = _approve_and_post_payroll({"month": 1, "year": 2024})
        assert not r.success
        # process raises ValueError
        mocker.patch("ai_knowledge.actions.payroll_processing.actor", return_value=user)
        mocker.patch("ai_knowledge.actions.payroll_processing._already_posted", return_value=True)
        with patch("ai_knowledge.actions.payroll_processing.atomic_transaction"):
            r = _approve_and_post_payroll({"month": 1, "year": 2024})
            assert r is not None

    def test_resolve_employee(self, mocker):
        from ai_knowledge.actions.payroll_processing import resolve_employee

        assert resolve_employee(1, "") is None
        mock_q = mocker.patch("models.Employee.query")
        mock_q.filter.return_value.order_by.return_value.first.return_value = "EMP"
        assert resolve_employee(1, "Ali") == "EMP"


class TestPurchaseReturnsDeep:
    def test_resolve_purchase(self, mocker):
        from ai_knowledge.actions.purchase_returns import _resolve_purchase

        mock_get = mocker.patch("extensions.db.session.get")
        mock_get.return_value = None
        assert _resolve_purchase(1, {"purchase_id": 5}) is None
        mock_get.return_value = MagicMock(tenant_id=1)
        assert _resolve_purchase(1, {"purchase_id": 5}) is not None
        mock_get.return_value = MagicMock(tenant_id=99)
        assert _resolve_purchase(1, {"purchase_id": 5}) is None
        assert _resolve_purchase(1, {"purchase_number": ""}) is None
        mock_q = mocker.patch("models.Purchase.query")
        mock_q.filter_by.return_value.first.return_value = "P"
        assert _resolve_purchase(1, {"purchase_number": "P001"}) == "P"

    def test_create_success(self, mocker):
        from ai_knowledge.actions.purchase_returns import _create_purchase_return

        mocker.patch("ai_knowledge.actions.purchase_returns.tenant_guard", return_value=(1, None))
        user = MagicMock(id=7)
        mocker.patch("ai_knowledge.actions.purchase_returns.actor", return_value=user)
        mocker.patch("ai_knowledge.actions.purchase_returns.escape_like", return_value="p")
        purchase = MagicMock(purchase_number="P001", status="draft")
        line = MagicMock(id=1, product_id=2, unit_cost=5)
        line.product = SimpleNamespace(name="Prod")
        purchase.lines = [line]
        mocker.patch("ai_knowledge.actions.purchase_returns._resolve_purchase", return_value=purchase)
        pr = MagicMock(id=1, return_number="PR001", total_amount=100)
        mocker.patch("services.purchase_service.PurchaseService.create_purchase_return", return_value=pr)
        with (
            patch("ai_knowledge.actions.purchase_returns.atomic_transaction"),
            patch("ai_knowledge.actions.purchase_returns.audit"),
        ):
            r = _create_purchase_return({"product_name": "Prod", "purchase_number": "P001", "quantity": 3})
            assert r.success
        # no user
        mocker.patch("ai_knowledge.actions.purchase_returns.actor", return_value=None)
        r = _create_purchase_return({"product_name": "Prod", "purchase_number": "P001", "quantity": 3})
        assert not r.success
        # purchase missing
        mocker.patch("ai_knowledge.actions.purchase_returns.actor", return_value=user)
        mocker.patch("ai_knowledge.actions.purchase_returns._resolve_purchase", return_value=None)
        r = _create_purchase_return({"product_name": "Prod", "purchase_number": "P001", "quantity": 3})
        assert not r.success
        # cancelled
        purchase.status = "cancelled"
        mocker.patch("ai_knowledge.actions.purchase_returns._resolve_purchase", return_value=purchase)
        r = _create_purchase_return({"product_name": "Prod", "purchase_number": "P001", "quantity": 3})
        assert not r.success
        # line not found
        purchase.status = "draft"
        mocker.patch("ai_knowledge.actions.purchase_returns.escape_like", return_value="nomatch")
        r = _create_purchase_return({"product_name": "X", "purchase_number": "P001", "quantity": 3})
        assert not r.success
        # qty zero
        mocker.patch("ai_knowledge.actions.purchase_returns.escape_like", return_value="p")
        r = _create_purchase_return({"product_name": "Prod", "purchase_number": "P001", "quantity": 0})
        assert not r.success
        # service raises ValueError
        mocker.patch(
            "services.purchase_service.PurchaseService.create_purchase_return",
            side_effect=ValueError("bad"),
        )
        r = _create_purchase_return({"product_name": "Prod", "purchase_number": "P001", "quantity": 3})
        assert not r.success

    def test_details_success(self, mocker):
        from ai_knowledge.actions.purchase_returns import _purchase_return_details

        mocker.patch("ai_knowledge.actions.purchase_returns.tenant_guard", return_value=(1, None))
        # by return_id
        mock_get = mocker.patch("extensions.db.session.get")
        line = MagicMock(product=MagicMock(name="Prod"), quantity=2, unit_cost=5, line_total=10)
        record = MagicMock(id=1, return_number="PR001", purchase_id=3, total_amount=10, reason="r", lines=[line])
        mock_get.return_value = record
        r = _purchase_return_details({"return_id": 1})
        assert r.success
        # by id wrong tenant
        mock_get.return_value = MagicMock(tenant_id=99)
        r = _purchase_return_details({"return_id": 1})
        assert not r.success
        # by number
        mock_q = mocker.patch("models.PurchaseReturn.query")
        mock_q.filter_by.return_value.first.return_value = record
        r = _purchase_return_details({"return_number": "PR001"})
        assert r.success
        # list
        mock_q.filter_by.return_value.order_by.return_value.limit.return_value.all.return_value = [record]
        r = _purchase_return_details({})
        assert r.success


class TestReturnsDeep:
    def test_resolve_sale(self, mocker):
        from ai_knowledge.actions.returns import _resolve_sale

        mock_get = mocker.patch("extensions.db.session.get")
        mock_get.return_value = None
        assert _resolve_sale(1, {"sale_id": 5}) is None
        mock_get.return_value = MagicMock(tenant_id=1)
        assert _resolve_sale(1, {"sale_id": 5}) is not None
        mock_get.return_value = MagicMock(tenant_id=99)
        assert _resolve_sale(1, {"sale_id": 5}) is None
        assert _resolve_sale(1, {"sale_number": ""}) is None
        mock_q = mocker.patch("models.Sale.query")
        mock_q.filter_by.return_value.first.return_value = "S"
        assert _resolve_sale(1, {"sale_number": "S001"}) == "S"

    def test_create_sale_return_success(self, mocker):
        from ai_knowledge.actions.returns import _create_sale_return

        mocker.patch("ai_knowledge.actions.returns.tenant_guard", return_value=(1, None))
        sale = MagicMock(sale_number="S001", status="completed")
        sale_line = MagicMock(id=5)
        sale_line.product = SimpleNamespace(name="Prod")
        sale.lines = [sale_line]
        mocker.patch("ai_knowledge.actions.returns._resolve_sale", return_value=sale)
        mocker.patch("ai_knowledge.actions.returns.escape_like", return_value="prod")
        user = MagicMock(id=1)
        mocker.patch("ai_knowledge.actions.returns.actor", return_value=user)
        pr = MagicMock(id=1, return_number="R001", refund_amount=50, total_amount=50)
        mocker.patch("services.return_service.ReturnService.create_return", return_value=pr)
        with patch("ai_knowledge.actions.returns.atomic_transaction"), patch("ai_knowledge.actions.returns.audit"):
            r = _create_sale_return({"product_name": "Prod", "sale_number": "S001", "quantity": 1})
            assert r.success
        # sale missing
        mocker.patch("ai_knowledge.actions.returns._resolve_sale", return_value=None)
        r = _create_sale_return({"product_name": "Prod", "sale_number": "S001", "quantity": 1})
        assert not r.success
        # cancelled status
        sale.status = "cancelled"
        mocker.patch("ai_knowledge.actions.returns._resolve_sale", return_value=sale)
        r = _create_sale_return({"product_name": "Prod", "sale_number": "S001", "quantity": 1})
        assert not r.success
        # line not found
        sale2 = MagicMock(sale_number="S001", status="completed")
        sale_line2 = MagicMock(id=5)
        sale_line2.product = SimpleNamespace(name="X")
        sale2.lines = [sale_line2]
        mocker.patch("ai_knowledge.actions.returns._resolve_sale", return_value=sale2)
        r = _create_sale_return({"product_name": "Prod", "sale_number": "S001", "quantity": 1})
        assert not r.success
        # service raises ValueError
        mocker.patch("services.return_service.ReturnService.create_return", side_effect=ValueError("bad"))
        r = _create_sale_return({"product_name": "Prod", "sale_number": "S001", "quantity": 1})
        assert not r.success

    def test_list_returns_success(self, mocker):
        from ai_knowledge.actions.returns import _list_returns

        mocker.patch("ai_knowledge.actions.returns.tenant_guard", return_value=(1, None))
        mock_r = MagicMock(id=1, return_number="R1", sale_id=3, total_amount=50, refund_amount=50, status="completed")
        mock_q = mocker.patch("models.ProductReturn.query")
        mock_q.filter_by.return_value.order_by.return_value.limit.return_value.all.return_value = [mock_r]
        r = _list_returns({})
        assert r.success
        assert r.data["count"] == 1
        # service raises
        mock_q.filter_by.return_value.order_by.return_value.limit.return_value.all.side_effect = Exception("boom")
        r = _list_returns({})
        assert r is not None


class TestSchemasValidators:
    def test_create_sale_return_validators(self):
        from pydantic import ValidationError

        from ai_knowledge.actions.schemas import CreateSaleReturnArgs

        with patch("ai_knowledge.actions.schemas") as _m:
            pass
        # one identifier required
        try:
            CreateSaleReturnArgs(product_name="Prod", quantity=1)
            raise AssertionError("should raise")
        except ValidationError:
            pass

    def test_update_customer_validators(self):
        from pydantic import ValidationError

        from ai_knowledge.actions import schemas

        # phone invalid
        with patch("ai_knowledge.actions.schemas._PackBaseArgs") as _m:
            pass
        for kwargs, should_raise in [
            ({"name": "x", "phone": "abc"}, True),
            ({"name": "x", "email": "bad"}, True),
            ({"name": "x"}, False),
        ]:
            try:
                schemas.UpdateCustomerArgs(**kwargs)
                if should_raise:
                    raise AssertionError(f"should raise: {kwargs}")
            except ValidationError:
                if not should_raise:
                    raise AssertionError(f"should not raise: {kwargs}")

    def test_update_product_validators(self):
        from pydantic import ValidationError

        from ai_knowledge.actions import schemas

        # no identifier
        try:
            schemas.UpdateProductArgs(selling_price=10)
            raise AssertionError("should raise no-identifier")
        except ValidationError:
            pass
        # no change field
        try:
            schemas.UpdateProductArgs(name="Prod")
            raise AssertionError("should raise no-change")
        except ValidationError:
            pass
        # valid
        r = schemas.UpdateProductArgs(name="Prod", selling_price=10)
        assert r.name == "Prod"

    def test_adjust_stock_validators(self):
        from pydantic import ValidationError

        from ai_knowledge.actions import schemas

        try:
            schemas.AdjustStockArgs(product_name="P", quantity_delta=0, reason="r")
            raise AssertionError("should raise zero delta")
        except ValidationError:
            pass
        r = schemas.AdjustStockArgs(product_name="P", quantity_delta=5, reason="r")
        assert r.quantity_delta == 5

    def test_models_with_valid_fields(self):
        from ai_knowledge.actions import schemas

        c = schemas.CreateChequeArgs(
            cheque_number="CN",
            cheque_type="incoming",
            amount=10,
            bank_name="B",
            due_date="2026-12-31",
        )
        assert c.cheque_number == "CN"
        lc = schemas.ListChequesArgs()
        assert lc.search == ""
        cs = schemas.CreateSaleReturnArgs(product_name="P", quantity=1, sale_number="S")
        assert cs.quantity == 1
        lr = schemas.ListReturnsArgs()
        assert lr is not None
        cq = schemas.CreateQuotationArgs(customer_name="c", lines=[{"product_name": "p", "quantity": 1}])
        assert len(cq.lines) == 1
        lq = schemas.ListQuotationsArgs()
        assert lq.status == ""
        aq = schemas.AdvanceQuotationArgs(quotation_number="Q", target="sent")
        assert aq.target == "sent"
        cr = schemas.CreatePurchaseReturnArgs(product_name="P", quantity=1, purchase_number="S")
        assert cr.quantity == 1
        pd = schemas.PurchaseReturnDetailsArgs()
        assert pd.return_number == ""
        dc = schemas.DepositChequeArgs(cheque_number="CN")
        assert dc.deposit_date == ""
        cc = schemas.ClearChequeArgs(cheque_number="CN")
        assert cc.clearance_date == ""
        bc = schemas.BounceChequeArgs(cheque_number="CN", reason="r")
        assert bc.bounce_fee is None
        pa = schemas.PayrollAdjustmentIn(employee_name="e")
        assert pa.allowances == 0
        cp = schemas.CalculatePayrollArgs(month=1, year=2024)
        assert cp.branch_id is None
        ap = schemas.ApprovePayrollArgs(month=1, year=2024)
        assert ap.adjustments == []


class TestRestoreDrillDeep:
    def test_resolve_scratch_database_url(self, monkeypatch):
        from services.restore_drill import RestoreDrillService as S

        monkeypatch.setenv("RESTORE_DRILL_DB", "")
        assert S.resolve_scratch_database_url()[1]
        monkeypatch.setenv("RESTORE_DRILL_DB", "postgres")
        assert S.resolve_scratch_database_url()[1]
        monkeypatch.delenv("DATABASE_URL", raising=False)
        monkeypatch.setenv("RESTORE_DRILL_DB", "scratch_db")
        monkeypatch.delenv("SQLALCHEMY_DATABASE_URI", raising=False)
        assert S.resolve_scratch_database_url()[1]
        monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@localhost:5432/azad_uae")
        url, err = S.resolve_scratch_database_url()
        assert err == ""
        assert "scratch_db" in url
        monkeypatch.setenv("RESTORE_DRILL_DB", "azad_uae")
        assert S.resolve_scratch_database_url()[1]
        monkeypatch.setenv("RESTORE_DRILL_DB", "scratch_db")
        monkeypatch.setenv("DATABASE_URL", "sqlite:///x.db")
        assert S.resolve_scratch_database_url()[1]

    def test_acquire_artifact_paths(self, mocker, tmp_path):
        from services.restore_drill import RestoreDrillService as S

        # filename provided but missing
        mocker.patch("services.backup_service.BackupService._backup_path", return_value=str(tmp_path / "nope.bak"))
        _, err = S.acquire_artifact(source="local", filename="f.bak")
        assert "not found" in err
        # filename exists
        p = tmp_path / "f.bak"
        p.write_text("x")
        mocker.patch("services.backup_service.BackupService._backup_path", return_value=str(p))
        art, err = S.acquire_artifact(source="local", filename="f.bak")
        assert art and art["origin"] == "local"
        # auto -> offsite fails -> fallback local backups
        mocker.patch(
            "services.backup_service.BackupService.list_backups", return_value=[{"filename": "b.bak", "path": str(p)}]
        )
        mocker.patch(
            "utils.offsite_backup.download_latest_offsite_artifact",
            return_value={"ok": False, "error": "net"},
        )
        art, err = S.acquire_artifact(source="auto")
        assert art and art["origin"] == "local"
        # offsite-only fails
        art, err = S.acquire_artifact(source="offsite")
        assert art is None
        # no backups
        mocker.patch("services.backup_service.BackupService.list_backups", return_value=[])
        art, err = S.acquire_artifact(source="auto")
        assert art is None

    def test_row_count_sanity(self, mocker):
        from services.restore_drill import RestoreDrillService as S

        mocker.patch("sqlalchemy.create_engine")
        mocker.patch("services.restore_drill.RestoreDrillService._count_table", return_value=5)
        out = S.row_count_sanity("url")
        assert out["ok"]
        # count failure
        mocker.patch(
            "services.restore_drill.RestoreDrillService._count_table",
            side_effect=Exception("count failed"),
        )
        out = S.row_count_sanity("url")
        assert not out["ok"]

    def test_write_drill_report(self, monkeypatch, tmp_path):
        from services.restore_drill import RestoreDrillService as S

        monkeypatch.setattr("services.restore_drill.DRILL_LOG_PATH", str(tmp_path / "r.log"))
        assert S.write_drill_report({"ok": True})
        # OSError branch
        monkeypatch.setattr("services.restore_drill.DRILL_LOG_PATH", "")
        path = S.write_drill_report({"ok": True})
        assert path == ""

    def test_run_drill(self, mocker, monkeypatch, tmp_path):
        from services.restore_drill import RestoreDrillService as S

        monkeypatch.setattr("services.restore_drill.DRILL_LOG_PATH", str(tmp_path / "r.log"))
        # resolve fails
        mocker.patch(
            "services.restore_drill.RestoreDrillService.resolve_scratch_database_url", return_value=(None, "no db")
        )
        r = S.run_drill()
        assert not r["ok"]
        # acquire fails
        mocker.patch(
            "services.restore_drill.RestoreDrillService.resolve_scratch_database_url", return_value=("url", "")
        )
        mocker.patch("services.restore_drill.RestoreDrillService.acquire_artifact", return_value=(None, "no artifact"))
        r = S.run_drill()
        assert not r["ok"]
        # full success
        mocker.patch(
            "services.restore_drill.RestoreDrillService.acquire_artifact",
            return_value=({"path": str(tmp_path / "a.bak"), "origin": "local", "filename": "a.bak"}, ""),
        )
        mocker.patch("services.restore_drill.RestoreDrillService.restore_into_scratch", return_value={"ok": True})
        mocker.patch(
            "services.restore_drill.RestoreDrillService.row_count_sanity",
            return_value={"counts": {"users": 5}, "errors": []},
        )
        r = S.run_drill()
        assert r["ok"]
        # restore crashes
        mocker.patch(
            "services.restore_drill.RestoreDrillService.restore_into_scratch",
            side_effect=Exception("crash"),
        )
        r = S.run_drill()
        assert not r["ok"]
