from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from utils.pos_helpers import (
    POS_WALKIN_MARKER,
    close_pos_session,
    create_pos_session,
    get_active_session,
    get_pos_walkin_customer,
    lookup_pos_product_exact,
    merge_checkout_lines,
    require_active_session,
    search_pos_products,
    serialize_pos_product,
)


def _product(pid=1, price=Decimal("25"), sku="SKU1", active=True):
    p = MagicMock()
    p.id = pid
    p.name = "Widget"
    p.name_ar = "أداة"
    p.sku = sku
    p.barcode = "BC1"
    p.regular_price = price
    p.current_stock = Decimal("10")
    p.unit = "pcs"
    p.is_active = active
    return p


class _FakeProductQuery:
    """Chainable query mock matching StockService filter/limit/order_by depth."""

    def __init__(self, *, first=None, exact_all=None, fuzzy_all=None, browse_all=None):
        self._first = first
        self._exact_all = exact_all if exact_all is not None else []
        self._fuzzy_all = fuzzy_all if fuzzy_all is not None else []
        self._browse_all = browse_all if browse_all is not None else []
        self._limit_val = None

    def filter(self, *args, **kwargs):
        return _FakeProductQuery(
            first=self._first,
            exact_all=self._exact_all,
            fuzzy_all=self._fuzzy_all,
            browse_all=self._browse_all,
        )

    def order_by(self, *args, **kwargs):
        return self

    def limit(self, n):
        child = _FakeProductQuery(
            first=self._first,
            exact_all=self._exact_all,
            fuzzy_all=self._fuzzy_all,
            browse_all=self._browse_all,
        )
        child._limit_val = n
        return child

    def first(self):
        return self._first

    def all(self):
        if self._limit_val == 5:
            return self._exact_all
        if self._limit_val:
            return self._fuzzy_all or self._browse_all
        return []


class TestMergeCheckoutLines:
    def test_merges_duplicate_product_rows(self):
        lines = [
            {"product_id": 1, "quantity": "2", "discount_percent": 0},
            {
                "product_id": 1,
                "quantity": "3",
                "discount_percent": 5,
                "unit_price": "20",
            },
        ]
        merged = merge_checkout_lines(lines)
        assert len(merged) == 1
        assert merged[0]["quantity"] == Decimal("5")
        assert merged[0]["unit_price"] == Decimal("20")

    def test_rejects_invalid_row_type(self):
        with pytest.raises(ValueError, match="غير صالحة"):
            merge_checkout_lines(["bad"])

    def test_rejects_non_positive_quantity(self):
        with pytest.raises(ValueError, match="أكبر من صفر"):
            merge_checkout_lines([{"product_id": 1, "quantity": "0"}])

    def test_rejects_invalid_discount(self):
        with pytest.raises(ValueError, match="0 و 100"):
            merge_checkout_lines(
                [{"product_id": 1, "quantity": "1", "discount_percent": 150}]
            )


class TestSerializePosProduct:
    def test_serializes_stock_and_labels(self):
        product = _product()
        payload = serialize_pos_product(product, {1: Decimal("4")}, warehouse_id=2)
        assert payload["stock"] == 4.0
        assert payload["text"] == "Widget (SKU1)"
        assert payload["warehouse_id"] == 2
        assert payload["is_out_of_stock"] is False

    def test_flags_inactive_and_no_stock(self):
        product = _product(active=False)
        payload = serialize_pos_product(product, {1: Decimal("0")})
        assert payload["is_inactive"] is True
        assert payload["is_out_of_stock"] is True


class TestWalkinCustomer:
    def test_returns_existing_walkin(self, mocker):
        existing = MagicMock(id=7)
        chain = MagicMock()
        chain.filter.return_value.filter.return_value.order_by.return_value.first.return_value = existing
        mocker.patch("utils.pos_helpers.tenant_query", return_value=chain)
        mocker.patch("utils.pos_helpers.get_active_tenant_id", return_value=1)
        assert get_pos_walkin_customer(1) is existing

    def test_creates_walkin_when_query_empty(self, mocker):
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.first.return_value = None
        mocker.patch("utils.pos_helpers.tenant_query", return_value=mock_query)
        mocker.patch("utils.pos_helpers.db.or_", return_value=MagicMock())
        mocker.patch("utils.pos_helpers.get_active_tenant_id", return_value=1)
        created = MagicMock(id=99)
        mocker.patch("utils.pos_helpers.Customer", return_value=created)
        add = mocker.patch("utils.pos_helpers.db.session.add")
        flush = mocker.patch("utils.pos_helpers.db.session.flush")
        result = get_pos_walkin_customer(1)
        add.assert_called_once_with(created)
        flush.assert_called_once()
        assert result is created

    def test_creates_walkin_when_missing(self, app, db_session, sample_tenant):
        with app.app_context():
            first = get_pos_walkin_customer(sample_tenant.id)
            second = get_pos_walkin_customer(sample_tenant.id)
        assert first.id is not None
        assert second.id == first.id
        assert POS_WALKIN_MARKER in (first.notes or "")

    def test_requires_tenant(self, mocker):
        mocker.patch("utils.pos_helpers.get_active_tenant_id", return_value=None)
        with pytest.raises(ValueError, match="شركة"):
            get_pos_walkin_customer()


class TestProductSearch:
    def test_empty_code_lookup(self, mocker):
        mocker.patch("utils.pos_helpers.StockService.get_visible_products_query")
        product, stock = lookup_pos_product_exact("")
        assert product is None
        assert stock == {}

    def test_exact_barcode_lookup(self, mocker):
        product = _product()
        base = _FakeProductQuery(first=product)
        mocker.patch(
            "utils.pos_helpers.StockService.get_visible_products_query",
            return_value=base,
        )
        mocker.patch("utils.pos_helpers._warehouse_ids_for_stock", return_value=[1])
        mocker.patch(
            "utils.pos_helpers.get_branch_stock_map", return_value={1: Decimal("3")}
        )
        found, stock = lookup_pos_product_exact("BC1")
        assert found.id == product.id
        assert stock[1] == Decimal("3")

    def test_search_with_query_string(self, mocker):
        product = _product()
        base = _FakeProductQuery(exact_all=[], fuzzy_all=[product])
        mocker.patch(
            "utils.pos_helpers.StockService.get_visible_products_query",
            return_value=base,
        )
        mocker.patch("utils.pos_helpers._warehouse_ids_for_stock", return_value=[1])
        mocker.patch(
            "utils.pos_helpers.get_branch_stock_map", return_value={1: Decimal("2")}
        )
        products, stock, wh = search_pos_products(
            "wid", user=MagicMock(), warehouse_id=1, category_id=2
        )
        assert products == [product]
        assert wh == [1]

    def test_search_exact_barcode_match(self, mocker):
        product = _product()
        base = _FakeProductQuery(exact_all=[product])
        mocker.patch(
            "utils.pos_helpers.StockService.get_visible_products_query",
            return_value=base,
        )
        mocker.patch("utils.pos_helpers._warehouse_ids_for_stock", return_value=[1])
        mocker.patch(
            "utils.pos_helpers.get_branch_stock_map", return_value={1: Decimal("5")}
        )
        products, stock, wh = search_pos_products("BC1", user=MagicMock())
        assert products == [product]

    def test_search_without_query_returns_limited(self, mocker):
        product = _product()
        base = _FakeProductQuery(browse_all=[product])
        mocker.patch(
            "utils.pos_helpers.StockService.get_visible_products_query",
            return_value=base,
        )
        mocker.patch("utils.pos_helpers._warehouse_ids_for_stock", return_value=[])
        products, stock, wh = search_pos_products("", user=MagicMock())
        assert products == [product]
        assert stock == {}

    def test_lookup_not_found(self, mocker):
        base = _FakeProductQuery(first=None)
        mocker.patch(
            "utils.pos_helpers.StockService.get_visible_products_query",
            return_value=base,
        )
        found, stock = lookup_pos_product_exact("MISSING")
        assert found is None

    def test_warehouse_ids_for_stock_single(self, mocker):
        mocker.patch(
            "utils.pos_helpers.get_accessible_warehouse_ids", return_value=[1, 2]
        )
        from utils.pos_helpers import _warehouse_ids_for_stock

        assert _warehouse_ids_for_stock(5, user=MagicMock()) == [5]

    def test_warehouse_ids_for_stock_accessible(self, mocker):
        mocker.patch(
            "utils.pos_helpers.get_accessible_warehouse_ids", return_value=[1, 2]
        )
        from utils.pos_helpers import _warehouse_ids_for_stock

        assert _warehouse_ids_for_stock(None, user=MagicMock()) == [1, 2]

    def test_get_active_session_no_tenant(self, mocker):
        mocker.patch("utils.pos_helpers.get_active_tenant_id", return_value=None)
        assert get_active_session(MagicMock()) is None

    def test_require_active_session_raises_value(self, mocker):
        mocker.patch("utils.pos_helpers.get_active_session", return_value=None)
        with pytest.raises(ValueError):
            require_active_session(MagicMock())


class TestPosSessions:
    def test_get_active_session_none_without_tenant(self, mocker):
        mocker.patch("utils.pos_helpers.get_active_tenant_id", return_value=None)
        assert get_active_session(MagicMock(id=1)) is None

    def test_get_active_session_returns_open(self, mocker):
        session = MagicMock()
        chain = MagicMock()
        chain.filter.return_value.order_by.return_value.first.return_value = session
        mocker.patch("utils.pos_helpers.PosSession.query", chain)
        mocker.patch("utils.pos_helpers.get_active_tenant_id", return_value=1)
        mocker.patch("utils.pos_helpers.get_active_branch_id", return_value=2)
        user = MagicMock(id=9)
        assert get_active_session(user, branch_id=2) is session

    def test_require_active_session_raises(self, mocker):
        mocker.patch("utils.pos_helpers.get_active_session", return_value=None)
        with pytest.raises(ValueError, match="جلسة"):
            require_active_session(MagicMock())

    def test_require_active_session_returns_session(self, mocker):
        session = MagicMock()
        mocker.patch("utils.pos_helpers.get_active_session", return_value=session)
        assert require_active_session(MagicMock()) is session

    def test_create_pos_session(self, mocker):
        mocker.patch("utils.pos_helpers.get_active_tenant_id", return_value=1)
        mocker.patch("utils.pos_helpers.generate_number", return_value="POS-SES-1")
        mocker.patch("utils.pos_helpers.PosSession", return_value=MagicMock(id=3))
        add = mocker.patch("utils.pos_helpers.db.session.add")
        user = MagicMock(id=4)
        create_pos_session(user, branch_id=2, opening_balance=Decimal("100"))
        add.assert_called_once()

    def test_create_pos_session_requires_tenant(self, mocker):
        mocker.patch("utils.pos_helpers.get_active_tenant_id", return_value=None)
        with pytest.raises(ValueError, match="شركة"):
            create_pos_session(MagicMock(), branch_id=1)


class TestClosePosSession:
    @staticmethod
    def _session():
        s = MagicMock()
        s.id = 10
        s.tenant_id = 1
        s.branch_id = 2
        s.session_number = "POS-1"
        s.user_id = 5
        s.difference = Decimal("0")
        s.close = MagicMock()
        return s

    def test_close_aggregates_sales(self, mocker):
        session = self._session()
        payment = MagicMock(payment_method="cash", amount=Decimal("50"))
        card_pay = MagicMock(payment_method="card", amount=Decimal("20"))
        sale = MagicMock(total_amount=Decimal("70"), payments=[payment, card_pay])
        sale_q = MagicMock()
        sale_q.filter.return_value.all.return_value = [sale]
        mocker.patch("models.Sale.query", sale_q)
        close_pos_session(session, Decimal("150"))
        assert session.total_sales == Decimal("70")
        assert session.total_cash_sales == Decimal("50")
        assert session.total_card_sales == Decimal("20")
        session.close.assert_called_once()

    def test_close_posts_shortage_gl(self, mocker):
        session = self._session()
        session.closed_at = datetime.now(timezone.utc)

        def _close(closing, notes):
            session.difference = Decimal("-5")

        session.close.side_effect = _close
        sale_q = MagicMock()
        sale_q.filter.return_value.all.return_value = []
        mocker.patch("models.Sale.query", sale_q)
        mocker.patch("services.gl_service.GLService.ensure_core_accounts")
        mocker.patch(
            "services.gl_tree_builder.GLTreeBuilder._branch_account_code",
            return_value="1110",
        )
        mocker.patch(
            "services.gl_helpers.get_account", return_value=MagicMock(is_header=False)
        )
        mocker.patch(
            "services.gl_service.GLService.get_account_code_for_concept",
            side_effect=["1110", "6995"],
        )
        create_je = mocker.patch("services.gl_service.GLService.create_journal_entry")
        close_pos_session(session, Decimal("95"))
        create_je.assert_called_once()

    def test_close_posts_overage_gl(self, mocker):
        session = self._session()
        session.closed_at = datetime.now(timezone.utc)

        def _close(closing, notes):
            session.difference = Decimal("8")

        session.close.side_effect = _close
        sale_q = MagicMock()
        sale_q.filter.return_value.all.return_value = []
        mocker.patch("models.Sale.query", sale_q)
        mocker.patch("services.gl_service.GLService.ensure_core_accounts")
        mocker.patch(
            "services.gl_tree_builder.GLTreeBuilder._branch_account_code",
            return_value="1110",
        )
        mocker.patch("services.gl_helpers.get_account", return_value=None)
        mocker.patch(
            "services.gl_service.GLService.get_account_code_for_concept",
            side_effect=["1110", "6995"],
        )
        create_je = mocker.patch("services.gl_service.GLService.create_journal_entry")
        close_pos_session(session, Decimal("108"))
        create_je.assert_called_once()

    def test_close_header_cash_account_fallback(self, mocker):
        session = self._session()
        session.closed_at = datetime.now(timezone.utc)

        def _close(closing, notes):
            session.difference = Decimal("-2")

        session.close.side_effect = _close
        sale_q = MagicMock()
        sale_q.filter.return_value.all.return_value = []
        mocker.patch("models.Sale.query", sale_q)
        mocker.patch("services.gl_service.GLService.ensure_core_accounts")
        mocker.patch(
            "services.gl_tree_builder.GLTreeBuilder._branch_account_code",
            return_value="1110",
        )
        mocker.patch(
            "services.gl_helpers.get_account", return_value=MagicMock(is_header=True)
        )
        mocker.patch(
            "services.gl_service.GLService.get_account_code_for_concept",
            side_effect=["1110-B", "6995"],
        )
        create_je = mocker.patch("services.gl_service.GLService.create_journal_entry")
        close_pos_session(session, Decimal("98"))
        create_je.assert_called_once()
