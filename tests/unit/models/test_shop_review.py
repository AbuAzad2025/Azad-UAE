"""Unit tests for models/shop_review.py — ShopReview storefront reviews."""

from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError


@pytest.fixture
def review(db_session, sample_tenant, sample_product):
    from models.shop_review import ShopReview

    r = ShopReview(
        tenant_id=sample_tenant.id,
        product_id=sample_product.id,
        customer_name="Reviewer One",
        rating=5,
        comment="ممتاز",
    )
    db_session.add(r)
    db_session.commit()
    return r


class TestShopReviewDefaults:
    def test_defaults_on_create(self, review):
        assert review.id is not None
        assert review.is_approved is False
        assert review.created_at is not None
        assert review.account_id is None

    def test_comment_optional(self, db_session, sample_tenant, sample_product):
        from models.shop_review import ShopReview

        r = ShopReview(
            tenant_id=sample_tenant.id,
            product_id=sample_product.id,
            customer_name="No Comment",
            rating=3,
        )
        db_session.add(r)
        db_session.commit()
        assert r.comment is None


class TestShopReviewConstraints:
    def test_rating_required(self, db_session, sample_tenant, sample_product):
        from models.shop_review import ShopReview

        db_session.add(
            ShopReview(
                tenant_id=sample_tenant.id,
                product_id=sample_product.id,
                customer_name="X",
                rating=None,
            )
        )
        with pytest.raises(IntegrityError):
            db_session.flush()
        db_session.rollback()

    def test_customer_name_required(self, db_session, sample_tenant, sample_product):
        from models.shop_review import ShopReview

        db_session.add(
            ShopReview(
                tenant_id=sample_tenant.id,
                product_id=sample_product.id,
                customer_name=None,
                rating=4,
            )
        )
        with pytest.raises(IntegrityError):
            db_session.flush()
        db_session.rollback()


class TestShopReviewRelationships:
    def test_product_relationship(self, review, sample_product):
        assert review.product is not None
        assert review.product.id == sample_product.id

    def test_product_backref_dynamic(self, review, sample_product):
        backref = sample_product.shop_reviews
        assert backref.count() >= 1
        assert any(r.id == review.id for r in backref.all())

    def test_approval_flow_persists(self, db_session, review):
        review.is_approved = True
        db_session.commit()
        db_session.expire_all()

        refreshed = type(review).query.get(review.id)
        assert refreshed.is_approved is True
