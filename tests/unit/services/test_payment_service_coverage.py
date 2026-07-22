from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest


class TestPaymentServiceHelpers:
    def test_resolve_transaction_rate(self, app):
        from services.payment_service import PaymentService

        with (
            app.app_context(),
            patch(
                "services.payment_service.ExchangeRateService.resolve_exchange_rate_for_transaction",
                return_value={"rate": 3.67, "rate_mode": "auto"},
            ),
        ):
            rate = PaymentService._resolve_transaction_rate("USD", tenant_id=1)
        assert rate == Decimal("3.67")

    def test_resolve_transaction_rate_needs_input(self, app):
        from services.payment_service import PaymentService

        with (
            app.app_context(),
            patch(
                "services.payment_service.ExchangeRateService.resolve_exchange_rate_for_transaction",
                return_value={"rate_mode": "needs_input"},
            ),
        ):
            with pytest.raises(ValueError, match="سعر الصرف"):
                PaymentService._resolve_transaction_rate("USD")

    def test_resolve_branch_id_explicit(self):
        from services.payment_service import PaymentService

        assert PaymentService._resolve_branch_id(5) == 5

    def test_resolve_branch_id_from_sale(self):
        from services.payment_service import PaymentService

        sale = MagicMock(branch_id=3)
        assert PaymentService._resolve_branch_id(sale=sale) == 3

    def test_resolve_branch_id_from_user(self):
        from services.payment_service import PaymentService

        user = MagicMock(branch_id=7)
        with patch("services.payment_service.branch_scope_id_for", return_value=None):
            assert PaymentService._resolve_branch_id(user=user) == 7

    def test_get_customer_balance_aed(self):
        from services.payment_service import PaymentService

        customer = MagicMock()
        customer.get_balance_aed.return_value = Decimal("150.50")
        assert PaymentService.get_customer_balance_aed(customer) == Decimal("150.50")

    def test_get_customer_balance_scoped(self):
        from services.payment_service import PaymentService

        def _query_chain(scalar_val):
            chain = MagicMock()
            chain.filter.return_value = chain
            chain.scalar.return_value = scalar_val
            return chain

        with (
            patch("services.payment_service.db") as mock_db,
            patch("services.payment_service.get_active_tenant_id", return_value=1),
        ):
            mock_db.session.query.side_effect = [
                _query_chain(Decimal("1000")),
                _query_chain(Decimal("400")),
                _query_chain(Decimal("50")),
            ]
            bal = PaymentService.get_customer_balance_scoped(5, branch_id=2, tenant_id=1)
        assert bal == Decimal("-650")

    def test_get_supplier_balance_scoped(self):
        from services.payment_service import PaymentService

        def _query_chain(scalar_val):
            chain = MagicMock()
            chain.filter.return_value = chain
            chain.scalar.return_value = scalar_val
            return chain

        with (
            patch("services.payment_service.db") as mock_db,
            patch("services.payment_service.get_active_tenant_id", return_value=1),
            patch("services.payment_service.Purchase", create=True),
        ):
            mock_db.session.query.side_effect = [
                _query_chain(Decimal("500")),
                _query_chain(Decimal("200")),
                _query_chain(Decimal("50")),
            ]
            bal = PaymentService.get_supplier_balance_scoped(3, branch_id=1)
        assert bal == Decimal("350")

    def test_get_unpaid_sales(self, mocker):
        from services.payment_service import PaymentService

        class _Col:
            def __gt__(self, other):
                return MagicMock()

            def __eq__(self, other):
                return MagicMock()

            @staticmethod
            def asc():
                return MagicMock()

        Sale = mocker.patch("services.payment_service.Sale")
        Sale.customer_id = _Col()
        Sale.status = _Col()
        Sale.balance_due = _Col()
        Sale.sale_date = _Col()
        Sale.query.filter.return_value.order_by.return_value.all.return_value = [MagicMock(id=1)]
        result = PaymentService.get_unpaid_sales(MagicMock(id=5))
        assert len(result) == 1

    def test_get_customer_balance_and_unpaid_sales(self):
        from services.payment_service import PaymentService

        customer = MagicMock(id=1)
        sale = MagicMock(
            id=2,
            sale_number="S-1",
            sale_date=MagicMock(strftime=lambda fmt: "2025-01-01"),
            total_amount=Decimal("100"),
            balance_due=Decimal("50"),
            currency="AED",
        )
        with (
            patch.object(PaymentService, "get_customer_balance_aed", return_value=Decimal("50")),
            patch.object(PaymentService, "get_unpaid_sales", return_value=[sale]),
        ):
            data = PaymentService.get_customer_balance_and_unpaid_sales(customer)
        assert data["balance_aed"] == 50.0
        assert len(data["unpaid_sales"]) == 1


class TestPaymentServiceCreatePayment:
    def test_create_payment_supplier_not_found(self, app):
        from services.payment_service import PaymentService

        with (
            app.app_context(),
            patch("services.payment_service.db") as mock_db,
            patch(
                "services.payment_service.current_user",
                MagicMock(is_authenticated=True, id=1, tenant_id=1),
            ),
        ):
            mock_db.session.get.return_value = None
            with pytest.raises(ValueError, match="المورد"):
                PaymentService.create_payment({"supplier_id": 99, "amount": 100})

    def test_create_payment_success_cash(self, app):
        from services.payment_service import PaymentService

        supplier = MagicMock(id=1, name="Sup", tenant_id=1)
        payment = MagicMock(
            id=10,
            payment_number="PAY-1",
            branch_id=1,
            amount=Decimal("100"),
            amount_aed=Decimal("100"),
            payment_confirmed=True,
        )
        with (
            app.app_context(),
            patch("services.payment_service.db") as mock_db,
            patch(
                "services.payment_service.current_user",
                MagicMock(is_authenticated=True, id=1, tenant_id=1),
            ),
            patch("services.payment_service.generate_number", return_value="PAY-001"),
            patch.object(PaymentService, "_resolve_transaction_rate", return_value=Decimal("1")),
            patch.object(PaymentService, "_resolve_branch_id", return_value=1),
            patch("services.payment_service.GLService") as gl,
            patch("services.payment_service.post_or_fail"),
        ):
            mock_db.session.get.return_value = supplier
            gl.get_payment_credit_account.return_value = "1120"
            gl.get_payment_credit_concept.return_value = "CASH"
            gl.ensure_core_accounts.return_value = None
            with patch("models.Payment", return_value=payment):
                result = PaymentService.create_payment(
                    {
                        "supplier_id": 1,
                        "amount": Decimal("100"),
                        "currency": "AED",
                        "payment_method": "cash",
                    }
                )
            assert result is payment

    def test_create_payment_posts_fx_when_purchase_linked(self, app):
        from services.payment_service import PaymentService

        supplier = MagicMock(id=1, name="Sup", tenant_id=1)
        purchase = MagicMock(id=7, currency="USD", exchange_rate=Decimal("3.0"))
        payment = MagicMock(
            id=10,
            payment_number="PAY-1",
            branch_id=1,
            amount=Decimal("100"),
            amount_aed=Decimal("350"),
            payment_confirmed=True,
        )
        with (
            app.app_context(),
            patch("services.payment_service.db") as mock_db,
            patch(
                "services.payment_service.current_user",
                MagicMock(is_authenticated=True, id=1, tenant_id=1),
            ),
            patch("services.payment_service.generate_number", return_value="PAY-001"),
            patch.object(PaymentService, "_resolve_transaction_rate", return_value=Decimal("3.5")),
            patch.object(PaymentService, "_resolve_branch_id", return_value=1),
            patch("services.payment_service.GLService"),
            patch("services.payment_service.post_or_fail"),
            patch.object(PaymentService, "_post_supplier_fx_gain_loss") as fx,
        ):
            mock_db.session.get.side_effect = lambda model, pk: supplier if model.__name__ == "Supplier" else purchase
            with patch("models.Payment", return_value=payment):
                PaymentService.create_payment(
                    {
                        "supplier_id": 1,
                        "amount": Decimal("100"),
                        "currency": "USD",
                        "payment_method": "cash",
                        "purchase_id": 7,
                    }
                )
        fx.assert_called_once_with(payment, purchase, 1)
        assert payment.purchase_id == 7


class TestSupplierFxGainLoss:
    def _payment(self, amount="100", rate="3.5"):
        return MagicMock(
            id=10,
            payment_number="PAY-FX-1",
            branch_id=1,
            amount=Decimal(amount),
            exchange_rate=Decimal(rate),
            currency="USD",
        )

    def _run(self, payment, purchase):
        from services.payment_service import PaymentService

        with (
            patch("services.payment_service.GLService") as gl,
            patch("services.payment_service.post_or_fail") as post,
            patch("services.payment_service.resolve_tenant_base_currency", return_value="AED"),
        ):
            gl.get_account_code_for_concept.side_effect = lambda code, **kw: {
                "AP": "2110",
                "FX_LOSS": "6600",
                "FX_GAIN": "4400",
            }[code]
            PaymentService._post_supplier_fx_gain_loss(payment, purchase, tenant_id=1)
        return post

    def test_fx_loss_when_rate_rises(self):
        purchase = MagicMock(currency="USD", exchange_rate=Decimal("3.0"))
        post = self._run(self._payment(rate="3.5"), purchase)
        post.assert_called_once()
        lines = post.call_args.args[0]
        assert lines[0]["concept_code"] == "FX_LOSS"
        assert lines[0]["debit"] == Decimal("50.000")
        assert lines[1]["concept_code"] == "AP"
        assert lines[1]["credit"] == Decimal("50.000")

    def test_fx_gain_when_rate_falls(self):
        purchase = MagicMock(currency="USD", exchange_rate=Decimal("3.0"))
        post = self._run(self._payment(rate="2.5"), purchase)
        post.assert_called_once()
        lines = post.call_args.args[0]
        assert lines[0]["concept_code"] == "AP"
        assert lines[0]["debit"] == Decimal("50.000")
        assert lines[1]["concept_code"] == "FX_GAIN"
        assert lines[1]["credit"] == Decimal("50.000")

    def test_no_fx_when_rates_match(self):
        purchase = MagicMock(currency="USD", exchange_rate=Decimal("3.5"))
        post = self._run(self._payment(rate="3.5"), purchase)
        post.assert_not_called()

    def test_fx_when_currency_differs(self):
        purchase = MagicMock(currency="EUR", exchange_rate=Decimal("3.0"), amount=Decimal("100"))
        post = self._run(self._payment(rate="3.5"), purchase)
        post.assert_called_once()

    def test_no_fx_below_threshold(self):
        purchase = MagicMock(currency="USD", exchange_rate=Decimal("3.0"))
        post = self._run(self._payment(rate="3.00005"), purchase)
        post.assert_not_called()

    def test_create_receipt_customer_not_found(self, app):
        from services.payment_service import PaymentService

        with app.app_context(), patch("services.payment_service.db") as mock_db:
            mock_db.session.get.return_value = None
            with pytest.raises(ValueError, match="Customer not found"):
                PaymentService.create_receipt({"customer_id": 1, "amount": 50})

    def test_create_receipt_invalid_cheque_date(self, app):
        from services.payment_service import PaymentService

        customer = MagicMock(id=1, tenant_id=1)
        with app.app_context(), patch("services.payment_service.db") as mock_db:
            mock_db.session.get.return_value = customer
            with pytest.raises(ValueError, match="تاريخ الشيك"):
                PaymentService.create_receipt(
                    {
                        "customer_id": 1,
                        "amount": 50,
                        "cheque_date": "bad-date",
                    }
                )

    def test_allocate_receipt_to_oldest_sales(self, app):
        from services.payment_service import PaymentService

        customer = MagicMock(id=1, tenant_id=1)
        receipt = MagicMock(
            amount_aed=Decimal("100"),
            receipt_number="RCV-1",
            currency="AED",
            exchange_rate=Decimal("1"),
            payment_method="cash",
            payment_confirmed=True,
            branch_id=1,
        )
        sale = MagicMock(
            id=2,
            balance_due=Decimal("100"),
            branch_id=1,
            tenant_id=1,
            exchange_rate=Decimal("1"),
        )
        with (
            app.app_context(),
            patch.object(PaymentService, "get_unpaid_sales", return_value=[sale]),
            patch("services.payment_service.generate_number", return_value="PAY-S-1"),
            patch("services.payment_service.db") as mock_db,
            patch(
                "services.payment_service.current_user",
                MagicMock(is_authenticated=True, id=1),
            ),
        ):
            PaymentService.allocate_receipt_to_oldest_sales(receipt, customer)
            customer.apply_receipt.assert_called_once()
            mock_db.session.flush.assert_called()


class TestPaymentServiceResolveBranch:
    def test_resolve_branch_from_scope(self):
        from services.payment_service import PaymentService

        user = MagicMock(branch_id=None)
        with patch("services.payment_service.branch_scope_id_for", return_value=9):
            assert PaymentService._resolve_branch_id(user=user) == 9

    def test_resolve_branch_from_current_user(self):
        from services.payment_service import PaymentService

        with (
            patch("services.payment_service.branch_scope_id_for", return_value=None),
            patch(
                "services.payment_service.current_user",
                MagicMock(is_authenticated=True, branch_id=4),
            ),
        ):
            assert PaymentService._resolve_branch_id() == 4


class TestPaymentServiceCreateReceiptSuccess:
    def test_create_receipt_cash_success(self, app):
        from services.payment_service import PaymentService

        customer = MagicMock(id=1, tenant_id=1, name="Cust")
        receipt = MagicMock(
            id=10,
            receipt_number="RCV-1",
            amount=Decimal("100"),
            amount_aed=Decimal("100"),
            payment_method="cash",
            payment_confirmed=True,
            branch_id=1,
            currency="AED",
            exchange_rate=Decimal("1"),
        )
        with (
            app.app_context(),
            patch("services.payment_service.db") as mock_db,
            patch(
                "services.payment_service.current_user",
                MagicMock(is_authenticated=True, id=1, tenant_id=1),
            ),
            patch("services.payment_service.generate_number", return_value="RCV-001"),
            patch.object(PaymentService, "_resolve_transaction_rate", return_value=Decimal("1")),
            patch.object(PaymentService, "_resolve_branch_id", return_value=1),
            patch("services.payment_service.GLService") as gl,
            patch("services.payment_service.post_or_fail"),
            patch("services.payment_service.Receipt", return_value=receipt),
        ):
            mock_db.session.get.return_value = customer
            gl.get_payment_debit_account.return_value = "1100"
            gl.get_payment_debit_concept.return_value = "CASH"
            gl.get_customer_credit_account.return_value = "1200"
            gl.get_customer_credit_concept.return_value = "AR"
            gl.ensure_core_accounts.return_value = None
            result = PaymentService.create_receipt(
                {
                    "customer_id": 1,
                    "amount": 100,
                    "currency": "AED",
                    "payment_method": "cash",
                }
            )
            assert result is not None
            customer.apply_receipt.assert_called_once()

    def test_create_receipt_cheque_success(self, app):
        from services.payment_service import PaymentService

        customer = MagicMock(id=1, tenant_id=1, name="Cust")
        receipt = MagicMock(
            id=11,
            receipt_number="RCV-2",
            amount=Decimal("200"),
            amount_aed=Decimal("200"),
            payment_method="cheque",
            payment_confirmed=False,
            branch_id=1,
            currency="AED",
            exchange_rate=Decimal("1"),
            receipt_date=datetime.now(),
        )
        with (
            app.app_context(),
            patch("services.payment_service.db") as mock_db,
            patch(
                "services.payment_service.current_user",
                MagicMock(is_authenticated=True, id=1, tenant_id=1),
            ),
            patch("services.payment_service.generate_number", return_value="RCV-002"),
            patch.object(PaymentService, "_resolve_transaction_rate", return_value=Decimal("1")),
            patch.object(PaymentService, "_resolve_branch_id", return_value=1),
            patch(
                "services.payment_service.process_cheque_receive",
                return_value=MagicMock(),
            ),
            patch("models.Cheque"),
            patch("services.payment_service.Receipt", return_value=receipt),
        ):
            mock_db.session.get.return_value = customer
            result = PaymentService.create_receipt(
                {
                    "customer_id": 1,
                    "amount": 200,
                    "currency": "AED",
                    "payment_method": "cheque",
                    "cheque_number": "CHQ1",
                    "cheque_date": "2026-06-30",
                    "bank_name": "ENBD",
                }
            )
            assert result is receipt

    def test_create_receipt_with_allocation(self, app):
        from services.payment_service import PaymentService

        customer = MagicMock(id=1, tenant_id=1, name="Cust")
        sale = MagicMock(
            id=2,
            customer_id=1,
            branch_id=1,
            tenant_id=1,
            balance_due=Decimal("100"),
            exchange_rate=Decimal("1"),
        )
        receipt = MagicMock(
            id=12,
            receipt_number="RCV-3",
            amount_aed=Decimal("100"),
            amount=Decimal("100"),
            payment_method="cash",
            payment_confirmed=True,
            branch_id=1,
            currency="AED",
            exchange_rate=Decimal("1"),
        )
        with (
            app.app_context(),
            patch("services.payment_service.db") as mock_db,
            patch(
                "services.payment_service.current_user",
                MagicMock(is_authenticated=True, id=1, tenant_id=1),
            ),
            patch("services.payment_service.generate_number", return_value="PAY-S-1"),
            patch.object(PaymentService, "_resolve_transaction_rate", return_value=Decimal("1")),
            patch.object(PaymentService, "_resolve_branch_id", return_value=1),
            patch("services.payment_service.GLService") as gl,
            patch("services.payment_service.post_or_fail"),
            patch("services.payment_service.Receipt", return_value=receipt),
            patch("models.Payment", return_value=MagicMock()),
        ):
            mock_db.session.get.side_effect = lambda model, pk: customer if pk == 1 else sale
            gl.get_payment_debit_account.return_value = "1100"
            gl.get_payment_debit_concept.return_value = "CASH"
            gl.get_customer_credit_account.return_value = "1200"
            gl.get_customer_credit_concept.return_value = "AR"
            gl.ensure_core_accounts.return_value = None
            PaymentService.create_receipt(
                {
                    "customer_id": 1,
                    "amount": 100,
                    "currency": "AED",
                    "payment_method": "cash",
                    "allocate_to_sales": {2: 100},
                }
            )
            sale.recalculate_payment_status.assert_called()


class TestPaymentServiceCreatePaymentExtended:
    def test_create_payment_cheque(self, app):
        from services.payment_service import PaymentService

        supplier = MagicMock(id=1, name="Sup", tenant_id=1)
        payment = MagicMock(
            id=10,
            payment_number="PAY-1",
            branch_id=1,
            amount=Decimal("100"),
            amount_aed=Decimal("100"),
            payment_confirmed=False,
        )
        with (
            app.app_context(),
            patch("services.payment_service.db") as mock_db,
            patch(
                "services.payment_service.current_user",
                MagicMock(is_authenticated=True, id=1, tenant_id=1),
            ),
            patch("services.payment_service.generate_number", return_value="PAY-001"),
            patch.object(PaymentService, "_resolve_transaction_rate", return_value=Decimal("1")),
            patch.object(PaymentService, "_resolve_branch_id", return_value=1),
            patch("services.payment_service.GLService") as gl,
            patch("services.payment_service.post_or_fail"),
            patch("models.Cheque"),
            patch("models.Payment", return_value=payment),
        ):
            mock_db.session.get.return_value = supplier
            gl.get_payment_credit_account.return_value = "1120"
            gl.get_payment_credit_concept.return_value = "BANK"
            gl.ensure_core_accounts.return_value = None
            result = PaymentService.create_payment(
                {
                    "supplier_id": 1,
                    "amount": Decimal("100"),
                    "currency": "AED",
                    "payment_method": "cheque",
                    "cheque_number": "CHQ1",
                    "cheque_date": "2026-06-30",
                    "bank_name": "ENBD",
                }
            )
            assert result is payment


class TestPaymentServiceFailurePaths:
    def test_create_payment_gl_failure(self, app):
        from services.payment_service import PaymentService

        supplier = MagicMock(id=1, name="Sup", tenant_id=1)
        payment = MagicMock(
            id=10,
            payment_number="PAY-GL",
            branch_id=1,
            amount=Decimal("100"),
            amount_aed=Decimal("100"),
            payment_confirmed=True,
            currency="AED",
            exchange_rate=Decimal("1"),
        )
        with (
            app.app_context(),
            patch("services.payment_service.db") as mock_db,
            patch(
                "services.payment_service.current_user",
                MagicMock(is_authenticated=True, id=1, tenant_id=1),
            ),
            patch("services.payment_service.generate_number", return_value="PAY-GL"),
            patch.object(PaymentService, "_resolve_transaction_rate", return_value=Decimal("1")),
            patch.object(PaymentService, "_resolve_branch_id", return_value=1),
            patch("services.payment_service.GLService") as gl,
            patch("services.payment_service.post_or_fail", side_effect=RuntimeError("gl")),
            patch("models.Payment", return_value=payment),
            patch("services.payment_service.current_app") as capp,
        ):
            mock_db.session.get.return_value = supplier
            gl.get_payment_credit_account.return_value = "1120"
            gl.get_payment_credit_concept.return_value = "CASH"
            gl.ensure_core_accounts.return_value = None
            capp.logger = MagicMock()
            with pytest.raises(ValueError, match="فشل الترحيل المحاسبي"):
                PaymentService.create_payment(
                    {
                        "supplier_id": 1,
                        "amount": Decimal("100"),
                        "currency": "AED",
                        "payment_method": "cash",
                    }
                )

    def test_create_receipt_fx_gain_on_allocation(self, app):
        from services.payment_service import PaymentService

        customer = MagicMock(id=1, tenant_id=1, name="Cust")
        source_sale = MagicMock(
            id=2,
            customer_id=1,
            branch_id=1,
            tenant_id=1,
            currency="USD",
            exchange_rate=Decimal("3.67"),
            balance_due=Decimal("100"),
        )
        source_sale.recalculate_payment_status = MagicMock()
        receipt = MagicMock(
            id=12,
            receipt_number="RCV-FX",
            amount=Decimal("100"),
            amount_aed=Decimal("380"),
            payment_method="cash",
            payment_confirmed=True,
            branch_id=1,
            currency="USD",
            exchange_rate=Decimal("3.80"),
        )
        with (
            app.app_context(),
            patch("services.payment_service.db") as mock_db,
            patch(
                "services.payment_service.current_user",
                MagicMock(is_authenticated=True, id=1, tenant_id=1),
            ),
            patch("services.payment_service.generate_number", return_value="RCV-FX"),
            patch.object(
                PaymentService,
                "_resolve_transaction_rate",
                return_value=Decimal("3.80"),
            ),
            patch.object(PaymentService, "_resolve_branch_id", return_value=1),
            patch("services.payment_service.GLService") as gl,
            patch("services.payment_service.post_or_fail") as post,
            patch("services.payment_service.Receipt", return_value=receipt),
            patch("models.Payment", return_value=MagicMock()),
        ):
            mock_db.session.get.side_effect = lambda model, pk: customer if pk == 1 else source_sale
            gl.get_payment_debit_account.return_value = "1100"
            gl.get_payment_debit_concept.return_value = "CASH"
            gl.get_customer_credit_account.return_value = "1200"
            gl.get_customer_credit_concept.return_value = "AR"
            gl.get_account_code_for_concept.return_value = "4900"
            gl.ensure_core_accounts.return_value = None
            PaymentService.create_receipt(
                {
                    "customer_id": 1,
                    "amount": 100,
                    "currency": "USD",
                    "payment_method": "cash",
                    "allocate_to_sales": {2: 100},
                }
            )
            assert post.call_count >= 2

    def test_create_receipt_allocation_skips_invalid_sale(self, app):
        from services.payment_service import PaymentService

        customer = MagicMock(id=1, tenant_id=1, name="Cust")
        receipt = MagicMock(
            id=13,
            receipt_number="RCV-SKIP",
            amount_aed=Decimal("50"),
            amount=Decimal("50"),
            payment_method="cash",
            payment_confirmed=True,
            branch_id=1,
            currency="AED",
            exchange_rate=Decimal("1"),
        )
        with (
            app.app_context(),
            patch("services.payment_service.db") as mock_db,
            patch(
                "services.payment_service.current_user",
                MagicMock(is_authenticated=True, id=1, tenant_id=1),
            ),
            patch("services.payment_service.generate_number", return_value="RCV-SKIP"),
            patch.object(PaymentService, "_resolve_transaction_rate", return_value=Decimal("1")),
            patch.object(PaymentService, "_resolve_branch_id", return_value=1),
            patch("services.payment_service.GLService") as gl,
            patch("services.payment_service.post_or_fail"),
            patch("services.payment_service.Receipt", return_value=receipt),
        ):
            mock_db.session.get.side_effect = lambda model, pk: customer if pk == 1 else None
            gl.get_payment_debit_account.return_value = "1100"
            gl.get_payment_debit_concept.return_value = "CASH"
            gl.get_customer_credit_account.return_value = "1200"
            gl.get_customer_credit_concept.return_value = "AR"
            gl.ensure_core_accounts.return_value = None
            PaymentService.create_receipt(
                {
                    "customer_id": 1,
                    "amount": 50,
                    "currency": "AED",
                    "payment_method": "cash",
                    "allocate_to_sales": {99: 50},
                }
            )
            customer.apply_receipt.assert_called_once()


class TestPaymentServiceReceiptCommitFailure:
    def test_create_receipt_commit_failure(self, app):
        from services.payment_service import PaymentService

        customer = MagicMock(id=1, tenant_id=1, name="Cust")
        receipt = MagicMock(
            id=14,
            receipt_number="RCV-COMMIT",
            amount=Decimal("50"),
            amount_aed=Decimal("50"),
            payment_method="cash",
            payment_confirmed=True,
            branch_id=1,
            currency="AED",
            exchange_rate=Decimal("1"),
        )
        with (
            app.app_context(),
            patch("services.payment_service.db") as mock_db,
            patch(
                "services.payment_service.current_user",
                MagicMock(is_authenticated=True, id=1, tenant_id=1),
            ),
            patch("services.payment_service.generate_number", return_value="RCV-COMMIT"),
            patch.object(PaymentService, "_resolve_transaction_rate", return_value=Decimal("1")),
            patch.object(PaymentService, "_resolve_branch_id", return_value=1),
            patch("services.payment_service.GLService") as gl,
            patch("services.payment_service.post_or_fail"),
            patch("services.payment_service.Receipt", return_value=receipt),
            patch("services.payment_service.current_app") as capp,
        ):
            mock_db.session.get.return_value = customer
            mock_db.session.flush.side_effect = RuntimeError("commit fail")
            gl.get_payment_debit_account.return_value = "1100"
            gl.get_payment_debit_concept.return_value = "CASH"
            gl.get_customer_credit_account.return_value = "1200"
            gl.get_customer_credit_concept.return_value = "AR"
            gl.ensure_core_accounts.return_value = None
            capp.logger = MagicMock()
            with pytest.raises(RuntimeError, match="commit fail"):
                PaymentService.create_receipt(
                    {
                        "customer_id": 1,
                        "amount": 50,
                        "currency": "AED",
                        "payment_method": "cash",
                    }
                )

    def test_create_receipt_outer_exception(self, app):
        from services.payment_service import PaymentService

        customer = MagicMock(id=1, tenant_id=1, name="Cust")
        with (
            app.app_context(),
            patch("services.payment_service.db") as mock_db,
            patch(
                "services.payment_service.current_user",
                MagicMock(is_authenticated=True, id=1, tenant_id=1),
            ),
            patch(
                "services.payment_service.generate_number",
                side_effect=RuntimeError("gen fail"),
            ),
            patch.object(PaymentService, "_resolve_transaction_rate", return_value=Decimal("1")),
            patch.object(PaymentService, "_resolve_branch_id", return_value=1),
            patch("services.payment_service.current_app") as capp,
        ):
            mock_db.session.get.return_value = customer
            capp.logger = MagicMock()
            with pytest.raises(RuntimeError, match="gen fail"):
                PaymentService.create_receipt(
                    {
                        "customer_id": 1,
                        "amount": 50,
                        "currency": "AED",
                        "payment_method": "cash",
                    }
                )


class TestPaymentServicePaymentCommitFailure:
    def test_create_payment_commit_failure(self, app):
        from services.payment_service import PaymentService

        supplier = MagicMock(id=1, name="Sup", tenant_id=1)
        payment = MagicMock(
            id=10,
            payment_number="PAY-C",
            branch_id=1,
            amount=Decimal("100"),
            amount_aed=Decimal("100"),
            payment_confirmed=True,
            currency="AED",
            exchange_rate=Decimal("1"),
        )
        with (
            app.app_context(),
            patch("services.payment_service.db") as mock_db,
            patch(
                "services.payment_service.current_user",
                MagicMock(is_authenticated=True, id=1, tenant_id=1),
            ),
            patch("services.payment_service.generate_number", return_value="PAY-C"),
            patch.object(PaymentService, "_resolve_transaction_rate", return_value=Decimal("1")),
            patch.object(PaymentService, "_resolve_branch_id", return_value=1),
            patch("services.payment_service.GLService") as gl,
            patch("services.payment_service.post_or_fail"),
            patch("models.Payment", return_value=payment),
            patch("services.payment_service.current_app") as capp,
        ):
            mock_db.session.get.return_value = supplier
            mock_db.session.flush.side_effect = RuntimeError("commit fail")
            gl.get_payment_credit_account.return_value = "1120"
            gl.get_payment_credit_concept.return_value = "CASH"
            gl.ensure_core_accounts.return_value = None
            capp.logger = MagicMock()
            with pytest.raises(RuntimeError, match="commit fail"):
                PaymentService.create_payment(
                    {
                        "supplier_id": 1,
                        "amount": Decimal("100"),
                        "currency": "AED",
                        "payment_method": "cash",
                    }
                )

    def test_create_payment_outer_exception(self, app):
        from services.payment_service import PaymentService

        supplier = MagicMock(id=1, name="Sup", tenant_id=1)
        with (
            app.app_context(),
            patch("services.payment_service.db") as mock_db,
            patch(
                "services.payment_service.current_user",
                MagicMock(is_authenticated=True, id=1, tenant_id=1),
            ),
            patch(
                "services.payment_service.generate_number",
                side_effect=RuntimeError("gen fail"),
            ),
            patch("services.payment_service.current_app") as capp,
        ):
            mock_db.session.get.return_value = supplier
            capp.logger = MagicMock()
            with pytest.raises(RuntimeError, match="gen fail"):
                PaymentService.create_payment(
                    {
                        "supplier_id": 1,
                        "amount": Decimal("100"),
                        "currency": "AED",
                        "payment_method": "cash",
                    }
                )


class TestPaymentServiceChequeAndFxLoss:
    def test_create_receipt_cheque_gl_failure(self, app):
        from services.payment_service import PaymentService
        from services.gl_posting import GlPostingError

        customer = MagicMock(id=1, tenant_id=1, name="Cust")
        receipt = MagicMock(
            id=15,
            receipt_number="RCV-CHQ",
            amount=Decimal("200"),
            amount_aed=Decimal("200"),
            payment_method="cheque",
            payment_confirmed=False,
            branch_id=1,
            currency="AED",
            exchange_rate=Decimal("1"),
            receipt_date=datetime.now(),
        )
        with (
            app.app_context(),
            patch("services.payment_service.db") as mock_db,
            patch(
                "services.payment_service.current_user",
                MagicMock(is_authenticated=True, id=1, tenant_id=1),
            ),
            patch("services.payment_service.generate_number", return_value="RCV-CHQ"),
            patch.object(PaymentService, "_resolve_transaction_rate", return_value=Decimal("1")),
            patch.object(PaymentService, "_resolve_branch_id", return_value=1),
            patch("services.payment_service.process_cheque_receive", return_value=None),
            patch("models.Cheque"),
            patch("services.payment_service.Receipt", return_value=receipt),
        ):
            mock_db.session.get.return_value = customer
            with pytest.raises(GlPostingError, match="فشل ترحيل الشيك"):
                PaymentService.create_receipt(
                    {
                        "customer_id": 1,
                        "amount": 200,
                        "currency": "AED",
                        "payment_method": "cheque",
                        "cheque_number": "CHQ1",
                        "cheque_date": "2026-06-30",
                        "bank_name": "ENBD",
                    }
                )

    def test_create_receipt_fx_loss_on_allocation(self, app):
        from services.payment_service import PaymentService

        customer = MagicMock(id=1, tenant_id=1, name="Cust")
        source_sale = MagicMock(
            id=2,
            customer_id=1,
            branch_id=1,
            tenant_id=1,
            currency="USD",
            exchange_rate=Decimal("3.80"),
            balance_due=Decimal("100"),
        )
        source_sale.recalculate_payment_status = MagicMock()
        receipt = MagicMock(
            id=16,
            receipt_number="RCV-LOSS",
            amount=Decimal("100"),
            amount_aed=Decimal("350"),
            payment_method="cash",
            payment_confirmed=True,
            branch_id=1,
            currency="USD",
            exchange_rate=Decimal("3.50"),
        )
        with (
            app.app_context(),
            patch("services.payment_service.db") as mock_db,
            patch(
                "services.payment_service.current_user",
                MagicMock(is_authenticated=True, id=1, tenant_id=1),
            ),
            patch("services.payment_service.generate_number", return_value="RCV-LOSS"),
            patch.object(
                PaymentService,
                "_resolve_transaction_rate",
                return_value=Decimal("3.50"),
            ),
            patch.object(PaymentService, "_resolve_branch_id", return_value=1),
            patch("services.payment_service.GLService") as gl,
            patch("services.payment_service.post_or_fail") as post,
            patch("services.payment_service.Receipt", return_value=receipt),
            patch("models.Payment", return_value=MagicMock()),
        ):
            mock_db.session.get.side_effect = lambda model, pk: customer if pk == 1 else source_sale
            gl.get_payment_debit_account.return_value = "1100"
            gl.get_payment_debit_concept.return_value = "CASH"
            gl.get_customer_credit_account.return_value = "1200"
            gl.get_customer_credit_concept.return_value = "AR"
            gl.get_account_code_for_concept.return_value = "4900"
            gl.ensure_core_accounts.return_value = None
            PaymentService.create_receipt(
                {
                    "customer_id": 1,
                    "amount": 100,
                    "currency": "USD",
                    "payment_method": "cash",
                    "allocate_to_sales": {2: 100},
                }
            )
            assert post.call_count >= 2

    def test_allocate_receipt_commit_failure(self, app):
        from services.payment_service import PaymentService

        customer = MagicMock(id=1, tenant_id=1)
        receipt = MagicMock(
            amount_aed=Decimal("50"),
            receipt_number="RCV-ALLOC",
            currency="AED",
            exchange_rate=Decimal("1"),
            payment_method="cash",
            payment_confirmed=True,
            branch_id=1,
        )
        sale = MagicMock(
            id=2,
            balance_due=Decimal("50"),
            branch_id=1,
            tenant_id=1,
            exchange_rate=Decimal("1"),
        )
        with (
            app.app_context(),
            patch.object(PaymentService, "get_unpaid_sales", return_value=[sale]),
            patch("services.payment_service.generate_number", return_value="PAY-A"),
            patch("services.payment_service.db") as mock_db,
            patch(
                "services.payment_service.current_user",
                MagicMock(is_authenticated=True, id=1),
            ),
            patch("services.payment_service.current_app") as capp,
        ):
            mock_db.session.flush.side_effect = RuntimeError("alloc commit fail")
            capp.logger = MagicMock()
            with pytest.raises(RuntimeError, match="alloc commit fail"):
                PaymentService.allocate_receipt_to_oldest_sales(receipt, customer)

    def test_create_receipt_gl_posting_failure(self, app):
        from services.payment_service import PaymentService

        customer = MagicMock(id=1, tenant_id=1, name="Cust")
        receipt = MagicMock(
            id=17,
            receipt_number="RCV-GL",
            amount=Decimal("50"),
            amount_aed=Decimal("50"),
            payment_method="cash",
            payment_confirmed=True,
            branch_id=1,
            currency="AED",
            exchange_rate=Decimal("1"),
        )
        with (
            app.app_context(),
            patch("services.payment_service.db") as mock_db,
            patch(
                "services.payment_service.current_user",
                MagicMock(is_authenticated=True, id=1, tenant_id=1),
            ),
            patch("services.payment_service.generate_number", return_value="RCV-GL"),
            patch.object(PaymentService, "_resolve_transaction_rate", return_value=Decimal("1")),
            patch.object(PaymentService, "_resolve_branch_id", return_value=1),
            patch("services.payment_service.GLService") as gl,
            patch(
                "services.payment_service.post_or_fail",
                side_effect=RuntimeError("gl fail"),
            ),
            patch("services.payment_service.Receipt", return_value=receipt),
            patch("services.payment_service.current_app") as capp,
        ):
            mock_db.session.get.return_value = customer
            gl.get_payment_debit_account.return_value = "1100"
            gl.get_payment_debit_concept.return_value = "CASH"
            gl.get_customer_credit_account.return_value = "1200"
            gl.get_customer_credit_concept.return_value = "AR"
            gl.ensure_core_accounts.return_value = None
            capp.logger = MagicMock()
            with pytest.raises(ValueError, match="فشل الترحيل المحاسبي"):
                PaymentService.create_receipt(
                    {
                        "customer_id": 1,
                        "amount": 50,
                        "currency": "AED",
                        "payment_method": "cash",
                    }
                )

    def test_create_receipt_fx_post_raises_on_error(self, app):
        from services.payment_service import PaymentService

        customer = MagicMock(id=1, tenant_id=1, name="Cust")
        source_sale = MagicMock(
            id=2,
            customer_id=1,
            branch_id=1,
            tenant_id=1,
            currency="USD",
            exchange_rate=Decimal("3.80"),
            balance_due=Decimal("100"),
        )
        source_sale.recalculate_payment_status = MagicMock()
        receipt = MagicMock(
            id=18,
            receipt_number="RCV-FXSKIP",
            amount=Decimal("100"),
            amount_aed=Decimal("380"),
            payment_method="cash",
            payment_confirmed=True,
            branch_id=1,
            currency="USD",
            exchange_rate=Decimal("3.50"),
        )
        with (
            app.app_context(),
            patch("services.payment_service.db") as mock_db,
            patch(
                "services.payment_service.current_user",
                MagicMock(is_authenticated=True, id=1, tenant_id=1),
            ),
            patch("services.payment_service.generate_number", return_value="RCV-FXSKIP"),
            patch.object(
                PaymentService,
                "_resolve_transaction_rate",
                return_value=Decimal("3.50"),
            ),
            patch.object(PaymentService, "_resolve_branch_id", return_value=1),
            patch("services.payment_service.GLService") as gl,
            patch(
                "services.payment_service.post_or_fail",
                side_effect=[None, RuntimeError("fx skip")],
            ),
            patch("services.payment_service.Receipt", return_value=receipt),
            patch("models.Payment", return_value=MagicMock()),
            patch("services.payment_service.current_app") as capp,
        ):
            mock_db.session.get.side_effect = lambda model, pk: customer if pk == 1 else source_sale
            gl.get_payment_debit_account.return_value = "1100"
            gl.get_payment_debit_concept.return_value = "CASH"
            gl.get_customer_credit_account.return_value = "1200"
            gl.get_customer_credit_concept.return_value = "AR"
            gl.get_account_code_for_concept.return_value = "4900"
            gl.ensure_core_accounts.return_value = None
            capp.logger = MagicMock()
            with pytest.raises(ValueError, match="فشل الترحيل المحاسبي"):
                PaymentService.create_receipt(
                    {
                        "customer_id": 1,
                        "amount": 100,
                        "currency": "USD",
                        "payment_method": "cash",
                        "allocate_to_sales": {2: 100},
                    }
                )
            capp.logger.exception.assert_called()

    def test_allocate_receipt_zero_balance_skipped(self, app):
        from services.payment_service import PaymentService

        customer = MagicMock(id=1, tenant_id=1)
        receipt = MagicMock(
            amount_aed=Decimal("50"),
            receipt_number="RCV-ZERO",
            currency="AED",
            exchange_rate=Decimal("1"),
            payment_method="cash",
            payment_confirmed=True,
            branch_id=1,
        )
        sale = MagicMock(
            id=2,
            balance_due=Decimal("0"),
            branch_id=1,
            tenant_id=1,
            exchange_rate=Decimal("1"),
        )
        with (
            app.app_context(),
            patch.object(PaymentService, "get_unpaid_sales", return_value=[sale]),
            patch("services.payment_service.generate_number", return_value="PAY-Z"),
            patch("services.payment_service.db"),
            patch(
                "services.payment_service.current_user",
                MagicMock(is_authenticated=True, id=1),
            ),
        ):
            PaymentService.allocate_receipt_to_oldest_sales(receipt, customer)
            customer.apply_receipt.assert_called_once()
