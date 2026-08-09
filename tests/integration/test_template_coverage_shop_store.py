"""Template coverage for shop, store, and public pages.

Covers templates that were not covered by the base smoke + expansion suites:
- shop/account_reset_password.html, shop/closed.html, shop/checkout.html
- shop/partials/quick_view_body.html, shop/product.html, shop/return_policy.html
- store/admin_order_detail.html

Uses real fixtures + `_store_context` so templates receive the same context
the shop blueprint provides.
"""

from __future__ import annotations

import pytest
from flask import render_template

from routes.shop import _store_context


@pytest.fixture
def shop_storefront(db_session, sample_tenant, sample_warehouse):
    """A live storefront: enabled tenant store, global ecommerce on."""
    import uuid

    from models import SystemSettings, TenantStore

    slug = f"test-store-{uuid.uuid4().hex[:8]}"
    store = TenantStore(
        tenant_id=sample_tenant.id,
        warehouse_id=sample_warehouse.id,
        is_enabled=True,
        platform_disabled=False,
        store_slug=slug,
        title=sample_tenant.name_ar or sample_tenant.name,
        phone="0500000000",
        whatsapp="971500000000",
    )
    db_session.add(store)
    db_session.commit()

    settings = SystemSettings.get_current()
    settings.enable_ecommerce = True
    db_session.commit()
    return store


def test_shop_account_reset_password_template(app, shop_storefront):
    """Test shop/account_reset_password.html renders."""
    with app.test_request_context():
        ctx = _store_context(shop_storefront)
        html = render_template(
            "shop/account_reset_password.html",
            token="test-token",
            noindex=True,
            **ctx,
        )
        assert html is not None
        assert len(html) > 0


def test_shop_checkout_template(app, shop_storefront):
    """Test shop/checkout.html renders."""
    from flask import session as flask_session

    from services.store_service import StoreService

    with app.test_request_context():
        ctx = _store_context(shop_storefront)
        cart = StoreService.get_cart(flask_session, tenant_id=shop_storefront.tenant_id) or {}
        html = render_template(
            "shop/checkout.html",
            cart=cart,
            noindex=True,
            **ctx,
        )
        assert html is not None
        assert len(html) > 0


def test_shop_closed_template(app, shop_storefront):
    """Test shop/closed.html renders."""
    with app.test_request_context():
        ctx = _store_context(shop_storefront)
        html = render_template("shop/closed.html", reason="tenant", **ctx)
        assert html is not None
        assert len(html) > 0


def test_shop_quick_view_body_template(app, shop_storefront, sample_product):
    """Test shop/partials/quick_view_body.html renders."""
    with app.test_request_context():
        ctx = _store_context(shop_storefront)
        html = render_template(
            "shop/partials/quick_view_body.html",
            product=sample_product,
            display_price=ctx["dp"](sample_product),
            available=1,
            wa_url=None,
            **ctx,
        )
        assert html is not None
        assert len(html) > 0


def test_shop_product_template(app, shop_storefront, sample_product):
    """Test shop/product.html renders."""
    with app.test_request_context():
        ctx = _store_context(shop_storefront)
        html = render_template(
            "shop/product.html",
            product=sample_product,
            display_price=ctx["dp"](sample_product),
            available=1,
            wa_url=None,
            related_products=[],
            recent_products=[],
            variants=[],
            loyalty_points=0,
            reviews=[],
            review_count=0,
            avg_rating=None,
            **ctx,
        )
        assert html is not None
        assert len(html) > 0


def test_shop_return_policy_template(app, shop_storefront):
    """Test shop/return_policy.html renders."""
    with app.test_request_context():
        ctx = _store_context(shop_storefront)
        policy = shop_storefront.return_policy(ctx["lang"])
        if not policy:
            pytest.skip("store has no return policy configured")
        html = render_template("shop/return_policy.html", policy=policy, **ctx)
        assert html is not None
        assert len(html) > 0


def test_store_admin_order_detail_template(app, db_session, sample_user, sample_sale):
    """Test store/admin_order_detail.html renders."""
    from flask_login import login_user

    with app.test_request_context():
        login_user(sample_user)
        html = render_template(
            "store/admin_order_detail.html",
            order=sample_sale,
            pay_method=None,
            stock_issues=[],
            is_fulfilled=False,
            status_label="pending",
            wa_admin_url=None,
        )
        assert html is not None
        assert len(html) > 0
