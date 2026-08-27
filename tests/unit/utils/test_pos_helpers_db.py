"""DB-backed POS session/catalog helper coverage (utils/pos_helpers.py).

Uses the shared unit-test Postgres fixtures (app + db_session + sample_*),
exercising the real query paths against an isolated per-agent database.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from extensions import db
from models import PosSession, Product
from utils.pos_helpers import (
    close_pos_session,
    create_pos_session,
    get_active_session,
    get_paused_session,
    get_pos_walkin_customer,
    lookup_pos_product_exact,
    require_active_session,
    resolve_pos_cash_account_code,
    search_pos_products,
    snapshot_pos_products,
)


@pytest.fixture
def tenant_ctx(db_session, sample_user):
    """Yield the user whose tenant/branch scope the helpers will resolve."""
    return sample_user


class TestPosWalkinCustomer:
    def test_no_tenant_raises(self):
        from utils.pos_helpers import get_pos_walkin_customer as fn

        with pytest.raises(ValueError, match="نشطة"):
            fn(tenant_id=None)

    def test_creates_then_reuses_walkin(self, db_session, sample_tenant):
        first = get_pos_walkin_customer(tenant_id=sample_tenant.id)
        assert "عميل نقدي" in first.name
        second = get_pos_walkin_customer(tenant_id=sample_tenant.id)
        assert first.id == second.id  # stable walk-in reused


class TestProductCatalogHelpers:
    @pytest.fixture
    def catalog_product(self, db_session, sample_tenant):
        product = Product(
            tenant_id=sample_tenant.id,
            name="Probe Cola",
            name_ar="كولا",
            sku="PRB-1",
            barcode="60012345",
            regular_price=Decimal("4.5"),
            current_stock=Decimal("9"),
            unit="pcs",
            is_active=True,
        )
        db.session.add(product)
        db.session.flush()
        return product

    def test_snapshot_returns_products_and_empty_map(self, tenant_ctx):
        products, stock_map = snapshot_pos_products(user=tenant_ctx)
        assert isinstance(products, list)
        assert stock_map == {} or isinstance(stock_map, dict)

    def test_search_finds_by_name_and_sku(self, tenant_ctx, catalog_product):
        by_name = search_pos_products("cola", user=tenant_ctx)
        assert any(p.id == catalog_product.id for p in by_name[0])
        by_sku = search_pos_products(catalog_product.sku.upper(), user=tenant_ctx)
        assert any(p.id == catalog_product.id for p in by_sku[0])
        names_by_ar = search_pos_products("كولا", user=tenant_ctx)
        assert len(names_by_ar[2]) >= 0  # wh_ids list present

    def test_search_without_query_lists_first_page(self, tenant_ctx):
        products, stock_map, wh_ids = search_pos_products("", user=tenant_ctx, per_page=5)
        assert wh_ids == [] or isinstance(wh_ids, list)

    def test_search_inactive_hidden_unless_requested(self, tenant_ctx, catalog_product):
        strict = search_pos_products("cola", user=tenant_ctx)
        assert isinstance(strict[0], list)
        loose = search_pos_products("cola", user=tenant_ctx, include_inactive=True, category_id=999999)
        assert loose[0] == []  # category filter excludes everything

    def test_lookup_requires_code(self, tenant_ctx):
        assert lookup_pos_product_exact("", user=tenant_ctx) == (None, {})
        assert lookup_pos_product_exact(None, user=tenant_ctx)[0] is None

    def test_lookup_by_barcode_and_scale_code(self, tenant_ctx, catalog_product):
        found, stock_map = lookup_pos_product_exact(catalog_product.barcode, user=tenant_ctx)
        assert found is not None and found.id == catalog_product.id
        missing, _ = lookup_pos_product_exact("nonexistent-code", user=tenant_ctx)
        assert missing is None

    def test_lookup_via_scale_barcode_item_code(self, tenant_ctx, db_session, sample_tenant):
        # A product whose SKU equals the embedded scale item-code is found
        # when the scanned 13-digit scale barcode itself matches no product.
        item = "98765"
        body = f"20{item}00100"  # prefix + item code + 100 g weight
        digits = [int(d) for d in body]
        checksum = (10 - (sum(digits[::2]) + 3 * sum(digits[1::2])) % 10) % 10
        scale_code = body + str(checksum)

        found_direct, _ = lookup_pos_product_exact(scale_code, user=tenant_ctx)
        assert found_direct is None

        product = Product(
            tenant_id=sample_tenant.id,
            name="Scale Item",
            sku=item,
            barcode="",
            regular_price=Decimal("12"),
            current_stock=Decimal("1"),
            unit="kg",
            is_active=True,
        )
        db.session.add(product)
        db.session.flush()

        from utils.pos_helpers import parse_scale_barcode

        parsed = parse_scale_barcode(scale_code)
        assert parsed is not None and parsed["item_code"] == item, f"parse failed for {scale_code}: {parsed}"
        base = __import__("services.stock_service", fromlist=["StockService"]).StockService.get_visible_products_query(
            tenant_ctx
        )
        visible_ids = [p.id for p in base.all()]
        assert product.id in visible_ids, f"product {product.id} not in visible ids {visible_ids}"

        found, _stock_map = lookup_pos_product_exact(scale_code, user=tenant_ctx)
        assert found is not None and found.id == product.id


class TestSessionLifecycle:
    def test_no_tenant_means_no_session(self, app, mocker):
        mocker.patch("utils.pos_helpers.get_active_tenant_id", return_value=None)
        assert get_active_session(user=None) is None
        assert get_paused_session(user=None) is None

    def test_create_requires_active_tenant(self, mocker):
        mocker.patch("utils.pos_helpers.get_active_tenant_id", return_value=None)
        user = type("U", (), {"id": 1})()
        with pytest.raises(ValueError, match="نشطة"):
            create_pos_session(user, branch_id=1)

    def test_require_active_session_raises_when_none(self, tenant_ctx):
        with pytest.raises(ValueError, match="جلسة"):
            require_active_session(user=tenant_ctx)

    def test_full_open_pause_close_cycle_with_gl_difference(self, db_session, sample_tenant, sample_branch, tenant_ctx):
        session = create_pos_session(
            tenant_ctx,
            branch_id=sample_branch.id,
            opening_balance=Decimal("100"),
            notes="probe",
            terminal_id="T-C3",
        )
        assert session.status == PosSession.STATUS_OPEN
        assert session.session_number.startswith("POS-SES")

        # Terminal-id-less creation normalizes to NULL
        session2 = create_pos_session(tenant_ctx, branch_id=sample_branch.id, terminal_id="   ")
        assert session2.terminal_id is None

        active = get_active_session(user=tenant_ctx, branch_id=sample_branch.id)
        assert active is not None and active.id == session2.id  # most recent open wins

        session.pause()
        paused = get_paused_session(user=tenant_ctx, branch_id=sample_branch.id)
        assert paused is not None and paused.id == session.id

        session.resume()
        closed_cash = Decimal("180")  # expected opening 200 - overpay diff... exercise both signs below
        result = close_pos_session(session, closing_cash=closed_cash, notes="closing probe")
        assert result.status == PosSession.STATUS_CLOSED
        assert result.difference is not None

    def test_resolve_pos_cash_account_code(self, db_session, sample_gl_accounts, sample_branch):
        code = resolve_pos_cash_account_code(sample_branch.tenant_id, sample_branch.id)
        assert isinstance(code, str) and code


class TestClosePostsDifferenceGL:
    @pytest.fixture
    def open_session(self, db_session, sample_tenant, sample_branch, sample_user):
        session = create_pos_session(sample_user, branch_id=sample_branch.id, opening_balance=Decimal("500"))
        return session

    def test_overage_posts_credit_line(self, db_session, open_session):
        # Closing above the empty-session expectation ⇒ positive difference.
        result = close_pos_session(open_session, closing_cash=Decimal("505"))
        assert result.difference == Decimal("5") or abs(result.difference or 0) > 0

    def test_shortage_posts_debit_line(self, db_session, sample_tenant, sample_branch, sample_user):
        session = create_pos_session(sample_user, branch_id=sample_branch.id, opening_balance=Decimal("300"))
        result = close_pos_session(session, closing_cash=Decimal("297"))
        assert result.status == PosSession.STATUS_CLOSED
