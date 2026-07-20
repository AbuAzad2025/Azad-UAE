"""Unit tests for models/pos_order_type.py — PosOrderType + default seeding."""

from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError


@pytest.fixture
def order_type(db_session, sample_tenant):
    from models.pos_order_type import PosOrderType

    ot = PosOrderType(
        tenant_id=sample_tenant.id,
        code="in_store",
        name_ar="في المتجر",
        name_en="In-store",
        sort_order=10,
        is_default=True,
    )
    db_session.add(ot)
    db_session.commit()
    return ot


class TestPosOrderTypeDefaults:
    def test_defaults_on_create(self, db_session, sample_tenant):
        from models.pos_order_type import PosOrderType

        ot = PosOrderType(tenant_id=sample_tenant.id, code="x1", name_ar="نوع")
        db_session.add(ot)
        db_session.commit()

        assert ot.is_active is True
        assert ot.sort_order == 0
        assert ot.is_default is False
        assert ot.kds_enabled is False
        assert ot.created_at is not None

    def test_display_name_prefers_arabic(self, order_type):
        assert order_type.display_name == "في المتجر"

    def test_display_name_falls_back_to_english(self, db_session, sample_tenant):
        from models.pos_order_type import PosOrderType

        ot = PosOrderType(tenant_id=sample_tenant.id, code="en_only", name_ar="", name_en="Pickup")
        assert ot.display_name == "Pickup"

    def test_display_name_falls_back_to_code(self, db_session, sample_tenant):
        from models.pos_order_type import PosOrderType

        ot = PosOrderType(tenant_id=sample_tenant.id, code="code_only", name_ar="", name_en=None)
        assert ot.display_name == "code_only"

    def test_to_dict_shape(self, order_type):
        d = order_type.to_dict()
        assert d["code"] == "in_store"
        assert d["display_name"] == "في المتجر"
        assert d["is_default"] is True
        assert set(d) == {
            "id",
            "code",
            "name_ar",
            "name_en",
            "display_name",
            "is_active",
            "sort_order",
            "is_default",
            "kds_enabled",
        }


class TestPosOrderTypeConstraints:
    def test_code_unique_per_tenant(self, db_session, sample_tenant, order_type):
        from models.pos_order_type import PosOrderType

        db_session.add(PosOrderType(tenant_id=sample_tenant.id, code="in_store", name_ar="نسخة"))
        with pytest.raises(IntegrityError):
            db_session.flush()
        db_session.rollback()

    def test_same_code_allowed_for_other_tenant(self, db_session, sample_tenant, order_type):
        from models import Tenant
        from models.pos_order_type import PosOrderType

        other = Tenant(
            name="Other Co OT",
            name_ar="أخرى",
            slug="other-co-ot",
            email="other-ot@example.com",
            country="AE",
            subscription_plan="basic",
        )
        db_session.add(other)
        db_session.flush()
        db_session.add(PosOrderType(tenant_id=other.id, code="in_store", name_ar="في المتجر"))
        db_session.commit()


class TestPosOrderTypeQueries:
    def test_for_tenant_active_only_and_ordering(self, db_session, sample_tenant):
        from models.pos_order_type import PosOrderType

        db_session.add_all(
            [
                PosOrderType(tenant_id=sample_tenant.id, code="b", name_ar="ب", sort_order=20),
                PosOrderType(tenant_id=sample_tenant.id, code="a", name_ar="أ", sort_order=10),
                PosOrderType(
                    tenant_id=sample_tenant.id,
                    code="off",
                    name_ar="م",
                    sort_order=5,
                    is_active=False,
                ),
            ]
        )
        db_session.commit()

        active = PosOrderType.for_tenant(sample_tenant.id)
        assert [ot.code for ot in active] == ["a", "b"]

        everything = PosOrderType.for_tenant(sample_tenant.id, active_only=False)
        assert [ot.code for ot in everything] == ["off", "a", "b"]

    def test_get_by_code(self, db_session, sample_tenant, order_type):
        from models.pos_order_type import PosOrderType

        assert PosOrderType.get_by_code(sample_tenant.id, "in_store") is order_type
        assert PosOrderType.get_by_code(sample_tenant.id, "missing") is None

    def test_get_by_code_active_only(self, db_session, sample_tenant):
        from models.pos_order_type import PosOrderType

        db_session.add(PosOrderType(tenant_id=sample_tenant.id, code="off", name_ar="م", is_active=False))
        db_session.commit()

        assert PosOrderType.get_by_code(sample_tenant.id, "off", active_only=True) is None
        assert PosOrderType.get_by_code(sample_tenant.id, "off") is not None

    def test_default_for_tenant_prefers_flagged(self, db_session, sample_tenant):
        from models.pos_order_type import PosOrderType

        db_session.add_all(
            [
                PosOrderType(tenant_id=sample_tenant.id, code="z", name_ar="ز", sort_order=1),
                PosOrderType(
                    tenant_id=sample_tenant.id,
                    code="flagged",
                    name_ar="م",
                    sort_order=99,
                    is_default=True,
                ),
            ]
        )
        db_session.commit()

        assert PosOrderType.default_for_tenant(sample_tenant.id).code == "flagged"

    def test_default_for_tenant_falls_back_to_first_active(self, db_session, sample_tenant):
        from models.pos_order_type import PosOrderType

        db_session.add_all(
            [
                PosOrderType(tenant_id=sample_tenant.id, code="b", name_ar="ب", sort_order=20),
                PosOrderType(tenant_id=sample_tenant.id, code="a", name_ar="أ", sort_order=10),
            ]
        )
        db_session.commit()

        assert PosOrderType.default_for_tenant(sample_tenant.id).code == "a"

    def test_default_for_tenant_none_when_empty(self, sample_tenant):
        from models.pos_order_type import PosOrderType

        assert PosOrderType.default_for_tenant(sample_tenant.id) is None


class TestDefaultSeedData:
    def test_seed_catalogue_integrity(self):
        from models.pos_order_type import DEFAULT_POS_ORDER_TYPES

        assert len(DEFAULT_POS_ORDER_TYPES) == 6
        codes = [row[0] for row in DEFAULT_POS_ORDER_TYPES]
        assert len(set(codes)) == len(codes)
        defaults = [row for row in DEFAULT_POS_ORDER_TYPES if row[3] is True]
        assert len(defaults) == 1
        assert defaults[0][0] == "in_store"
        for code, name_ar, name_en, _d, sort_order, kds in DEFAULT_POS_ORDER_TYPES:
            assert code and name_ar and name_en
            assert isinstance(sort_order, int)
            assert isinstance(kds, bool)

    def test_ensure_default_seeds_once(self, db_session, sample_tenant):
        from models.pos_order_type import PosOrderType, ensure_default_pos_order_types

        ensure_default_pos_order_types(sample_tenant.id)
        db_session.commit()
        first_count = PosOrderType.query.filter_by(tenant_id=sample_tenant.id).count()
        assert first_count == 6
        assert PosOrderType.default_for_tenant(sample_tenant.id).code == "in_store"

        # Idempotent: a second call seeds nothing more.
        ensure_default_pos_order_types(sample_tenant.id)
        db_session.commit()
        assert PosOrderType.query.filter_by(tenant_id=sample_tenant.id).count() == first_count

    def test_ensure_default_skips_configured_tenant(self, db_session, order_type):
        from models.pos_order_type import PosOrderType, ensure_default_pos_order_types

        ensure_default_pos_order_types(order_type.tenant_id)
        db_session.commit()
        assert PosOrderType.query.filter_by(tenant_id=order_type.tenant_id).count() == 1
