from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch


def _query_chain(items):
    q = MagicMock()
    q.filter_by.return_value = q
    q.filter.return_value = q
    q.order_by.return_value = q
    q.all.return_value = items
    return q


class TestCustomersStatementBuilder:
    def test_statement_sale_lines_without_product(self, customers_client, bypass_customers_auth):
        line = MagicMock(
            quantity=2,
            unit_price=50,
            discount_percent=10,
            line_total=90,
            notes="n",
            product=None,
        )
        sale = MagicMock(
            id=1,
            sale_number="S-NP",
            sale_date=datetime(2025, 6, 1),
            payment_status="paid",
            subtotal=90,
            discount_amount=0,
            shipping_cost=0,
            tax_rate=0,
            tax_amount=0,
            total_amount=90,
            amount_aed=90,
            paid_amount_aed=90,
            balance_due=0,
            currency="AED",
            exchange_rate=1,
            notes="",
            lines=[line],
        )
        sale.seller = None
        sale.payments.order_by.return_value.all.return_value = []
        with (
            patch("routes.customers.Sale") as SaleMod,
            patch("models.Payment") as PayMod,
            patch("models.Receipt") as RcvMod,
            patch("routes.customers.branch_scope_id", return_value=None),
            patch(
                "routes.customers.resolve_default_currency",
                side_effect=Exception("no tenant"),
            ),
        ):
            SaleMod.query.filter_by.return_value = _query_chain([sale])
            PayMod.query.filter_by.return_value = _query_chain([])
            RcvMod.query.filter_by.return_value = _query_chain([])
            resp = customers_client.get("/customers/1/statement")
        assert resp.status_code == 200

    def test_statement_payment_with_cheque_and_user(self, customers_client, bypass_customers_auth):
        cheque = MagicMock(
            cheque_number="CHQ-9",
            bank_name="ENBD",
            due_date=datetime(2025, 7, 1),
            clearance_date=None,
        )
        user = MagicMock()
        user.get_display_name.return_value = "Cashier"
        payment = MagicMock(
            id=2,
            payment_number="P-9",
            payment_date=datetime(2025, 6, 2),
            amount_aed=50,
            amount=50,
            currency="AED",
            exchange_rate=1,
            reference_number="REF-9",
            payment_method="cheque",
            payment_confirmed=False,
            direction="incoming",
            notes="",
            cheque_number=None,
            bank_name=None,
            status_ar="معلقة",
        )
        payment.cheque = cheque
        payment.get_method_display.return_value = "شيك"
        payment.user = user
        with (
            patch("routes.customers.Sale") as SaleMod,
            patch("models.Payment") as PayMod,
            patch("models.Receipt") as RcvMod,
            patch("routes.customers.branch_scope_id", return_value=None),
        ):
            SaleMod.query.filter_by.return_value = _query_chain([])
            PayMod.query.filter_by.return_value = _query_chain([payment])
            RcvMod.query.filter_by.return_value = _query_chain([])
            resp = customers_client.get("/customers/1/statement?transaction_type=payment")
        assert resp.status_code == 200

    def test_statement_outgoing_payment_debit(self, customers_client, bypass_customers_auth):
        payment = MagicMock(
            id=3,
            payment_number="P-OUT",
            payment_date=datetime(2025, 6, 3),
            amount_aed=30,
            amount=30,
            currency="AED",
            exchange_rate=1,
            reference_number="OUT",
            payment_method="cash",
            payment_confirmed=True,
            direction="outgoing",
            notes="",
            cheque_number=None,
            bank_name=None,
        )
        payment.get_method_display.return_value = "نقد"
        payment.user = None
        payment.cheque = None
        with (
            patch("routes.customers.Sale") as SaleMod,
            patch("models.Payment") as PayMod,
            patch("models.Receipt") as RcvMod,
            patch("routes.customers.branch_scope_id", return_value=None),
        ):
            SaleMod.query.filter_by.return_value = _query_chain([])
            PayMod.query.filter_by.return_value = _query_chain([payment])
            RcvMod.query.filter_by.return_value = _query_chain([])
            resp = customers_client.get("/customers/1/statement")
        assert resp.status_code == 200

    def test_statement_skips_duplicate_receipt_ref(self, customers_client, bypass_customers_auth):
        payment = MagicMock(
            id=4,
            payment_number="P-DUP",
            payment_date=datetime(2025, 6, 4),
            amount_aed=25,
            amount=25,
            currency="AED",
            exchange_rate=1,
            reference_number="RCV-DUP",
            payment_method="cash",
            payment_confirmed=True,
            direction="incoming",
            notes="",
            cheque_number=None,
            bank_name=None,
        )
        payment.get_method_display.return_value = "نقد"
        payment.user = None
        payment.cheque = None
        receipt = MagicMock(
            id=5,
            receipt_number="RCV-DUP",
            receipt_date=datetime(2025, 6, 4),
            amount_aed=25,
            amount=25,
            payment_confirmed=True,
        )
        with (
            patch("routes.customers.Sale") as SaleMod,
            patch("models.Payment") as PayMod,
            patch("models.Receipt") as RcvMod,
            patch("routes.customers.branch_scope_id", return_value=None),
        ):
            SaleMod.query.filter_by.return_value = _query_chain([])
            PayMod.query.filter_by.return_value = _query_chain([payment])
            RcvMod.query.filter_by.return_value = _query_chain([receipt])
            resp = customers_client.get("/customers/1/statement")
        assert resp.status_code == 200

    def test_statement_opening_balance_and_pending_receipt(self, customers_client, bypass_customers_auth):
        sale = MagicMock(
            id=6,
            sale_number="S-OLD",
            sale_date=datetime(2025, 1, 15),
            payment_status="paid",
            subtotal=100,
            discount_amount=0,
            shipping_cost=0,
            tax_rate=0,
            tax_amount=0,
            total_amount=100,
            amount_aed=100,
            paid_amount_aed=100,
            balance_due=0,
            currency="AED",
            exchange_rate=1,
            notes="",
            lines=[],
        )
        sale.seller = MagicMock(full_name="Seller")
        sale.payments.order_by.return_value.all.return_value = []
        receipt = MagicMock(
            id=7,
            receipt_number="RCV-PEND",
            receipt_date=datetime(2025, 2, 1),
            amount_aed=40,
            amount=40,
            payment_confirmed=False,
        )
        with (
            patch("routes.customers.Sale") as SaleMod,
            patch("models.Payment") as PayMod,
            patch("models.Receipt") as RcvMod,
            patch("routes.customers.branch_scope_id", return_value=None),
        ):
            SaleMod.query.filter_by.return_value = _query_chain([sale])
            PayMod.query.filter_by.return_value = _query_chain([])
            RcvMod.query.filter_by.return_value = _query_chain([receipt])
            resp = customers_client.get("/customers/1/statement?date_from=2025-02-01&transaction_type=receipt")
        assert resp.status_code == 200

    def test_statement_sale_with_payments_and_product_sku(self, customers_client, bypass_customers_auth):
        product = MagicMock(sku="SKU-X", unit="kg")
        product.get_display_name.return_value = "Product X"
        line = MagicMock(
            quantity=1,
            unit_price=100,
            discount_percent=0,
            line_total=100,
            notes="",
            product=product,
        )
        p1 = MagicMock(
            id=8,
            payment_number="P1",
            payment_date=datetime(2025, 5, 1),
            amount_aed=60,
            amount=60,
            currency="AED",
            exchange_rate=1,
            reference_number="R1",
            payment_method="cash",
            payment_confirmed=True,
            direction="incoming",
            notes="",
            cheque_number="C1",
            bank_name="B1",
        )
        p1.get_method_display.return_value = "نقد"
        p1.user = MagicMock(full_name="U1")
        p1.cheque = None
        p2 = MagicMock(
            id=9,
            payment_number="P2",
            payment_date=datetime(2025, 5, 10),
            amount_aed=40,
            amount=40,
            currency="AED",
            exchange_rate=1,
            reference_number="R2",
            payment_method="cash",
            payment_confirmed=True,
            direction="incoming",
            notes="",
            cheque_number=None,
            bank_name=None,
        )
        p2.get_method_display.return_value = "نقد"
        p2.user = None
        p2.cheque = None
        sale = MagicMock(
            id=10,
            sale_number="S-FULL",
            sale_date=datetime(2025, 5, 1),
            payment_status="partial",
            subtotal=100,
            discount_amount=5,
            shipping_cost=2,
            tax_rate=5,
            tax_amount=5,
            total_amount=102,
            amount_aed=102,
            paid_amount_aed=100,
            balance_due=2,
            currency="AED",
            exchange_rate=1,
            notes="note",
            lines=[line],
        )
        sale.seller = MagicMock()
        sale.seller.get_display_name.return_value = "Rep"
        sale.payments.order_by.return_value.all.return_value = [p1, p2]
        with (
            patch("routes.customers.Sale") as SaleMod,
            patch("models.Payment") as PayMod,
            patch("models.Receipt") as RcvMod,
            patch("routes.customers.branch_scope_id", return_value=1),
        ):
            SaleMod.query.filter_by.return_value.filter.return_value.order_by.return_value.all.return_value = [sale]
            PayMod.query.filter_by.return_value.filter.return_value.order_by.return_value.all.return_value = []
            RcvMod.query.filter_by.return_value.filter.return_value.order_by.return_value.all.return_value = []
            resp = customers_client.get(
                "/customers/1/statement?date_from=2025-05-01&date_to=2025-05-31&transaction_type=sale"
            )
        assert resp.status_code == 200

    def test_statement_sale_payments_track_last_date(self, customers_client, bypass_customers_auth):
        early = MagicMock(
            id=20,
            payment_number="P-EARLY",
            payment_date=datetime(2025, 5, 1),
            amount_aed=30,
            amount=30,
            currency="AED",
            exchange_rate=1,
            reference_number="R-E",
            payment_method="cash",
            payment_confirmed=True,
            direction="incoming",
            notes="",
            cheque_number=None,
            bank_name=None,
        )
        early.get_method_display.return_value = "نقد"
        early.user = None
        early.cheque = None
        late = MagicMock(
            id=21,
            payment_number="P-LATE",
            payment_date=datetime(2025, 5, 15),
            amount_aed=70,
            amount=70,
            currency="AED",
            exchange_rate=1,
            reference_number="R-L",
            payment_method="cash",
            payment_confirmed=True,
            direction="incoming",
            notes="",
            cheque_number=None,
            bank_name=None,
        )
        late.get_method_display.return_value = "نقد"
        late.user = MagicMock()
        late.user.get_display_name.return_value = "Cashier"
        late.cheque = None
        sale = MagicMock(
            id=22,
            sale_number="S-PAY",
            sale_date=datetime(2025, 5, 1),
            payment_status="partial",
            subtotal=100,
            discount_amount=0,
            shipping_cost=0,
            tax_rate=0,
            tax_amount=0,
            total_amount=100,
            amount_aed=100,
            paid_amount_aed=100,
            balance_due=0,
            currency="AED",
            exchange_rate=1,
            notes="",
            lines=[],
        )
        sale.seller = None
        sale.payments.order_by.return_value.all.return_value = [early, late]
        with (
            patch("routes.customers.Sale") as SaleMod,
            patch("models.Payment") as PayMod,
            patch("models.Receipt") as RcvMod,
            patch("routes.customers.branch_scope_id", return_value=None),
        ):
            SaleMod.query.filter_by.return_value = _query_chain([sale])
            PayMod.query.filter_by.return_value = _query_chain([])
            RcvMod.query.filter_by.return_value = _query_chain([])
            resp = customers_client.get("/customers/1/statement?transaction_type=sale")
        assert resp.status_code == 200
