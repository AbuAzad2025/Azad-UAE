"""Gap coverage for models/pos_cart.py — summary/detail dict branches."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from models.pos_cart import PosCart


def _cart(**kwargs):
    params = {
        "tenant_id": 1,
        "session_id": 1,
        "user_id": 1,
        "payload": {"lines": []},
    }
    params.update(kwargs)
    return PosCart(**params)


class TestPosCartDicts:
    def test_summary_all_none(self):
        cart = _cart(label=None, item_count=None, total_estimate=None, currency=None)
        cart.parked_at = None
        cart.resumed_at = None
        cart.updated_at = None
        data = cart.to_summary_dict()
        assert data["label"] == ""
        assert data["item_count"] == 0
        assert data["total_estimate"] == 0
        assert data["currency"] is None
        assert data["parked_at"] is None
        assert data["resumed_at"] is None
        assert data["updated_at"] is None
        assert "payload" not in data

    def test_summary_with_values(self):
        now = datetime.now(UTC)
        cart = _cart(
            label="Hold 1",
            status="parked",
            item_count=3,
            total_estimate=Decimal("45.500"),
            currency="AED",
        )
        cart.id = 7
        cart.parked_at = now
        cart.resumed_at = now
        cart.updated_at = now
        data = cart.to_summary_dict()
        assert data["id"] == 7
        assert data["label"] == "Hold 1"
        assert data["item_count"] == 3
        assert data["total_estimate"] == float(Decimal("45.500"))
        assert data["parked_at"] == now.isoformat()

    def test_detail_includes_payload(self):
        cart = _cart(status="parked", payload={"lines": [{"sku": "A"}], "customer_id": 5})
        data = cart.to_detail_dict()
        assert data["payload"] == {"lines": [{"sku": "A"}], "customer_id": 5}
        assert data["status"] == "parked"

    def test_repr(self):
        cart = _cart(status="parked")
        cart.id = 3
        assert "3" in repr(cart)
        assert "parked" in repr(cart)

    def test_status_constants(self):
        assert PosCart.STATUS_PARKED == "parked"
        assert PosCart.STATUS_RESUMED == "resumed"
        assert PosCart.STATUS_EXPIRED == "expired"
        assert set(PosCart.STATUSES) == {"parked", "resumed", "expired"}

    def test_persist_roundtrip(self, db_session, sample_tenant, sample_user, sample_branch):
        from models.pos_session import PosSession

        session = PosSession(
            tenant_id=sample_tenant.id,
            branch_id=sample_branch.id,
            user_id=sample_user.id,
            session_number="CART-COV3-1",
        )
        db_session.add(session)
        db_session.flush()
        cart = PosCart(
            tenant_id=sample_tenant.id,
            session_id=session.id,
            user_id=sample_user.id,
            label="Counter 2",
            payload={"lines": [], "currency": "AED"},
            item_count=0,
            total_estimate=Decimal("0"),
            currency="AED",
        )
        db_session.add(cart)
        db_session.flush()
        fetched = db_session.get(PosCart, cart.id)
        assert fetched.to_detail_dict()["payload"] == {"lines": [], "currency": "AED"}
        assert fetched.to_summary_dict()["label"] == "Counter 2"
