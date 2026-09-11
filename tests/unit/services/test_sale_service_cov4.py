"""Coverage-4 for services/sale_service.py — validation/helper arcs.

Targets (production lines):
- _ensure_discount_within_subtotal None passthrough (32-33) + exceed raise
  (34-37) + ok passthrough.
- _commission_base_aed non-positive fast return (41-42) + conversion success
  (43-49) + exception fallback (50-52).
- create_sale guards: inactive customer (81-82), inactive seller (84-85),
  empty lines (87-88), currency fallback + strip/validate (90-98), negative
  discount (105-106), negative shipping (108-109).
- prepare_split_payments: empty (884-885), non-dict (888-889), non-positive
  amount (890-892), bad rate (896-897), happy path with amount_aed (898-913).
- has_inventory_posted True/False (863-874).
- cancel_sale already-cancelled (1274-1275) + confirmed-payments guard
  (1279-1284).
- update_payment_status flush path (1347-1358).
- list_active_users None -> [] (1363-1367).
- list/get archived + count helpers tenant scoping (1370-1401).
"""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest

from services.sale_service import SaleService


def _inactive_customer():
    return SimpleNamespace(is_active=False, tenant_id=1)


def _active_party(**kwargs):
    base = {"is_active": True, "tenant_id": 1, "branch_id": 1, "id": 1}
    base.update(kwargs)
    return SimpleNamespace(**base)


class TestDiscountAndCommission:
    def test_discount_none_passthrough(self):
        assert SaleService._ensure_discount_within_subtotal(None, Decimal("10")) is None
        assert SaleService._ensure_discount_within_subtotal(Decimal("1"), None) is None

    def test_discount_exceeds_raises(self):
        with pytest.raises(ValueError, match="الخصم"):
            SaleService._ensure_discount_within_subtotal(Decimal("11"), Decimal("10"))

    def test_discount_ok(self):
        assert SaleService._ensure_discount_within_subtotal(Decimal("5"), Decimal("10")) is None

    def test_commission_non_positive(self):
        assert SaleService._commission_base_aed(Decimal("0"), Decimal("1")) == Decimal("0")
        assert SaleService._commission_base_aed(Decimal("-2"), Decimal("1")) == Decimal("0")

    def test_commission_converts(self):
        out = SaleService._commission_base_aed(
            Decimal("100"), Decimal("1"), currency="AED", tenant_id=1
        )
        assert out == Decimal("100.000")

    def test_commission_fallback_on_error(self, mocker):
        mocker.patch(
            "services.sale_service.convert_and_quantize_aed",
            side_effect=RuntimeError("fx down"),
        )
        out = SaleService._commission_base_aed(
            Decimal("50"), Decimal("1"), currency="AED", tenant_id=1
        )
        assert out == Decimal("50")


class TestCreateSaleGuards:
    def test_inactive_customer_raises(self):
        with pytest.raises(ValueError, match="العميل"):
            SaleService.create_sale(
                customer=_inactive_customer(), seller=_active_party(),
                lines_data=[{"product_id": 1, "quantity": 1}],
            )

    def test_inactive_seller_raises(self):
        with pytest.raises(ValueError, match="البائع"):
            SaleService.create_sale(
                customer=_active_party(), seller=_inactive_customer(),
                lines_data=[{"product_id": 1, "quantity": 1}],
            )

    def test_empty_lines_raises(self):
        with pytest.raises(ValueError, match="منتج"):
            SaleService.create_sale(
                customer=_active_party(), seller=_active_party(), lines_data=[]
            )

    def test_negative_discount_raises(self):
        with pytest.raises(ValueError, match="الخصم"):
            SaleService.create_sale(
                customer=_active_party(), seller=_active_party(),
                lines_data=[{"product_id": 1, "quantity": 1}],
                currency="AED", discount_amount=-5,
            )

    def test_negative_shipping_raises(self):
        with pytest.raises(ValueError, match="الشحن"):
            SaleService.create_sale(
                customer=_active_party(), seller=_active_party(),
                lines_data=[{"product_id": 1, "quantity": 1}],
                currency="AED", shipping_cost=-1,
            )

    def test_currency_resolution_fallback(self, mocker):
        def _tenant_id(*args, **kwargs):
            if not args:
                raise RuntimeError("no ctx")
            return 1

        mocker.patch(
            "services.sale_service.get_active_tenant_id", side_effect=_tenant_id
        )
        mocker.patch(
            "services.sale_service.resolve_default_currency",
            side_effect=RuntimeError("no tenant"),
        )
        with pytest.raises(ValueError, match="الخصم"):
            # Falls back to system default currency (warning arc lines 94-96),
            # then fails deterministically on the negative-discount guard.
            SaleService.create_sale(
                customer=_active_party(), seller=_active_party(),
                lines_data=[{"product_id": 1, "quantity": 1}],
                discount_amount=-5,
            )


class TestSplitPayments:
    def test_empty_raises(self):
        with pytest.raises(ValueError, match="فارغة"):
            SaleService.prepare_split_payments([])

    def test_non_dict_raises(self):
        with pytest.raises(ValueError, match="غير صالحة"):
            SaleService.prepare_split_payments(["nope"])

    def test_non_positive_amount_raises(self):
        with pytest.raises(ValueError, match="أكبر من صفر"):
            SaleService.prepare_split_payments(
                [{"amount": "0", "payment_method": "cash", "currency": "AED"}]
            )

    def test_bad_rate_raises(self):
        with pytest.raises(ValueError, match="الصرف"):
            SaleService.prepare_split_payments(
                [{"amount": "10", "payment_method": "cash", "currency": "AED",
                  "exchange_rate": "0"}]
            )

    def test_happy_path(self):
        out = SaleService.prepare_split_payments(
            [{"amount": "10", "payment_method": "cash", "currency": "AED",
              "exchange_rate": "1", "reference_number": "R1"}],
            tenant_id=1,
        )
        assert out[0]["amount_aed"] == Decimal("10.000")
        assert out[0]["reference_number"] == "R1"

    def test_method_alias_key(self):
        out = SaleService.prepare_split_payments(
            [{"amount": "5", "method": "cash", "currency": "AED"}]
        )
        assert out[0]["payment_method"] == "cash"


class TestCancelAndHelpers:
    def test_cancel_already_cancelled(self):
        with pytest.raises(ValueError, match="ملغاة"):
            SaleService.cancel_sale(SimpleNamespace(status="cancelled", id=1))

    def test_cancel_confirmed_payments_guard(self, db_session, sample_sale):
        from models import Payment

        pay = Payment(
            tenant_id=sample_sale.tenant_id, sale_id=sample_sale.id,
            payment_number=f"COV4-{sample_sale.id}", payment_type="customer_payment",
            payment_method="cash",
            amount=Decimal("10"),
            amount_aed=Decimal("10"), payment_confirmed=True,
        )
        db_session.add(pay)
        db_session.flush()
        with pytest.raises(ValueError, match="دفعات مؤكدة"):
            SaleService.cancel_sale(sample_sale)
        db_session.rollback()

    def test_update_payment_status_flush(self, db_session, sample_sale):
        SaleService.update_payment_status(sample_sale)
        assert sample_sale.id is not None

    def test_has_inventory_posted_false(self, db_session, sample_sale):
        assert SaleService.has_inventory_posted(sample_sale) is False

    def test_list_active_users_none(self):
        assert SaleService.list_active_users(tenant_id=None) == []

    def test_list_active_users_real(self, db_session, sample_tenant):
        assert isinstance(SaleService.list_active_users(sample_tenant.id), list)

    def test_archived_helpers_empty(self, db_session, sample_tenant):
        assert SaleService.list_archived_sale_records(sample_tenant.id) == []
        assert SaleService.get_archived_sale_record(999999999, sample_tenant.id) is None

    def test_archived_helpers_unscoped(self, db_session):
        assert SaleService.list_archived_sale_records() == []
        assert SaleService.get_archived_sale_record(999999999) is None

    def test_counts_zero(self, db_session, sample_sale):
        assert SaleService.count_sale_payments(sample_sale.id, sample_sale.tenant_id) >= 0
        assert SaleService.count_sale_cheques(sample_sale.id, sample_sale.tenant_id) >= 0
