"""Gap coverage for models/supplier.py — balances, stats, display helpers."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from models.supplier import Supplier


def _supplier(**kwargs):
    params = {"tenant_id": 1, "name": "Cov Supplier"}
    params.update(kwargs)
    return Supplier(**params)


class TestBalanceAliases:
    def test_balance_with_nones(self):
        sup = _supplier()
        sup.total_purchases_aed = None
        sup.total_paid_aed = None
        assert sup.get_balance_base() == Decimal("0")
        assert sup.get_balance_aed() == Decimal("0")

    def test_balance_math(self):
        sup = _supplier(total_purchases_aed=Decimal("500"), total_paid_aed=Decimal("200"))
        assert sup.get_balance_base() == Decimal("300")

    def test_purchases_base_alias(self):
        sup = _supplier()
        sup.total_purchases_base = Decimal("11")
        assert sup.total_purchases_aed == Decimal("11")

    def test_paid_base_alias(self):
        sup = _supplier()
        sup.total_paid_base = Decimal("6")
        assert sup.total_paid_aed == Decimal("6")

    def test_apply_with_none(self):
        sup = _supplier()
        sup.total_purchases_aed = None
        sup.total_paid_aed = None
        sup.apply_purchase(None)
        sup.apply_payment(None)
        assert sup.total_purchases_aed == Decimal("0")
        assert sup.total_paid_aed == Decimal("0")

    def test_apply_base_delegates(self):
        sup = _supplier(total_purchases_aed=Decimal("10"), total_paid_aed=Decimal("3"))
        sup.apply_purchase_base(Decimal("5"))
        sup.apply_payment_base(Decimal("1"))
        assert sup.total_purchases_aed == Decimal("15")
        assert sup.total_paid_aed == Decimal("4")


class TestDisplay:
    def test_display_name_en(self):
        assert _supplier(name="عربي", name_en="English").get_display_name("en") == "English"

    def test_display_name_en_fallback(self):
        assert _supplier(name="عربي", name_en=None).get_display_name("en") == "عربي"

    def test_display_name_ar(self):
        assert _supplier(name="عربي").get_display_name("ar") == "عربي"

    def test_type_display_known(self):
        assert _supplier(supplier_type="parts").get_type_display() == "قطع غيار"

    def test_type_display_unknown(self):
        assert _supplier(supplier_type="mystery").get_type_display() == "mystery"

    def test_rating_stars(self):
        assert _supplier(rating=3).get_rating_stars() == "⭐" * 3

    def test_rating_stars_empty(self):
        assert _supplier(rating=0).get_rating_stars() == "☆☆☆☆☆"
        sup = _supplier()
        sup.rating = None
        assert sup.get_rating_stars() == "☆☆☆☆☆"


class TestUpdateStatistics:
    def _purchase(self, db_session, supplier, number, status, amount):
        from models.purchase import Purchase

        pur = Purchase(
            tenant_id=supplier.tenant_id,
            purchase_number=number,
            supplier_id=supplier.id,
            supplier_name=supplier.name,
            total_amount=Decimal(str(amount)),
            amount=Decimal(str(amount)),
            amount_aed=Decimal(str(amount)),
            user_id=1,
            status=status,
            purchase_date=datetime.now(UTC),
        )
        db_session.add(pur)
        db_session.flush()
        return pur

    def _payment(self, db_session, supplier, number, **kwargs):
        from models.payment import Payment

        params = {
            "tenant_id": supplier.tenant_id,
            "payment_number": number,
            "payment_type": "supplier_payment",
            "direction": "outgoing",
            "supplier_id": supplier.id,
            "amount": Decimal("50"),
            "amount_aed": Decimal("50"),
            "payment_method": "cash",
            "payment_confirmed": True,
            "payment_date": datetime.now(UTC),
        }
        params.update(kwargs)
        pay = Payment(**params)
        db_session.add(pay)
        db_session.flush()
        return pay

    def test_stats_counts_only_confirmed(self, db_session, sample_tenant):
        sup = Supplier(tenant_id=sample_tenant.id, name="Stats Supplier")
        db_session.add(sup)
        db_session.flush()
        self._purchase(db_session, sup, "SUP-P1", "confirmed", "200")
        self._purchase(db_session, sup, "SUP-P2", "draft", "999")
        self._payment(db_session, sup, "SUP-PAY1")
        sup.update_statistics()
        assert sup.total_purchases_aed == Decimal("200")
        assert sup.total_paid_aed == Decimal("50")
        assert sup.last_purchase_date is not None

    def test_pending_cheque_counts_bounced_excluded(self, db_session, sample_tenant):
        sup = Supplier(tenant_id=sample_tenant.id, name="Cheque Supplier")
        db_session.add(sup)
        db_session.flush()
        self._purchase(db_session, sup, "SUP-C1", "confirmed", "100")
        self._payment(
            db_session,
            sup,
            "SUP-CP1",
            payment_confirmed=False,
            payment_method="cheque",
            rejection_reason=None,
            amount_aed=Decimal("30"),
            amount=Decimal("30"),
        )
        self._payment(
            db_session,
            sup,
            "SUP-CP2",
            payment_confirmed=False,
            payment_method="cheque",
            rejection_reason="bounced",
            amount_aed=Decimal("70"),
            amount=Decimal("70"),
        )
        sup.update_statistics()
        assert sup.total_paid_aed == Decimal("30")

    def test_no_purchases(self, db_session, sample_tenant):
        sup = Supplier(tenant_id=sample_tenant.id, name="Empty Supplier")
        db_session.add(sup)
        db_session.flush()
        sup.update_statistics()
        assert sup.total_purchases_aed == Decimal("0")
        assert sup.total_paid_aed == Decimal("0")


class TestToDict:
    def test_keys(self):
        sup = _supplier(
            name_en="EN",
            supplier_type="parts",
            total_purchases_aed=Decimal("100"),
            total_paid_aed=Decimal("40"),
            rating=4,
        )
        data = sup.to_dict()
        assert data["balance_aed"] == 60.0
        assert data["rating_stars"] == "⭐" * 4
        assert data["type_display"] == "قطع غيار"

    def test_repr(self):
        assert "Cov Supplier" in repr(_supplier())
