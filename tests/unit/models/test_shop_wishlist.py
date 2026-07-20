"""Unit tests for models/shop_wishlist.py — ShopWishlist storefront wishlists."""

from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError


@pytest.fixture
def shop_account(db_session, sample_tenant, sample_customer):
    from models.shop_customer_account import ShopCustomerAccount

    account = ShopCustomerAccount(
        tenant_id=sample_tenant.id,
        customer_id=sample_customer.id,
        email="shopper@example.com",
        name="Shopper One",
    )
    account.set_password("secret123")
    db_session.add(account)
    db_session.commit()
    return account


@pytest.fixture
def wishlist_item(db_session, sample_tenant, sample_product, shop_account):
    from models.shop_wishlist import ShopWishlist

    item = ShopWishlist(
        tenant_id=sample_tenant.id,
        account_id=shop_account.id,
        product_id=sample_product.id,
    )
    db_session.add(item)
    db_session.commit()
    return item


class TestShopWishlistDefaults:
    def test_create_with_defaults(self, wishlist_item):
        assert wishlist_item.id is not None
        assert wishlist_item.created_at is not None

    def test_account_relationship(self, wishlist_item, shop_account):
        assert wishlist_item.account is not None
        assert wishlist_item.account.id == shop_account.id

    def test_account_backref_dynamic(self, wishlist_item, shop_account):
        backref = shop_account.wishlist_items
        assert backref.count() >= 1
        assert any(i.id == wishlist_item.id for i in backref.all())


class TestShopWishlistConstraints:
    def test_account_product_pair_unique(self, db_session, sample_tenant, sample_product, shop_account, wishlist_item):
        from models.shop_wishlist import ShopWishlist

        db_session.add(
            ShopWishlist(
                tenant_id=sample_tenant.id,
                account_id=shop_account.id,
                product_id=sample_product.id,
            )
        )
        with pytest.raises(IntegrityError):
            db_session.flush()
        db_session.rollback()

    def test_same_product_allowed_for_other_account(
        self,
        db_session,
        sample_tenant,
        sample_product,
        sample_customer,
        shop_account,
        wishlist_item,
    ):
        from models.shop_customer_account import ShopCustomerAccount
        from models.shop_wishlist import ShopWishlist

        other = ShopCustomerAccount(
            tenant_id=sample_tenant.id,
            customer_id=sample_customer.id,
            email="shopper2@example.com",
            name="Shopper Two",
        )
        other.set_password("secret123")
        db_session.add(other)
        db_session.flush()

        db_session.add(
            ShopWishlist(
                tenant_id=sample_tenant.id,
                account_id=other.id,
                product_id=sample_product.id,
            )
        )
        db_session.commit()

    def test_account_id_required(self, db_session, sample_tenant, sample_product):
        from models.shop_wishlist import ShopWishlist

        db_session.add(
            ShopWishlist(
                tenant_id=sample_tenant.id,
                account_id=None,
                product_id=sample_product.id,
            )
        )
        with pytest.raises(IntegrityError):
            db_session.flush()
        db_session.rollback()
