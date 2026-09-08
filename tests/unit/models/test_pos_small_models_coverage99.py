"""Coverage-99% boost for small models with isolated branch misses:

- models/shipment.py             (L76, 79, 81, 87 = validator raises)
- models/pos_override_token.py   (L47, 51 = naive datetime + repr)
- models/pos_shift.py            (L89, 92-93, 100, 102 = notes, close, naive dts)
- models/pos_printer.py          (L63, 65, 69 = for_tenant filters, to_dict)
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from models.pos_override_token import PosOverrideToken
from models.pos_printer import PosPrinter
from models.pos_shift import PosShift
from models.shipment import Shipment

# ---------------------------------------------------------------------------
# Shipment
# ---------------------------------------------------------------------------


class TestShipmentValidators:
    def test_both_explicit_fks_raises(self):
        s = Shipment()
        # Build state directly using setattr so validators fire one at a
        # time; the second FK raises, exercising L76.
        s.sale_id = 11
        with pytest.raises(ValueError, match="exactly one explicit FK"):
            s.purchase_return_id = 22

    def test_wrong_source_type_raises(self):
        s = Shipment(source_type="purchase_return")
        with pytest.raises(ValueError, match="requires source_type='sale'"):
            s._validate_exactly_one_explicit("sale_id", 11)

    def test_source_id_mismatch_raises(self):
        s = Shipment(source_type="sale", source_id=99)
        with pytest.raises(ValueError, match="must match source_id"):
            s._validate_exactly_one_explicit("sale_id", 11)

    def test_invalid_source_type_raises(self):
        s = Shipment()
        with pytest.raises(ValueError, match="Invalid source_type"):
            s._validate_source_type("source_type", "warehouse")

    def test_happy_path_passes(self):
        s = Shipment(source_type="sale")
        assert s._validate_source_type("source_type", "sale") == "sale"
        assert s._validate_exactly_one_explicit("sale_id", 5) == 5


# ---------------------------------------------------------------------------
# PosOverrideToken
# ---------------------------------------------------------------------------


class TestPosOverrideToken:
    def test_naive_datetime_is_treated_as_utc(self):
        naive_expires = datetime.now(UTC).replace(tzinfo=None) - timedelta(seconds=10)
        tok = PosOverrideToken(
            tenant_id=1,
            action="open_drawer",
            cashier_user_id=2,
            supervisor_user_id=3,
            session_id=4,
            nonce="n1",
            expires_at=naive_expires,
        )
        assert tok.is_expired() is True

    def test_future_datetime_not_expired(self):
        future = datetime.now(UTC) + timedelta(hours=1)
        tok = PosOverrideToken(
            tenant_id=1,
            action="x",
            cashier_user_id=2,
            supervisor_user_id=3,
            nonce="n2",
            expires_at=future,
        )
        assert tok.is_expired() is False

    def test_repr_contains_action_and_ids(self):
        tok = PosOverrideToken(
            tenant_id=1,
            action="discount_override",
            cashier_user_id=4,
            supervisor_user_id=7,
            nonce="n3",
            expires_at=datetime.now(UTC) + timedelta(seconds=30),
        )
        s = repr(tok)
        assert "discount_override" in s
        assert "cashier=4" in s
        assert "by=7" in s


# ---------------------------------------------------------------------------
# PosShift
# ---------------------------------------------------------------------------


class TestPosShiftMethods:
    def _shift(self, **kwargs):
        defaults = dict(
            tenant_id=1,
            session_id=1,
            user_id=1,
            shift_number="S1",
            starting_cash="100.000",
            total_cash_sales="250.000",
            total_change_given="10.000",
            total_cash_refunds="0.000",
            total_pay_ins="0.000",
            total_pay_outs="0.000",
            opened_at=datetime.now(UTC),
        )
        defaults.update(kwargs)
        return PosShift(**defaults)

    def test_reconcile_with_notes(self):
        from decimal import Decimal

        s = self._shift()
        s.reconcile(Decimal("340.000"), notes="end of day")
        assert s.notes == "end of day"
        assert s.status == PosShift.SHIFT_RECONCILED
        assert s.discrepancy == Decimal("0.000")

    def test_reconcile_without_notes_keeps_none(self):
        from decimal import Decimal

        s = self._shift()
        s.reconcile(Decimal("340.000"))
        assert s.notes is None

    def test_close_sets_status_and_timestamp(self):
        s = self._shift()
        assert s.closed_at is None
        s.close()
        assert s.status == PosShift.SHIFT_CLOSED
        assert s.closed_at is not None
        assert s.closed_at.tzinfo is not None

    def test_duration_minutes_naive_datetimes(self):
        naive_start = datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=1)
        naive_end = datetime.now(UTC).replace(tzinfo=None)
        s = self._shift(opened_at=naive_start, closed_at=naive_end)
        duration = s.duration_minutes
        assert isinstance(duration, int)
        assert 58 <= duration <= 61

    def test_duration_minutes_when_still_open(self):
        s = self._shift(opened_at=datetime.now(UTC) - timedelta(minutes=20))
        assert isinstance(s.duration_minutes, int)
        assert s.duration_minutes >= 19


# ---------------------------------------------------------------------------
# PosPrinter
# ---------------------------------------------------------------------------


class TestPosPrinterClassMethod:
    def test_for_tenant_filters_inactive(self, db_session, sample_tenant):
        active = PosPrinter(tenant_id=sample_tenant.id, name="active", role="customer", is_active=True)
        inactive = PosPrinter(tenant_id=sample_tenant.id, name="inactive", role="customer", is_active=False)
        db_session.add_all([active, inactive])
        db_session.flush()
        result = PosPrinter.for_tenant(sample_tenant.id, active_only=True)
        names = [p.name for p in result]
        assert "active" in names
        assert "inactive" not in names

    def test_for_tenant_filters_by_role(self, db_session, sample_tenant):
        cust = PosPrinter(tenant_id=sample_tenant.id, name="C", role="customer", is_active=True)
        kitch = PosPrinter(tenant_id=sample_tenant.id, name="K", role="kitchen", is_active=True)
        db_session.add_all([cust, kitch])
        db_session.flush()
        result = PosPrinter.for_tenant(sample_tenant.id, role="kitchen", active_only=True)
        names = [p.name for p in result]
        assert names == ["K"]

    def test_to_dict_has_all_keys(self):
        p = PosPrinter(
            tenant_id=1,
            name="Front",
            role="customer",
            connection_type="agent_network",
            host="127.0.0.1",
            port=9100,
            encoding="cp864",
            category_ids=[1, 2],
            is_active=True,
            sort_order=5,
        )
        d = p.to_dict()
        for key in (
            "id",
            "name",
            "role",
            "connection_type",
            "host",
            "port",
            "serial_port",
            "baud_rate",
            "encoding",
            "category_ids",
            "is_active",
            "sort_order",
        ):
            assert key in d
        assert d["category_ids"] == [1, 2]
        assert d["is_active"] is True
