"""PosSessionService — real-DB behavioral coverage.

update_session_totals mirrors the checkout bookkeeping contract:
* ``sale.total_amount`` always lands in ``total_sales``;
* a legacy single ``payment_data`` cash tender lands in ``total_cash_sales``
  (converted to AED) but not double-counted into ``total_sales``;
* split ``payments_data`` chunks land in their tender bucket AND
  ``total_sales`` (each chunk is real money accepted beyond the sale line).
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest

from models import PosSession, PosShift


@pytest.fixture
def pos_session(db_session, sample_tenant, sample_branch, sample_user):
    session = PosSession(
        tenant_id=sample_tenant.id,
        branch_id=sample_branch.id,
        user_id=sample_user.id,
        session_number=f"POS-SES-{uuid.uuid4().hex[:8]}",
        opening_balance_cash=Decimal("100.000"),
        status="open",
    )
    db_session.add(session)
    db_session.flush()
    return session


@pytest.fixture
def sale(db_session, sample_sale):
    """Re-use the shared sale fixture; totals are what matter here."""
    return sample_sale


class TestUpdateSessionTotals:
    def test_cash_payment_updates_sales_and_cash_bucket(
        self, db_session, sample_tenant, pos_session, sale
    ):
        from services.pos_session_service import PosSessionService

        PosSessionService.update_session_totals(
            pos_session,
            sale,
            payment_data={"payment_method": "cash", "amount": "150.555"},
            tenant_id=sample_tenant.id,
        )
        db_session.flush()

        assert Decimal(str(pos_session.total_sales)) == Decimal("210.000")
        assert Decimal(str(pos_session.total_cash_sales)) == Decimal("150.555")
        assert Decimal(str(pos_session.total_card_sales)) == Decimal("0")

    def test_non_cash_payment_data_leaves_cash_bucket_untouched(
        self, db_session, sample_tenant, pos_session, sale
    ):
        from services.pos_session_service import PosSessionService

        PosSessionService.update_session_totals(
            pos_session,
            sale,
            payment_data={"payment_method": "card", "amount": "210.000"},
            tenant_id=sample_tenant.id,
        )
        db_session.flush()

        assert Decimal(str(pos_session.total_sales)) == Decimal("210.000")
        assert Decimal(str(pos_session.total_cash_sales)) == Decimal("0")

    def test_no_payment_data_still_records_sale_total(self, db_session, sample_tenant, pos_session, sale):
        from services.pos_session_service import PosSessionService

        PosSessionService.update_session_totals(pos_session, sale, tenant_id=sample_tenant.id)
        db_session.flush()

        assert Decimal(str(pos_session.total_sales)) == Decimal("210.000")
        assert Decimal(str(pos_session.total_cash_sales)) == Decimal("0")

    def test_split_tenders_land_in_buckets_and_total_sales(
        self, db_session, sample_tenant, pos_session, sale
    ):
        from services.pos_session_service import PosSessionService

        PosSessionService.update_session_totals(
            pos_session,
            sale,
            payments_data=[
                {"payment_method": "cash", "amount": "50.000", "currency": "AED"},
                {"payment_method": "card", "amount": "20.000", "currency": "AED"},
            ],
            tenant_id=sample_tenant.id,
        )
        db_session.flush()

        # 210 (sale) + 50 (cash chunk) + 20 (card chunk)
        assert Decimal(str(pos_session.total_sales)) == Decimal("280.000")
        assert Decimal(str(pos_session.total_cash_sales)) == Decimal("50.000")
        assert Decimal(str(pos_session.total_card_sales)) == Decimal("20.000")

    def test_foreign_currency_tender_is_converted_to_aed(
        self, db_session, sample_tenant, pos_session, sale
    ):
        from services.pos_session_service import PosSessionService

        PosSessionService.update_session_totals(
            pos_session,
            sale,
            payment_data={"payment_method": "cash", "amount": "100.000"},
            payment_currency="SAR",
            payment_exchange_rate="0.5",
            tenant_id=sample_tenant.id,
        )
        db_session.flush()
        assert Decimal(str(pos_session.total_cash_sales)) == Decimal("50.000")

    def test_accumulates_onto_existing_totals_and_none_safe_defaults(
        self, db_session, sample_tenant, pos_session, sale
    ):
        from services.pos_session_service import PosSessionService

        pos_session.total_sales = None
        pos_session.total_cash_sales = None
        PosSessionService.update_session_totals(
            pos_session,
            sale,
            payment_data={"payment_method": "cash", "amount": "10.000"},
            tenant_id=sample_tenant.id,
        )
        PosSessionService.update_session_totals(
            pos_session,
            sale,
            payment_data={"payment_method": "cash", "amount": "5.500"},
            tenant_id=sample_tenant.id,
        )
        db_session.flush()

        assert Decimal(str(pos_session.total_sales)) == Decimal("420.000")
        assert Decimal(str(pos_session.total_cash_sales)) == Decimal("15.500")

    def test_unknown_tender_method_only_counts_into_total_sales(
        self, db_session, sample_tenant, pos_session, sale
    ):
        from services.pos_session_service import PosSessionService

        PosSessionService.update_session_totals(
            pos_session,
            sale,
            payments_data=[{"payment_method": "store_credit", "amount": "30.000", "currency": "AED"}],
            tenant_id=sample_tenant.id,
        )
        db_session.flush()

        assert Decimal(str(pos_session.total_sales)) == Decimal("240.000")
        assert Decimal(str(pos_session.total_cash_sales)) == Decimal("0")
        assert Decimal(str(pos_session.total_card_sales)) == Decimal("0")


class TestCreateShift:
    def test_create_shift_persists_open_shift_with_starting_cash(
        self, db_session, sample_tenant, sample_user, pos_session
    ):
        from services.pos_session_service import PosSessionService

        shift = PosSessionService.create_shift(
            tenant_id=sample_tenant.id,
            user_id=sample_user.id,
            starting_cash=Decimal("250.000"),
        )
        # The route assigns identity fields before flushing (shift has no
        # number/branch columns of its own) — mirror that contract here.
        shift.session_id = pos_session.id
        shift.shift_number = f"SHF-{uuid.uuid4().hex[:8]}"
        db_session.add(shift)
        db_session.flush()

        stored = db_session.get(PosShift, shift.id)
        assert stored is not None
        assert stored.tenant_id == sample_tenant.id
        assert stored.user_id == sample_user.id
        assert stored.session_id == pos_session.id
        assert stored.status == PosShift.SHIFT_OPEN
        assert Decimal(str(stored.starting_cash)) == Decimal("250.000")
        assert stored.closed_at is None
        # Branch is derived through the parent session.
        assert stored.branch_id == pos_session.branch_id

    def test_create_shift_defaults_starting_cash_to_zero(
        self, db_session, sample_tenant, sample_user, pos_session
    ):
        from services.pos_session_service import PosSessionService

        shift = PosSessionService.create_shift(tenant_id=sample_tenant.id, user_id=sample_user.id)
        shift.session_id = pos_session.id
        shift.shift_number = f"SHF-{uuid.uuid4().hex[:8]}"
        db_session.add(shift)
        db_session.flush()

        assert Decimal(str(shift.starting_cash)) == Decimal("0")
