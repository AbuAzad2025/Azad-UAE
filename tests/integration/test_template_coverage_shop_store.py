"""Template coverage for shop, store, and public pages.

Covers templates that were not covered by the base smoke + expansion suites:
- public/donate_azad.html, public/donate_thanks.html
- shop/account_reset_password.html, shop/checkout.html, shop/closed.html
- shop/partials/quick_view_body.html, shop/product.html, shop/return_policy.html
- store/admin_order_detail.html
"""

from __future__ import annotations

from unittest.mock import MagicMock

from flask import render_template


def _make_mock(**kwargs):
    """Create a mock object that returns mocks for any attribute access."""
    mock = MagicMock()
    for key, value in kwargs.items():
        setattr(mock, key, value)
    # Return mock for any other attribute access
    mock.__getattr__ = lambda self, name: MagicMock()
    return mock


def test_donate_azad_template(app):
    """Test public/donate_azad.html renders."""
    with app.test_request_context():
        html = render_template("public/donate_azad.html", vault=_make_mock())
        assert html is not None
        assert len(html) > 0


def test_donate_thanks_template(app):
    """Test public/donate_thanks.html renders."""
    with app.test_request_context():
        html = render_template(
            "public/donate_thanks.html",
            donation=_make_mock(amount_usd="100", amount_aed="367"),
        )
        assert html is not None
        assert len(html) > 0


def test_shop_account_reset_password_template(app):
    """Test shop/account_reset_password.html renders."""
    with app.test_request_context():
        html = render_template(
            "shop/account_reset_password.html",
            store=_make_mock(seo_description="Test store"),
        )
        assert html is not None
        assert len(html) > 0


def test_shop_checkout_template(app):
    """Test shop/checkout.html renders."""
    with app.test_request_context():
        html = render_template(
            "shop/checkout.html",
            store=_make_mock(seo_description="Test store"),
            cart=_make_mock(),
        )
        assert html is not None
        assert len(html) > 0


def test_shop_closed_template(app):
    """Test shop/closed.html renders."""
    with app.test_request_context():
        html = render_template(
            "shop/closed.html",
            store=_make_mock(seo_description="Test store"),
        )
        assert html is not None
        assert len(html) > 0


def test_shop_quick_view_body_template(app):
    """Test shop/partials/quick_view_body.html renders."""
    with app.test_request_context():
        html = render_template(
            "shop/partials/quick_view_body.html",
            product=_make_mock(),
        )
        assert html is not None
        assert len(html) > 0


def test_shop_product_template(app):
    """Test shop/product.html renders."""
    with app.test_request_context():
        html = render_template(
            "shop/product.html",
            product=_make_mock(),
            store=_make_mock(seo_description="Test store"),
        )
        assert html is not None
        assert len(html) > 0


def test_shop_return_policy_template(app):
    """Test shop/return_policy.html renders."""
    with app.test_request_context():
        html = render_template(
            "shop/return_policy.html",
            store=_make_mock(seo_description="Test store"),
        )
        assert html is not None
        assert len(html) > 0


def test_store_admin_order_detail_template(app):
    """Test store/admin_order_detail.html renders."""
    with app.test_request_context():
        html = render_template(
            "store/admin_order_detail.html",
            order=_make_mock(),
        )
        assert html is not None
        assert len(html) > 0
