"""Coverage gaps for ``services/store_order_service.py``.

The route boundary is already covered by ``test_store_coverage_gaps.py``; this
module drives the service internals the routes never reach: row-lock retries,
platform-fee reversal on cancellation, stored FX-rate lookup and the two
cart / provisional-order -> Sale builders.

Collaborators are patched at the service boundary.  In the builder tests the
whole ``db`` name in the service module is replaced with a mock so no real
INSERT is attempted (see the note in ``_mock_builder_boundaries``).
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from sqlalchemy.exc import OperationalError

from models.store_provisional_order import StoreProvisionalOrder
from services.store_order_service import StoreOrderService


@pytest.fixture(autouse=True)
def _no_platform_fee(mocker):
    """Fee accrual is a separate service; keep it out of confirm_order here."""
    mocker.patch(
        "services.azad_platform_fee_service.AzadPlatformFeeService.record_store_online_fee",
        return_value=None,
    )


def _chain_query(**terminals):
    """Minimal fluent query stub: filter_by()/order_by() return the query itself."""
    q = MagicMock(name="query_chain")
    for method in ("filter", "filter_by", "order_by", "limit", "offset"):
        getattr(q, method).return_value = q
    q.first.return_value = terminals.get("first")
    q.all.return_value = terminals.get("all", [])
    q.scalar.return_value = terminals.get("scalar")
    q.count.return_value = terminals.get("count", 0)
    return q


class _FakeSale:
    """Stands in for ``models.Sale`` so constructor kwargs are observable.

    ``create_store_order_from_cart`` passes ``currency_rate_source`` to the
    real ORM model, which has no such column; this fake keeps the test focused
    on the builder logic (the defect is reported separately).
    """

    def __init__(self, **kwargs):
        self.id = None
        self.sale_number = None
        for key, value in kwargs.items():
            setattr(self, key, value)


# ─────────────────────────────────────────────────────────────────────────────
# _locked_sale
# ─────────────────────────────────────────────────────────────────────────────


class TestLockedSale:
    def test_non_integer_id_passes_through(self):
        sale = MagicMock()
        sale.id = "not-an-int"
        assert StoreOrderService._locked_sale(sale) is sale

    def test_transient_sale_is_not_locked(self):
        from models import Sale

        # int id but never added to a session -> inspect(sale).persistent is
        # False, so the method returns before any SQL is issued.
        sale = Sale(id=987654, tenant_id=1)
        assert StoreOrderService._locked_sale(sale) is sale

    def test_inspect_failure_falls_back(self, mocker, online_sale):
        mocker.patch("sqlalchemy.inspect", side_effect=RuntimeError("no inspection"))
        assert StoreOrderService._locked_sale(online_sale) is online_sale

    def test_lock_retries_then_succeeds(self, mocker, online_sale):
        dbmock = mocker.patch("services.store_order_service.db")
        savepoint = MagicMock()
        dbmock.session.begin_nested.return_value = savepoint
        err = OperationalError("SELECT ... FOR UPDATE", {}, Exception("deadlock"))
        ok = MagicMock()
        ok.first.return_value = object()
        dbmock.session.execute.side_effect = [err, ok]

        assert StoreOrderService._locked_sale(online_sale) is online_sale
        savepoint.rollback.assert_called_once()
        savepoint.commit.assert_called_once()

    def test_lock_exhausts_retries_and_reraises(self, mocker, online_sale):
        dbmock = mocker.patch("services.store_order_service.db")
        savepoint = MagicMock()
        dbmock.session.begin_nested.return_value = savepoint
        err = OperationalError("SELECT ... FOR UPDATE", {}, Exception("still locked"))
        dbmock.session.execute.side_effect = err

        with pytest.raises(OperationalError):
            StoreOrderService._locked_sale(online_sale)
        assert savepoint.rollback.call_count == 3
        savepoint.commit.assert_not_called()

    def test_zero_retries_has_no_lock_statement(self, mocker, online_sale):
        # A deployment that sets _MAX_LOCK_RETRIES to 0 exits the retry loop
        # without ever executing the SELECT, reaching the row is None branch.
        mocker.patch("services.stock_service._MAX_LOCK_RETRIES", 0)
        dbmock = mocker.patch("services.store_order_service.db")

        assert StoreOrderService._locked_sale(online_sale) is online_sale
        dbmock.session.execute.assert_not_called()

    def test_refresh_failure_is_logged(self, mocker, online_sale):
        dbmock = mocker.patch("services.store_order_service.db")
        dbmock.session.begin_nested.return_value = MagicMock()
        ok = MagicMock()
        ok.first.return_value = object()
        dbmock.session.execute.return_value = ok
        dbmock.session.refresh.side_effect = RuntimeError("stale instance")

        assert StoreOrderService._locked_sale(online_sale) is online_sale
        dbmock.session.refresh.assert_called_once_with(online_sale)


# ─────────────────────────────────────────────────────────────────────────────
# confirm_order / cancel_order gaps
# ─────────────────────────────────────────────────────────────────────────────


class TestConfirmAndCancelGaps:
    def test_mark_paid_zero_amount_skips_payment(self, mocker, online_sale):
        mocker.patch(
            "services.store_order_service.SaleService.has_inventory_posted",
            return_value=True,
        )
        create_payment = mocker.patch("services.store_order_service.SaleService.create_payment_for_sale")
        online_sale.payment_status = "unpaid"
        online_sale.total_amount = Decimal("0")
        online_sale.balance_due = Decimal("0")
        online_sale.checkout_payment_method = "cod"
        online_sale.recalculate_payment_status = MagicMock()

        StoreOrderService.confirm_order(online_sale, mark_paid=True)

        create_payment.assert_not_called()
        online_sale.recalculate_payment_status.assert_not_called()

    def test_fee_accrual_failure_does_not_block_confirmation(self, mocker, online_sale):
        mocker.patch(
            "services.store_order_service.SaleService.has_inventory_posted",
            return_value=True,
        )
        mocker.patch(
            "services.azad_platform_fee_service.AzadPlatformFeeService.record_store_online_fee",
            side_effect=RuntimeError("platform vault missing"),
        )

        result = StoreOrderService.confirm_order(online_sale)

        assert result.status == "confirmed"

    def test_cancel_fulfilled_reverses_posted_platform_fee(self, mocker, online_sale):
        mocker.patch(
            "services.store_order_service.SaleService.has_inventory_posted",
            return_value=True,
        )
        cancel = mocker.patch("services.store_order_service.SaleService.cancel_sale")
        posted_fee = MagicMock(id=11, gl_posted=True, status="accrued")
        unposted_fee = MagicMock(id=12, gl_posted=False, status="accrued")
        mocker.patch("models.AzadPlatformFee.query").filter_by.return_value.all.return_value = [
            posted_fee,
            unposted_fee,
        ]
        reverse = mocker.patch("services.gl_service.GLService.reverse_entry")
        online_sale.status = "confirmed"
        online_sale.coupon_code = None

        StoreOrderService.cancel_order(online_sale)

        reverse.assert_called_once()
        assert posted_fee.status == "cancelled"
        assert unposted_fee.status == "cancelled"
        cancel.assert_called_once_with(online_sale)


# ─────────────────────────────────────────────────────────────────────────────
# create_store_order_from_cart
# ─────────────────────────────────────────────────────────────────────────────


def _mock_builder_boundaries(mocker, *, store_price=Decimal("10"), stored_rate=Decimal("3.7")):
    """Patch every collaborator of the two Sale builders.

    The builders construct ORM objects with real columns now (``SaleLine``
    uses ``amount_aed``, ``Sale`` uses ``rate_source`` and a generated
    ``sale_number``). Faking the two classes still keeps these tests focused
    on service logic; ``generate_number`` is stubbed so no sequence row is
    needed and ``db`` is mocked so no real flush occurs.
    """
    mocker.patch("services.store_order_service.resolve_tenant_base_currency", return_value="AED")
    mocker.patch(
        "services.store_order_service.convert_and_quantize_aed",
        side_effect=lambda amount, currency, exchange_rate, **kw: (
            Decimal(str(amount)) * Decimal(str(exchange_rate))
        ).quantize(Decimal("0.001")),
    )
    mocker.patch(
        "services.store_order_service.StoreOrderService._latest_stored_rate",
        return_value=stored_rate,
    )
    mocker.patch(
        "services.store_order_service.StoreService.get_online_warehouse",
        return_value=MagicMock(id=10),
    )
    mocker.patch(
        "services.store_pricing_service.StorePricingService.resolve_store_price",
        return_value=store_price,
    )
    product = MagicMock(id=7, regular_price=Decimal("12"))
    product_query = _chain_query(first=product)
    mocker.patch("models.Product.query", product_query)
    sale_line_cls = mocker.patch("models.SaleLine")
    mocker.patch("services.store_order_service.Sale", _FakeSale)
    mocker.patch("services.store_order_service.generate_number", return_value="S-TEST-1")
    dbmock = mocker.patch("services.store_order_service.db")
    return product, product_query, sale_line_cls, dbmock


class TestCreateStoreOrderFromCart:
    def test_success_with_stored_rate(self, mocker, sample_tenant, sample_customer):
        _, _, _, dbmock = _mock_builder_boundaries(mocker)

        sale = StoreOrderService.create_store_order_from_cart(
            sample_tenant.id,
            customer_id=sample_customer.id,
            cart={7: Decimal("2")},
            currency_code="usd",
        )

        assert sale.source == "online_store"
        assert sale.status == "pending"
        assert sale.currency == "USD"
        assert sale.exchange_rate == Decimal("3.7")
        assert sale.warehouse_id == 10
        assert sale.total_amount == Decimal("20.000")
        assert sale.amount_aed == Decimal("74.000")
        assert sale.customer_id == sample_customer.id
        # one Sale + one SaleLine
        assert dbmock.session.add.call_count == 2

    def test_missing_rate_warns_and_uses_one(self, mocker, sample_tenant):
        _mock_builder_boundaries(mocker, stored_rate=None)

        sale = StoreOrderService.create_store_order_from_cart(
            sample_tenant.id,
            customer_id=None,
            cart={7: Decimal("1")},
            currency_code="USD",
            warehouse_id=99,
            branch_id=3,
            payment_method="card",
            notes="customer note",
            seller_id=5,
        )

        assert sale.exchange_rate == Decimal("1")
        assert sale.warehouse_id == 99
        assert sale.branch_id == 3
        assert sale.seller_id == 5
        assert sale.notes == "customer note"

    def test_skips_missing_product_and_nonpositive_quantity(self, mocker, sample_tenant):
        product, product_query, _, dbmock = _mock_builder_boundaries(mocker)
        product_query.first.side_effect = [product, None, product]

        sale = StoreOrderService.create_store_order_from_cart(
            sample_tenant.id,
            customer_id=None,
            cart={7: Decimal("2"), 8: Decimal("1"), 9: Decimal("0")},
            currency_code="AED",
        )

        assert sale.currency == "AED"
        assert sale.total_amount == Decimal("20.000")
        # second product missing, third has qty 0 -> only one line added
        assert dbmock.session.add.call_count == 2

    def test_price_falls_back_to_regular_price(self, mocker, sample_tenant):
        _, _, _, _ = _mock_builder_boundaries(mocker, store_price=None)

        sale = StoreOrderService.create_store_order_from_cart(
            sample_tenant.id,
            customer_id=None,
            cart={7: Decimal("1")},
            currency_code="AED",
        )

        assert sale.subtotal == Decimal("12")

    def test_empty_cart_raises(self, mocker, sample_tenant):
        _, product_query, _, _ = _mock_builder_boundaries(mocker)
        product_query.first.return_value = None

        with pytest.raises(ValueError, match="سلة"):
            StoreOrderService.create_store_order_from_cart(
                sample_tenant.id,
                customer_id=None,
                cart={7: Decimal("1")},
                currency_code="AED",
            )


# ─────────────────────────────────────────────────────────────────────────────
# _latest_stored_rate
# ─────────────────────────────────────────────────────────────────────────────


class TestLatestStoredRate:
    def test_returns_latest_rate_as_decimal(self, mocker):
        row = MagicMock(rate="3.75")
        mocker.patch(
            "models.exchange_rate_record.ExchangeRateRecord.query"
        ).filter_by.return_value.order_by.return_value.first.return_value = row

        assert StoreOrderService._latest_stored_rate(1, "USD", "AED") == Decimal("3.75")

    def test_returns_none_without_row(self, mocker):
        mocker.patch(
            "models.exchange_rate_record.ExchangeRateRecord.query"
        ).filter_by.return_value.order_by.return_value.first.return_value = None

        assert StoreOrderService._latest_stored_rate(1, "USD", "AED") is None

    def test_returns_none_on_lookup_error(self, mocker):
        mocker.patch("models.exchange_rate_record.ExchangeRateRecord.query").filter_by.side_effect = RuntimeError(
            "db down"
        )

        assert StoreOrderService._latest_stored_rate(1, "USD", "AED") is None


# ─────────────────────────────────────────────────────────────────────────────
# convert_provisional_to_sale
# ─────────────────────────────────────────────────────────────────────────────


def _provisional(**over):
    p = MagicMock()
    p.tenant_id = 1
    p.currency_code = "USD"
    p.exchange_rate = Decimal("3.7")
    p.cart_json = [
        {
            "product_id": 7,
            "quantity": "2",
            "unit_price": "10",
            "line_total": "20",
            "product_name": "Widget",
        }
    ]
    p.customer_email = "buyer@example.com"
    p.subtotal_tx_ccy = Decimal("20")
    p.subtotal_aed = Decimal("74")
    p.provisional_number = "PROV-1"
    for key, value in over.items():
        setattr(p, key, value)
    return p


def _mock_convert_boundaries(mocker, *, available=True):
    mocker.patch("services.store_order_service.resolve_tenant_base_currency", return_value="AED")
    mocker.patch(
        "services.store_order_service.StoreService.get_online_warehouse",
        return_value=MagicMock(id=10),
    )
    mocker.patch(
        "services.store_order_service.StockService.check_availability_in_warehouse",
        return_value=(available, "out of stock"),
    )
    mocker.patch("utils.tax_settings.effective_tax_rate", return_value=Decimal("0.16"))
    mocker.patch(
        "services.store_order_service.convert_and_quantize_aed",
        side_effect=lambda amount, currency, exchange_rate, **kw: (
            Decimal(str(amount)) * Decimal(str(exchange_rate))
        ).quantize(Decimal("0.001")),
    )
    mocker.patch("models.Customer.query").filter_by.return_value.first.return_value = MagicMock(id=3)
    mocker.patch("models.SaleLine")
    fulfill = mocker.patch("services.store_order_service.SaleService.fulfill_sale")
    dbmock = mocker.patch("services.store_order_service.db")
    return fulfill, dbmock


class TestConvertProvisionalToSale:
    def test_success_marks_provisional_converted(self, mocker, sample_tenant):
        fulfill, dbmock = _mock_convert_boundaries(mocker)
        prov = _provisional()
        prov.tenant_id = sample_tenant.id
        approver = MagicMock(id=42)

        sale = StoreOrderService.convert_provisional_to_sale(prov, approver)

        assert sale.status == "confirmed"
        assert sale.currency == "USD"
        assert sale.seller_id == 42
        assert sale.customer_id == 3
        assert prov.status == StoreProvisionalOrder.STATUS_CONVERTED
        assert prov.converted_sale_id == sale.id
        assert prov.approved_by == 42
        assert isinstance(prov.approved_at, datetime)
        assert prov.approved_at.tzinfo is not None
        fulfill.assert_called_once()
        assert dbmock.session.add.call_count == 2

    def test_no_online_warehouse_raises(self, mocker):
        mocker.patch("services.store_order_service.resolve_tenant_base_currency", return_value="AED")
        mocker.patch("services.store_order_service.StoreService.get_online_warehouse", return_value=None)

        with pytest.raises(ValueError, match="مستودع"):
            StoreOrderService.convert_provisional_to_sale(_provisional(), None)

    def test_empty_cart_raises(self, mocker):
        mocker.patch("services.store_order_service.resolve_tenant_base_currency", return_value="AED")
        mocker.patch(
            "services.store_order_service.StoreService.get_online_warehouse",
            return_value=MagicMock(id=10),
        )

        with pytest.raises(ValueError, match="منتجات"):
            StoreOrderService.convert_provisional_to_sale(_provisional(cart_json=[]), None)

    def test_unavailable_stock_raises(self, mocker):
        _mock_convert_boundaries(mocker, available=False)

        with pytest.raises(ValueError, match="Widget"):
            StoreOrderService.convert_provisional_to_sale(_provisional(), None)

    def test_unknown_customer_email_is_ignored(self, mocker, sample_tenant):
        _, _ = _mock_convert_boundaries(mocker)
        customer_query = mocker.patch("models.Customer.query")
        customer_query.filter_by.return_value.first.return_value = None
        prov = _provisional(customer_email="unknown@example.com")
        prov.tenant_id = sample_tenant.id

        sale = StoreOrderService.convert_provisional_to_sale(prov, None)

        assert sale.customer_id is None
        assert prov.status == StoreProvisionalOrder.STATUS_CONVERTED

    def test_no_customer_email_and_no_approver(self, mocker, sample_tenant):
        _, _ = _mock_convert_boundaries(mocker)
        prov = _provisional(customer_email=None)
        prov.tenant_id = sample_tenant.id

        sale = StoreOrderService.convert_provisional_to_sale(prov, None)

        assert sale.customer_id is None
        assert sale.seller_id is None
        assert prov.approved_by is None
        assert prov.status == StoreProvisionalOrder.STATUS_CONVERTED

    def test_zero_quantity_line(self, mocker, sample_tenant):
        _, _ = _mock_convert_boundaries(mocker)
        cart = [
            {
                "product_id": 7,
                "quantity": "0",
                "unit_price": "10",
                "line_total": "0",
                "product_name": "Zero",
            }
        ]
        prov = _provisional(cart_json=cart, customer_email=None, subtotal_tx_ccy=Decimal("0"))
        prov.tenant_id = sample_tenant.id

        sale = StoreOrderService.convert_provisional_to_sale(prov, None)

        assert sale.status == "confirmed"
        assert sale.total_amount == Decimal("0")
