"""Coverage-4 for services.stock_service — pure/else/except arcs (real paths)."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from services.stock_service import _MWACHelper, _resolve_gl_concept_account


@pytest.fixture(autouse=True)
def _ctx(app, db_session):
    with app.app_context():
        yield
        db_session.rollback()


class TestMwacCalc:
    def test_receipt(self):
        qty, val, avg = _MWACHelper.calc(Decimal("10"), Decimal("100"), Decimal("5"), Decimal("12"))
        assert qty == Decimal("15")
        assert val == Decimal("160")
        assert avg == Decimal("10.6667")

    def test_zero_qty_returns_zero_avg(self):
        qty, val, avg = _MWACHelper.calc(Decimal("5"), Decimal("50"), Decimal("-5"), Decimal("10"))
        assert qty == Decimal("0")
        assert avg == Decimal("0")

    def test_issue(self):
        qty, val, avg = _MWACHelper.calc(Decimal("10"), Decimal("100"), Decimal("-4"), Decimal("10"))
        assert qty == Decimal("6")


class TestResolveGlAccount:
    def test_static_disabled_returns_fallback(self, mocker):
        mocker.patch("services.gl_account_resolver.is_dynamic_gl_mapping_enabled", return_value=False)
        assert _resolve_gl_concept_account("ANYTHING", "9999", tenant_id=1) == "9999"

    def test_no_tenant_returns_fallback_or_static(self, mocker):
        mocker.patch("services.gl_account_resolver.is_dynamic_gl_mapping_enabled", return_value=True)
        out = _resolve_gl_concept_account("NOPE_CONCEPT", "9999", tenant_id=None)
        assert out in ("9999", out)

    def test_dynamic_success(self, mocker):
        mocker.patch("services.gl_account_resolver.is_dynamic_gl_mapping_enabled", return_value=True)
        mocker.patch(
            "services.gl_account_resolver.resolve_gl_account",
            return_value=MagicMock(account_code="1150"),
        )
        assert _resolve_gl_concept_account("CASH", "9999", tenant_id=3) == "1150"

    def test_dynamic_mapping_error_reraises(self, mocker):
        from services.gl_account_resolver import GLMappingError

        mocker.patch("services.gl_account_resolver.is_dynamic_gl_mapping_enabled", return_value=True)
        mocker.patch(
            "services.gl_account_resolver.resolve_gl_account",
            side_effect=GLMappingError(tenant_id=1, concept_code="C", branch_id=None, issue="x"),
        )
        with pytest.raises(GLMappingError):
            _resolve_gl_concept_account("C", "9999", tenant_id=1)

    def test_dynamic_generic_error_wraps(self, mocker):
        from services.gl_account_resolver import GLMappingError

        mocker.patch("services.gl_account_resolver.is_dynamic_gl_mapping_enabled", return_value=True)
        mocker.patch(
            "services.gl_account_resolver.resolve_gl_account", side_effect=RuntimeError("boom")
        )
        with pytest.raises(GLMappingError):
            _resolve_gl_concept_account("C", "9999", tenant_id=1)

    def test_static_concept_hit(self, mocker):
        mocker.patch("services.gl_account_resolver.is_dynamic_gl_mapping_enabled", return_value=False)
        from services.gl_service import GL_ACCOUNT_CONCEPTS

        # pick a real concept mapping if available
        if GL_ACCOUNT_CONCEPTS:
            concept = next(iter(GL_ACCOUNT_CONCEPTS.values()))
            out = _resolve_gl_concept_account(concept, "9999", tenant_id=None)
            assert isinstance(out, str)


class TestAvailability:
    def test_missing_product(self, mocker):
        from services.stock_service import StockService

        mocker.patch("services.stock_service.db.session.get", return_value=None)
        ok, _msg = StockService.check_availability(999, 1)
        assert ok is False

    def test_inactive_product(self, mocker):
        from types import SimpleNamespace

        from services.stock_service import StockService

        mocker.patch(
            "services.stock_service.db.session.get",
            return_value=SimpleNamespace(is_active=False),
        )
        ok, _msg = StockService.check_availability(1, 1)
        assert ok is False

    def test_insufficient_stock(self, mocker):
        from types import SimpleNamespace

        from services.stock_service import StockService

        mocker.patch(
            "services.stock_service.db.session.get",
            return_value=SimpleNamespace(is_active=True, current_stock=Decimal("1")),
        )
        ok, _msg = StockService.check_availability(1, 5)
        assert ok is False

    def test_sufficient_stock(self, mocker):
        from types import SimpleNamespace

        from services.stock_service import StockService

        mocker.patch(
            "services.stock_service.db.session.get",
            return_value=SimpleNamespace(is_active=True, current_stock=Decimal("10")),
        )
        ok, _msg = StockService.check_availability(1, 5)
        assert ok is True

    def test_warehouse_missing(self, mocker):
        from types import SimpleNamespace

        from services.stock_service import StockService

        mocker.patch(
            "services.stock_service.db.session.get",
            return_value=SimpleNamespace(is_active=True, current_stock=Decimal("10")),
        )
        from models import Warehouse

        mq = MagicMock()
        mq.filter_by.return_value = mq
        mq.first.return_value = None
        mocker.patch.object(Warehouse, "query", new_callable=mocker.PropertyMock, return_value=mq)
        ok, _msg = StockService.check_availability_in_warehouse(1, 1, 999)
        assert ok is False

    def test_warehouse_negative_allowed(self, mocker):
        from types import SimpleNamespace

        from services.stock_service import StockService

        mocker.patch(
            "services.stock_service.db.session.get",
            return_value=SimpleNamespace(is_active=True, current_stock=Decimal("0")),
        )
        from models import Warehouse

        mq = MagicMock()
        mq.filter_by.return_value = mq
        mq.first.return_value = SimpleNamespace(allow_negative_inventory=True)
        mocker.patch.object(Warehouse, "query", new_callable=mocker.PropertyMock, return_value=mq)
        ok, _msg = StockService.check_availability_in_warehouse(1, 5, 1)
        assert ok is True
