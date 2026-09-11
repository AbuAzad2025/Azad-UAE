"""Coverage boost for services/payment_service.py.

DB-free tests: real PaymentService methods run with DB/GL/rate/user
boundaries mocked. Targets branch-resolution tails, supplier-FX guards,
create_payment purchase/flush branches, supplier-refund flow, customer
payment/refund flows, receipt FX auto-posting + allocation loop, scoped
balances, allocate-to-oldest, and delete helpers.
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, patch

MOD = "services.payment_service"


def _chain(*, scalar=None, all_result=None, first_result=None):
    q = MagicMock()
    q.filter.return_value = q
    q.filter_by.return_value = q
    q.order_by.return_value = q
    q.scalar.return_value = scalar
    q.all.return_value = all_result if all_result is not None else []
    q.first.return_value = first_result
    return q


def _user_mock(**kw):
    base = {"is_authenticated": False, "id": 1, "tenant_id": 9, "branch_id": None}
    base.update(kw)
    return MagicMock(**base)


class TestResolveBranchId:
    def test_falls_back_to_current_user_branch(self):
        from services.payment_service import PaymentService

        user = MagicMock(branch_id=None)
        with (
            patch(f"{MOD}.branch_scope_id_for", return_value=None),
            patch(f"{MOD}.current_user", new=_user_mock(is_authenticated=True, branch_id=8)),
        ):
            assert PaymentService._resolve_branch_id(user=user) == 8

    def test_returns_none_when_no_branch_anywhere(self):
        from services.payment_service import PaymentService

        user = MagicMock(branch_id=None)
        with (
            patch(f"{MOD}.branch_scope_id_for", return_value=None),
            patch(f"{MOD}.current_user", new=_user_mock(is_authenticated=False, branch_id=None)),
        ):
            assert PaymentService._resolve_branch_id(user=user) is None


class TestSupplierFxGuards:
    def _payment(self, **kw):
        base = {
            "exchange_rate": Decimal("3.5"),
            "amount": Decimal("100"),
            "amount_aed": Decimal("350"),
            "currency": "USD",
            "branch_id": 2,
            "payment_number": "PAY-1",
            "payment_confirmed": True,
        }
        base.update(kw)
        return MagicMock(**base)

    def _purchase(self, **kw):
        base = {"exchange_rate": Decimal("3.0"), "currency": "USD", "amount_aed": Decimal("300")}
        base.update(kw)
        purchase = MagicMock(**base)
        purchase.get_paid_amount.return_value = Decimal("0")
        return purchase

    def _run(self, payment, purchase):
        from services.payment_service import PaymentService

        with (
            patch(f"{MOD}.GLService") as gl,
            patch(f"{MOD}.post_or_fail") as post,
        ):
            PaymentService._post_supplier_fx_gain_loss(payment, purchase, 1)
        return gl, post

    def test_no_purchase_returns(self):
        gl, post = self._run(self._payment(), None)
        post.assert_not_called()

    def test_unconfirmed_payment_returns(self):
        gl, post = self._run(self._payment(payment_confirmed=False), self._purchase())
        post.assert_not_called()

    def test_zero_amount_returns(self):
        gl, post = self._run(self._payment(amount=Decimal("0")), self._purchase())
        post.assert_not_called()

    def test_equal_rates_return(self):
        payment = self._payment(exchange_rate=Decimal("3.0"))
        gl, post = self._run(payment, self._purchase())
        post.assert_not_called()

    def test_cross_currency_fully_open_returns(self):
        # open_before <= 0: paid covers the whole purchase amount
        purchase = self._purchase(currency="EUR", amount_aed=Decimal("100"))
        purchase.get_paid_amount.return_value = Decimal("110")
        payment = self._payment(currency="USD", amount_aed=Decimal("10"))
        gl, post = self._run(payment, purchase)
        post.assert_not_called()

    def test_cross_currency_partial_payment_returns(self):
        # remaining_after > 0.01 -> gain/loss stays in the open balance
        purchase = self._purchase(currency="EUR", amount_aed=Decimal("1000"))
        purchase.get_paid_amount.return_value = Decimal("60")
        payment = self._payment(currency="USD", amount_aed=Decimal("50"))
        gl, post = self._run(payment, purchase)
        post.assert_not_called()

    def test_tiny_diff_returns(self):
        payment = self._payment(amount=Decimal("1"), amount_aed=Decimal("3.000"), exchange_rate=Decimal("3.0001"))
        gl, post = self._run(payment, self._purchase())
        post.assert_not_called()


class TestCreatePaymentBranches:
    def test_supplier_missing_raises(self):
        from services.payment_service import PaymentService

        with (
            patch(f"{MOD}.current_user", new=_user_mock()),
            patch(f"{MOD}.branch_scope_id_for", return_value=None),
            patch(f"{MOD}.db") as mock_db,
        ):
            mock_db.session.get.return_value = None
            try:
                PaymentService.create_payment({"supplier_id": 9, "amount": "10"})
            except ValueError:
                pass
            else:
                raise AssertionError("expected ValueError")

    def test_purchase_none_skips_fx(self):
        from services.payment_service import PaymentService

        supplier = MagicMock(id=2, tenant_id=1, name="Sup", apply_payment=MagicMock())
        with (
            patch(f"{MOD}.current_user", new=_user_mock()),
            patch(f"{MOD}.branch_scope_id_for", return_value=None),
            patch(f"{MOD}.db") as mock_db,
            patch(f"{MOD}.generate_number", return_value="PAY-1"),
            patch(f"{MOD}.PaymentService._resolve_transaction_rate", return_value=Decimal("1")),
            patch(f"{MOD}.resolve_tenant_base_currency", return_value="AED"),
            patch(f"{MOD}.GLService"),
            patch(f"{MOD}.post_or_fail", return_value=MagicMock(id=50)),
            patch(f"{MOD}.current_app"),
            patch(f"{MOD}.PaymentService._post_supplier_fx_gain_loss") as fx,
        ):
            mock_db.session.get.side_effect = [supplier, None]
            payment = PaymentService.create_payment(
                {"supplier_id": 2, "amount": "10", "currency": "AED", "purchase_id": 7}
            )
        assert payment.payment_number == "PAY-1"
        fx.assert_not_called()

    def test_flush_failure_raises(self):
        from services.payment_service import PaymentService

        supplier = MagicMock(id=2, tenant_id=1, name="Sup", apply_payment=MagicMock())
        with (
            patch(f"{MOD}.current_user", new=_user_mock()),
            patch(f"{MOD}.branch_scope_id_for", return_value=None),
            patch(f"{MOD}.db") as mock_db,
            patch(f"{MOD}.generate_number", return_value="PAY-1"),
            patch(f"{MOD}.PaymentService._resolve_transaction_rate", return_value=Decimal("1")),
            patch(f"{MOD}.resolve_tenant_base_currency", return_value="AED"),
            patch(f"{MOD}.GLService"),
            patch(f"{MOD}.post_or_fail", return_value=MagicMock(id=50)),
            patch(f"{MOD}.current_app"),
        ):
            mock_db.session.get.return_value = supplier
            mock_db.session.flush.side_effect = [None, RuntimeError("boom")]
            try:
                PaymentService.create_payment({"supplier_id": 2, "amount": "10", "currency": "AED"})
            except RuntimeError:
                pass
            else:
                raise AssertionError("expected RuntimeError")

    def test_cheque_path_creates_cheque(self):
        from services.payment_service import PaymentService

        supplier = MagicMock(id=2, tenant_id=1, name="Sup", apply_payment=MagicMock())
        with (
            patch(f"{MOD}.current_user", new=_user_mock()),
            patch(f"{MOD}.branch_scope_id_for", return_value=None),
            patch(f"{MOD}.db") as mock_db,
            patch(f"{MOD}.generate_number", return_value="PAY-1"),
            patch(f"{MOD}.PaymentService._resolve_transaction_rate", return_value=Decimal("1")),
            patch(f"{MOD}.resolve_tenant_base_currency", return_value="AED"),
            patch(f"{MOD}.GLService"),
            patch(f"{MOD}.post_or_fail", return_value=MagicMock(id=50)),
            patch(f"{MOD}.current_app"),
        ):
            mock_db.session.get.return_value = supplier
            payment = PaymentService.create_payment(
                {
                    "supplier_id": 2,
                    "amount": "10",
                    "currency": "AED",
                    "payment_method": "cheque",
                    "cheque_number": "CH-1",
                }
            )
        assert payment.payment_confirmed is False
        supplier.apply_payment.assert_called_once()


class TestSupplierRefund:
    def test_missing_supplier_raises(self):
        from services.payment_service import PaymentService

        with patch(f"{MOD}.db") as mock_db:
            mock_db.session.get.return_value = None
            try:
                PaymentService.create_supplier_refund(9, "10", "AED", "cash")
            except ValueError:
                pass
            else:
                raise AssertionError("expected ValueError")

    def test_success_posts_refund(self):
        from services.payment_service import PaymentService

        supplier = MagicMock(id=3, tenant_id=1, name="Sup", apply_payment=MagicMock())
        with (
            patch(f"{MOD}.current_user", new=_user_mock()),
            patch(f"{MOD}.db") as mock_db,
            patch(f"{MOD}.generate_number", return_value="PAY-R1"),
            patch(f"{MOD}.PaymentService._resolve_transaction_rate", return_value=Decimal("1")),
            patch(f"{MOD}.resolve_tenant_base_currency", return_value="AED"),
            # create_supplier_refund imports GLService locally
            patch("services.gl_service.GLService") as gl,
            patch(f"{MOD}.post_or_fail", return_value=MagicMock(id=51)) as post,
        ):
            mock_db.session.get.return_value = supplier
            gl.get_payment_debit_account.return_value = "1110"
            gl.get_payment_debit_concept.return_value = "CASH"
            payment = PaymentService.create_supplier_refund(3, "25", "AED", "cash")
        assert payment.payment_number == "PAY-R1"
        post.assert_called_once()
        supplier.apply_payment.assert_called_once()


class TestCustomerPayment:
    def test_missing_customer_raises(self):
        from services.payment_service import PaymentService

        with patch(f"{MOD}.db") as mock_db:
            mock_db.session.get.return_value = None
            try:
                PaymentService.create_customer_payment(9, "10")
            except ValueError:
                pass
            else:
                raise AssertionError("expected ValueError")

    def test_success_with_branch(self):
        from services.payment_service import PaymentService

        customer = MagicMock(id=5, tenant_id=1, apply_receipt=MagicMock())
        with (
            patch(f"{MOD}.current_user", new=_user_mock()),
            patch(f"{MOD}.db") as mock_db,
            patch("utils.helpers.generate_number", return_value="PAY-C1"),
        ):
            mock_db.session.get.return_value = customer
            payment = PaymentService.create_customer_payment(5, "40", branch_id=2, user_id=9)
        assert payment.branch_id == 2
        customer.apply_receipt.assert_called_once_with(Decimal("40"))

    def test_resolves_branch_from_user(self):
        from services.payment_service import PaymentService

        customer = MagicMock(id=5, tenant_id=1, apply_receipt=MagicMock())
        user = MagicMock(branch_id=7)
        with (
            patch(f"{MOD}.current_user", new=_user_mock()),
            patch(f"{MOD}.db") as mock_db,
            patch("utils.helpers.generate_number", return_value="PAY-C2"),
        ):
            mock_db.session.get.side_effect = [customer, user]
            payment = PaymentService.create_customer_payment(5, "40", user_id=9)
        assert payment.branch_id == 7

    def test_missing_user_leaves_branch_unset(self):
        from services.payment_service import PaymentService

        customer = MagicMock(id=5, tenant_id=1, apply_receipt=MagicMock())
        with (
            patch(f"{MOD}.current_user", new=_user_mock()),
            patch(f"{MOD}.db") as mock_db,
            patch("utils.helpers.generate_number", return_value="PAY-C3"),
        ):
            mock_db.session.get.side_effect = [customer, None]
            payment = PaymentService.create_customer_payment(5, "40", user_id=9)
        assert payment.branch_id is None


class TestCustomerRefund:
    def test_missing_customer_raises(self):
        from services.payment_service import PaymentService

        with patch(f"{MOD}.db") as mock_db:
            mock_db.session.get.return_value = None
            try:
                PaymentService.create_customer_refund(9, "10", "AED", "1", "10", "cash")
            except ValueError:
                pass
            else:
                raise AssertionError("expected ValueError")

    def test_cheque_path(self):
        from services.payment_service import PaymentService

        customer = MagicMock(id=5, name="Cust")
        cheque = MagicMock(id=11)
        with (
            patch(f"{MOD}.current_user", new=_user_mock()),
            patch(f"{MOD}.db") as mock_db,
            patch("utils.helpers.generate_number", return_value="PAY-RF1"),
            patch("services.cheque_service.ChequeService.create_cheque", return_value=cheque) as mk,
            patch("services.cheque_service.process_cheque_issue") as issue,
        ):
            mock_db.session.get.return_value = customer
            payment = PaymentService.create_customer_refund(5, "30", "AED", "1", "30", "cheque", cheque_number="CH-9")
        assert payment.cheque_id == 11
        assert payment.payment_confirmed is False
        mk.assert_called_once()
        issue.assert_called_once_with(cheque)

    def test_gl_path(self):
        from services.payment_service import PaymentService

        customer = MagicMock(id=5, name="Cust")
        with (
            patch(f"{MOD}.current_user", new=_user_mock()),
            patch(f"{MOD}.db") as mock_db,
            patch("utils.helpers.generate_number", return_value="PAY-RF2"),
            # create_customer_refund imports GLService locally
            patch("services.gl_service.GLService") as gl,
            patch(f"{MOD}.post_or_fail", return_value=MagicMock(id=52)) as post,
        ):
            mock_db.session.get.return_value = customer
            gl.get_payment_credit_account.return_value = "1110"
            gl.get_customer_credit_account.return_value = "1130"
            gl.get_customer_credit_concept.return_value = "AR"
            gl.get_payment_credit_concept.return_value = "CASH"
            payment = PaymentService.create_customer_refund(5, "30", "AED", "1", "30", "cash")
        assert payment.payment_number == "PAY-RF2"
        post.assert_called_once()


class TestReceiptFxAndAllocation:
    def _customer(self):
        return MagicMock(id=5, tenant_id=1, name="Cust", apply_receipt=MagicMock())

    def _sale(self, **kw):
        base = {
            "id": 9,
            "currency": "USD",
            "exchange_rate": Decimal("3.0"),
            "customer_id": 999,
            "branch_id": 2,
            "tenant_id": 1,
            "balance_due": Decimal("1000"),
        }
        base.update(kw)
        return MagicMock(**base)

    def _run_receipt(self, data, rate, customer=None, sale=None, flush_side=None):
        from services.payment_service import PaymentService

        customer = customer or self._customer()
        gets = [customer]
        if data.get("allocate_to_sales"):
            gets.append(sale if sale is not None else self._sale())
            n_sales = len(data["allocate_to_sales"])
            gets.extend([sale if sale is not None else self._sale()] * n_sales)
        with (
            patch(f"{MOD}.current_user", new=_user_mock()),
            patch(f"{MOD}.branch_scope_id_for", return_value=None),
            patch(f"{MOD}.db") as mock_db,
            patch(f"{MOD}.generate_number", return_value="RCV-1"),
            patch(f"{MOD}.PaymentService._resolve_transaction_rate", return_value=rate),
            patch(f"{MOD}.resolve_tenant_base_currency", return_value="AED"),
            patch(f"{MOD}.GLService") as gl,
            patch(f"{MOD}.post_or_fail", return_value=MagicMock(id=60)) as post,
            patch(f"{MOD}.current_app"),
        ):
            mock_db.session.get.side_effect = gets
            if flush_side is not None:
                mock_db.session.flush.side_effect = flush_side
            gl.get_payment_debit_account.return_value = "1110"
            gl.get_customer_credit_account.return_value = "1130"
            gl.get_payment_debit_concept.return_value = "CASH"
            gl.get_customer_credit_concept.return_value = "AR"
            gl.get_account_code_for_concept.return_value = "4400"
            receipt = PaymentService.create_receipt(data)
        return receipt, post

    def _base_data(self, **kw):
        base = {"customer_id": 5, "amount": "100", "currency": "USD", "payment_method": "cash"}
        base.update(kw)
        return base

    def test_fx_gain_posts_second_entry(self):
        receipt, post = self._run_receipt(self._base_data(allocate_to_sales={9: 10}), Decimal("3.5"))
        assert post.call_count == 2
        fx_lines = post.call_args_list[1].args[0]
        assert fx_lines[0]["concept_code"] == "AR"
        assert fx_lines[0]["debit"] == Decimal("50.000")
        assert receipt.receipt_number == "RCV-1"

    def test_fx_loss_posts_loss_entry(self):
        receipt, post = self._run_receipt(self._base_data(allocate_to_sales={9: 10}), Decimal("2.5"))
        assert post.call_count == 2
        fx_lines = post.call_args_list[1].args[0]
        assert fx_lines[0]["concept_code"] == "FX_LOSS"

    def test_equal_rates_skip_fx(self):
        receipt, post = self._run_receipt(self._base_data(allocate_to_sales={9: 10}), Decimal("3.0"))
        assert post.call_count == 1

    def test_tiny_diff_skips_fx(self):
        receipt, post = self._run_receipt(self._base_data(amount="1", allocate_to_sales={9: 10}), Decimal("3.0001"))
        assert post.call_count == 1

    def test_zero_amount_breaks_allocation(self):
        receipt, post = self._run_receipt(self._base_data(amount="0", allocate_to_sales={9: 10}), Decimal("3.0"))
        assert post.call_count == 1

    def test_zero_allocatable_continues(self):
        sale = self._sale(customer_id=5, balance_due=Decimal("0"))
        receipt, post = self._run_receipt(self._base_data(allocate_to_sales={9: 50}), Decimal("3.0"), sale=sale)
        assert post.call_count == 1

    def test_full_allocation_path(self):
        sale = self._sale(
            customer_id=5,
            balance_due=Decimal("1000"),
            paid_amount_aed=Decimal("0"),
            paid_amount=Decimal("0"),
            exchange_rate=Decimal("3.0"),
        )
        receipt, post = self._run_receipt(
            self._base_data(amount="100", allocate_to_sales={9: 50}), Decimal("3.0"), sale=sale
        )
        assert post.call_count == 1
        sale.recalculate_payment_status.assert_called_once()

    def test_allocation_skips_paid_amount_when_sale_rate_zero(self):
        # sale_rate = Decimal(str(exchange_rate or 1)): only a negative rate
        # stays <= 0 (0/None fall back to 1), taking the 842->846 arc.
        sale = self._sale(
            customer_id=5,
            balance_due=Decimal("1000"),
            paid_amount_aed=Decimal("0"),
            paid_amount=Decimal("0"),
            exchange_rate=Decimal("-2"),
        )
        receipt, post = self._run_receipt(
            self._base_data(amount="100", allocate_to_sales={9: 50}), Decimal("3.0"), sale=sale
        )
        # FX entry fires (sale rate 0 vs receipt rate 3.0) + main entry
        assert post.call_count == 2
        sale.recalculate_payment_status.assert_called_once()

    def test_allocation_flush_failure_raises(self):
        sale = self._sale(
            customer_id=5,
            balance_due=Decimal("1000"),
            paid_amount_aed=Decimal("0"),
            paid_amount=Decimal("0"),
            exchange_rate=Decimal("3.0"),
        )
        try:
            self._run_receipt(
                self._base_data(amount="100", allocate_to_sales={9: 50}),
                Decimal("3.0"),
                sale=sale,
                flush_side=[None, None, RuntimeError("flush")],
            )
        except RuntimeError:
            pass
        else:
            raise AssertionError("expected RuntimeError")


class TestScopedBalances:
    def test_customer_balance_resolves_tenant_and_branch(self):
        from services.payment_service import PaymentService

        with (
            patch(f"{MOD}.db") as mock_db,
            patch(f"{MOD}.get_active_tenant_id", return_value=4),
        ):
            mock_db.session.query.side_effect = [
                _chain(scalar=Decimal("100")),
                _chain(scalar=Decimal("30")),
                _chain(scalar=Decimal("5")),
            ]
            bal = PaymentService.get_customer_balance_scoped(5, branch_id=2, tenant_id=None)
        # receipts(30) - sales(100) - outgoing(5)
        assert bal == Decimal("-75")

    def test_customer_balance_none_scalars(self):
        from services.payment_service import PaymentService

        with (
            patch(f"{MOD}.db") as mock_db,
            patch(f"{MOD}.get_active_tenant_id", return_value=None),
        ):
            mock_db.session.query.side_effect = [_chain(), _chain(), _chain()]
            assert PaymentService.get_customer_balance_scoped(5) == Decimal("0")

    def test_supplier_balance_resolves_tenant_and_branch(self):
        from services.payment_service import PaymentService

        with (
            patch(f"{MOD}.db") as mock_db,
            patch(f"{MOD}.get_active_tenant_id", return_value=4),
        ):
            mock_db.session.query.side_effect = [
                _chain(scalar=Decimal("500")),
                _chain(scalar=Decimal("200")),
                _chain(scalar=Decimal("50")),
            ]
            bal = PaymentService.get_supplier_balance_scoped(6, branch_id=2, tenant_id=None)
        assert bal == Decimal("350")

    def test_supplier_balance_with_explicit_tenant_no_branch(self):
        from services.payment_service import PaymentService

        with patch(f"{MOD}.db") as mock_db:
            mock_db.session.query.side_effect = [
                _chain(scalar=Decimal("500")),
                _chain(scalar=Decimal("200")),
                _chain(scalar=Decimal("50")),
            ]
            bal = PaymentService.get_supplier_balance_scoped(6, tenant_id=1)
        assert bal == Decimal("350")

    def test_supplier_balance_without_tenant_or_branch(self):
        from services.payment_service import PaymentService

        with (
            patch(f"{MOD}.db") as mock_db,
            patch(f"{MOD}.get_active_tenant_id", return_value=None),
        ):
            mock_db.session.query.side_effect = [_chain(), _chain(), _chain()]
            assert PaymentService.get_supplier_balance_scoped(6) == Decimal("0")


class TestAllocateOldest:
    def test_no_unpaid_sales_flushes(self):
        from services.payment_service import PaymentService

        receipt = MagicMock(amount_aed=Decimal("100"), receipt_number="RCV-7")
        customer = MagicMock()
        with (
            patch(f"{MOD}.db"),
            patch.object(PaymentService, "get_unpaid_sales", return_value=[]),
            patch(f"{MOD}.current_app"),
        ):
            PaymentService.allocate_receipt_to_oldest_sales(receipt, customer)
        customer.apply_receipt.assert_called_once_with(Decimal("100"))

    def test_breaks_when_fully_allocated(self):
        from services.payment_service import PaymentService

        receipt = MagicMock(
            amount_aed=Decimal("100"),
            receipt_number="RCV-8",
            branch_id=2,
            currency="AED",
            exchange_rate=Decimal("1"),
            payment_method="cash",
            payment_confirmed=True,
            cheque_id=None,
        )
        customer = MagicMock(id=5, tenant_id=1)
        s1 = MagicMock(
            balance_due=Decimal("100"),
            exchange_rate=Decimal("1"),
            tenant_id=1,
            id=1,
            branch_id=2,
            paid_amount_aed=Decimal("0"),
            paid_amount=Decimal("0"),
        )
        s2 = MagicMock(
            balance_due=Decimal("50"),
            exchange_rate=Decimal("1"),
            tenant_id=1,
            id=2,
            branch_id=2,
            paid_amount_aed=Decimal("0"),
            paid_amount=Decimal("0"),
        )
        with (
            patch(f"{MOD}.db"),
            patch.object(PaymentService, "get_unpaid_sales", return_value=[s1, s2]),
            patch(f"{MOD}.generate_number", return_value="PAY-S1"),
            patch(f"{MOD}.current_user", new=_user_mock()),
            patch(f"{MOD}.current_app"),
        ):
            PaymentService.allocate_receipt_to_oldest_sales(receipt, customer)
        assert s2.recalculate_payment_status.call_count == 0
        s1.recalculate_payment_status.assert_called_once()


class TestDeletes:
    def test_delete_receipt_with_and_without_cheque(self):
        from services.payment_service import PaymentService

        cheque = MagicMock()
        with patch(f"{MOD}.db") as mock_db:
            PaymentService.delete_receipt(MagicMock(cheque=cheque))
            assert mock_db.session.delete.call_count == 2
            mock_db.session.delete.reset_mock()
            PaymentService.delete_receipt(MagicMock(cheque=None))
            assert mock_db.session.delete.call_count == 1

    def test_delete_payment_with_and_without_cheque(self):
        from services.payment_service import PaymentService

        cheque = MagicMock()
        with patch(f"{MOD}.db") as mock_db:
            PaymentService.delete_payment(MagicMock(cheque=cheque))
            assert mock_db.session.delete.call_count == 2
            mock_db.session.delete.reset_mock()
            PaymentService.delete_payment(MagicMock(cheque=None))
            assert mock_db.session.delete.call_count == 1
