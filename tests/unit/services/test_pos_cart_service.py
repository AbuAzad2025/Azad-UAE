"""PosCartService — server-side parked carts with real db_session.

Covers park/list/resume/delete, tenant isolation, user scoping,
double-resume prevention, and payload hygiene.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest

from models import PosCart, PosSession
from services.pos_cart_service import PosCartConflictError, PosCartService


def _lines(*rows):
    return [
        {"product_id": pid, "quantity": qty, "unit_price": price, "discount_percent": disc}
        for pid, qty, price, disc in rows
    ]


def _payload(**over):
    base = {
        "lines": _lines((1, "2", "25", "0"), (2, "1", "10", "10")),
        "customer_id": 7,
        "warehouse_id": 3,
        "currency": "aed",
        "order_type": "in_store",
        "notes": "hold for customer",
        "internal_debug_blob": "x" * 100,  # must be dropped by the whitelist
    }
    base.update(over)
    return base


@pytest.fixture
def pos_session(db_session, sample_tenant, sample_branch, sample_user):
    session = PosSession(
        tenant_id=sample_tenant.id,
        branch_id=sample_branch.id,
        user_id=sample_user.id,
        session_number=f"POS-SES-{uuid.uuid4().hex[:8]}",
        opening_balance_cash=Decimal("0"),
        status="open",
    )
    db_session.add(session)
    db_session.flush()
    return session


@pytest.fixture
def other_user(db_session):
    """A cashier in a completely different tenant (cross-tenant probe)."""
    from models import Branch, Role, Tenant, User

    unique = uuid.uuid4().hex[:8]
    tenant = Tenant(
        name=f"Other Co {unique}",
        name_ar="شركة أخرى",
        slug=f"other-co-{unique}",
        email=f"other-{unique}@example.com",
        phone_1="0500000000",
        country="AE",
        subscription_plan="basic",
        default_currency="AED",
        base_currency="AED",
        is_active=True,
    )
    db_session.add(tenant)
    db_session.flush()
    role = db_session.query(Role).filter_by(slug="super_admin").first()
    branch = Branch(
        tenant_id=tenant.id,
        name=f"Other Branch {unique[:4]}",
        code=f"OB{unique[:4].upper()}",
        is_active=True,
        is_main=True,
    )
    db_session.add(branch)
    db_session.flush()
    user = User(
        username=f"other-{unique}",
        email=f"other-{unique}@example.com",
        full_name="Other User",
        tenant_id=tenant.id,
        role_id=role.id if role else None,
        branch_id=branch.id,
    )
    user.set_password("password123")
    db_session.add(user)
    db_session.flush()
    return user


class TestParkCart:
    def test_park_creates_cart_with_summary(self, db_session, sample_user, pos_session):
        cart = PosCartService.park_cart(user=sample_user, session=pos_session, payload=_payload(), label="طاولة ٥")
        assert cart.id is not None
        assert cart.status == PosCart.STATUS_PARKED
        assert cart.tenant_id == sample_user.tenant_id
        assert cart.user_id == sample_user.id
        assert cart.session_id == pos_session.id
        assert cart.label == "طاولة ٥"
        assert cart.item_count == 2
        # 2*25 + 1*10*0.9 = 59.000
        assert Decimal(str(cart.total_estimate)) == Decimal("59.000")
        assert cart.currency == "AED"

    def test_park_sanitizes_payload_to_whitelist(self, db_session, sample_user, pos_session):
        cart = PosCartService.park_cart(user=sample_user, session=pos_session, payload=_payload())
        assert "internal_debug_blob" not in cart.payload
        assert cart.payload["currency"] == "aed"  # payload kept verbatim, summary upper-cased
        assert len(cart.payload["lines"]) == 2

    def test_park_requires_lines(self, db_session, sample_user, pos_session):
        with pytest.raises(ValueError, match="فارغة"):
            PosCartService.park_cart(user=sample_user, session=pos_session, payload={"lines": []})

    def test_park_rejects_non_dict_payload(self, db_session, sample_user, pos_session):
        with pytest.raises(ValueError, match="غير صالحة"):
            PosCartService.park_cart(user=sample_user, session=pos_session, payload="not-a-dict")

    def test_park_rejects_non_positive_quantity(self, db_session, sample_user, pos_session):
        payload = _payload(lines=[{"product_id": 1, "quantity": "0", "unit_price": "5"}])
        with pytest.raises(ValueError, match="أكبر من صفر"):
            PosCartService.park_cart(user=sample_user, session=pos_session, payload=payload)

    def test_park_without_session_raises(self, sample_user):
        with pytest.raises(ValueError, match="جلسة"):
            PosCartService.park_cart(user=sample_user, session=None, payload=_payload())

    def test_park_update_replaces_payload_and_reparks(self, db_session, sample_user, pos_session):
        cart = PosCartService.park_cart(user=sample_user, session=pos_session, payload=_payload())
        PosCartService.resume_cart(user=sample_user, cart_id=cart.id)
        assert cart.status == PosCart.STATUS_RESUMED

        updated = PosCartService.park_cart(
            user=sample_user,
            session=pos_session,
            payload=_payload(lines=[{"product_id": 9, "quantity": "3", "unit_price": "4"}]),
            cart_id=cart.id,
            label="محدّثة",
        )
        assert updated.id == cart.id
        assert updated.status == PosCart.STATUS_PARKED
        assert updated.resumed_at is None
        assert updated.item_count == 1
        assert Decimal(str(updated.total_estimate)) == Decimal("12.000")
        assert updated.label == "محدّثة"

    def test_park_update_missing_cart_raises(self, db_session, sample_user, pos_session):
        with pytest.raises(LookupError):
            PosCartService.park_cart(user=sample_user, session=pos_session, payload=_payload(), cart_id=999999)

    def test_park_cap_per_session(self, db_session, sample_user, pos_session, monkeypatch):
        monkeypatch.setattr(PosCartService, "MAX_CARTS_PER_SESSION", 2)
        PosCartService.park_cart(user=sample_user, session=pos_session, payload=_payload())
        PosCartService.park_cart(user=sample_user, session=pos_session, payload=_payload())
        with pytest.raises(ValueError, match="الأقصى"):
            PosCartService.park_cart(user=sample_user, session=pos_session, payload=_payload())

    def test_park_rejects_oversized_payload(self, db_session, sample_user, pos_session):
        payload = _payload(notes="x" * (PosCartService.MAX_PAYLOAD_BYTES + 10))
        with pytest.raises(ValueError, match="كبير"):
            PosCartService.park_cart(user=sample_user, session=pos_session, payload=payload)


class TestListCarts:
    def test_list_returns_parked_summaries_only(self, db_session, sample_user, pos_session):
        PosCartService.park_cart(user=sample_user, session=pos_session, payload=_payload(), label="أ")
        carts = PosCartService.list_carts(user=sample_user, session=pos_session)
        assert len(carts) == 1
        summary = carts[0].to_summary_dict()
        assert "payload" not in summary
        assert summary["label"] == "أ"
        assert summary["item_count"] == 2
        assert summary["total_estimate"] == 59.0

    def test_list_excludes_resumed_carts(self, db_session, sample_user, pos_session):
        cart = PosCartService.park_cart(user=sample_user, session=pos_session, payload=_payload())
        PosCartService.resume_cart(user=sample_user, cart_id=cart.id)
        assert PosCartService.list_carts(user=sample_user, session=pos_session) == []

    def test_list_empty_without_session(self, sample_user):
        assert PosCartService.list_carts(user=sample_user, session=None) == []

    def test_list_scoped_to_user(self, db_session, sample_user, other_user, pos_session):
        PosCartService.park_cart(user=sample_user, session=pos_session, payload=_payload())
        assert PosCartService.list_carts(user=other_user, session=pos_session) == []

    def test_list_respects_limit_cap(self, db_session, sample_user, pos_session):
        for _ in range(3):
            PosCartService.park_cart(user=sample_user, session=pos_session, payload=_payload())
        carts = PosCartService.list_carts(user=sample_user, session=pos_session, limit=2)
        assert len(carts) == 2


class TestResumeCart:
    def test_resume_returns_full_payload(self, db_session, sample_user, pos_session):
        cart = PosCartService.park_cart(user=sample_user, session=pos_session, payload=_payload())
        resumed = PosCartService.resume_cart(user=sample_user, cart_id=cart.id)
        assert resumed.status == PosCart.STATUS_RESUMED
        assert resumed.resumed_at is not None
        detail = resumed.to_detail_dict()
        assert detail["payload"]["lines"][0]["product_id"] == 1

    def test_double_resume_blocked(self, db_session, sample_user, pos_session):
        cart = PosCartService.park_cart(user=sample_user, session=pos_session, payload=_payload())
        PosCartService.resume_cart(user=sample_user, cart_id=cart.id)
        with pytest.raises(PosCartConflictError, match="مسبقاً"):
            PosCartService.resume_cart(user=sample_user, cart_id=cart.id)

    def test_resume_cross_user_not_found(self, db_session, sample_user, other_user, pos_session):
        cart = PosCartService.park_cart(user=sample_user, session=pos_session, payload=_payload())
        with pytest.raises(LookupError):
            PosCartService.resume_cart(user=other_user, cart_id=cart.id)

    def test_resume_cross_tenant_not_found(self, db_session, sample_user, other_user, pos_session):
        """A cart parked by tenant A's cashier is invisible to tenant B's cashier."""
        cart = PosCartService.park_cart(user=sample_user, session=pos_session, payload=_payload())
        assert cart.tenant_id != other_user.tenant_id
        with pytest.raises(LookupError):
            PosCartService.resume_cart(user=other_user, cart_id=cart.id)
        # The cart itself remains parked for the real owner.
        assert db_session.get(PosCart, cart.id).status == PosCart.STATUS_PARKED


class TestDeleteCart:
    def test_delete_removes_cart(self, db_session, sample_user, pos_session):
        cart = PosCartService.park_cart(user=sample_user, session=pos_session, payload=_payload())
        PosCartService.delete_cart(user=sample_user, cart_id=cart.id)
        assert db_session.get(PosCart, cart.id) is None

    def test_delete_missing_raises(self, sample_user):
        with pytest.raises(LookupError):
            PosCartService.delete_cart(user=sample_user, cart_id=999999)

    def test_delete_cross_tenant_blocked(self, db_session, sample_user, other_user, pos_session):
        cart = PosCartService.park_cart(user=sample_user, session=pos_session, payload=_payload())
        with pytest.raises(LookupError):
            PosCartService.delete_cart(user=other_user, cart_id=cart.id)
        assert db_session.get(PosCart, cart.id) is not None
