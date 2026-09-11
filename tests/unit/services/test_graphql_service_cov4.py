"""Cov4: graphql_service — permission/converter/resolver/mutate/schema arcs."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import services.graphql_service as g


def _anon():
    u = SimpleNamespace(is_authenticated=False, is_owner=False)
    return u


def _owner():
    u = SimpleNamespace(is_authenticated=True, is_owner=True, id=1, has_permission=lambda c: True)
    return u


def test_require_permission_unauthenticated(monkeypatch):
    monkeypatch.setattr(g, "current_user", _anon())
    with pytest.raises(PermissionError, match="Authentication"):
        g._require_permission("manage_sales")


def test_require_permission_owner_bypass(monkeypatch):
    monkeypatch.setattr(g, "current_user", _owner())
    assert g._require_permission("anything") is None


def test_require_permission_missing(monkeypatch):
    u = SimpleNamespace(is_authenticated=True, is_owner=False, has_permission=lambda c: False)
    monkeypatch.setattr(g, "current_user", u)
    with pytest.raises(PermissionError, match="Missing permission"):
        g._require_permission("manage_sales")


def test_converters_handle_nones():
    s = SimpleNamespace(
        id=1, sale_number="S", customer_id=2, total_amount=None, amount_aed=None, status="pending", created_at=None
    )
    t = g.Query._convert_sale_to_type(s)
    assert t.total_amount == 0
    c = SimpleNamespace(id=1, name="n", phone=None, email=None, address=None, balance=None)
    assert g.Query._convert_customer_to_type(c).balance == 0
    p = SimpleNamespace(
        id=1, name="p", part_number=None, regular_price=None, cost_price=None, current_stock=0, is_active=True
    )
    assert g.Query._convert_product_to_type(p).regular_price == 0


def test_resolvers_call_tenant_query(monkeypatch, sample_tenant):
    monkeypatch.setattr(g, "current_user", _owner())
    fake_q = MagicMock()
    fake_q.limit.return_value.offset.return_value.all.return_value = []
    fake_q.limit.return_value.all.return_value = []
    fake_q.filter_by.return_value.first.return_value = None
    with patch.object(g, "tenant_query", return_value=fake_q):
        assert g.Query.resolve_all_sales(None, limit=5, offset=2) == []
        assert g.Query.resolve_sale(None, 1) is None
        assert g.Query.resolve_all_customers(None) == []
        assert g.Query.resolve_customer(None, 1) is None
        assert g.Query.resolve_all_products(None) == []
        assert g.Query.resolve_product(None, 1) is None


def test_resolvers_return_rows(monkeypatch):
    monkeypatch.setattr(g, "current_user", _owner())
    sale = SimpleNamespace(
        id=1, sale_number="S1", customer_id=1, total_amount=10, amount_aed=10, status="confirmed", created_at=None
    )
    fq = MagicMock()
    fq.filter_by.return_value.first.return_value = sale
    with patch.object(g, "tenant_query", return_value=fq):
        assert g.Query.resolve_sale(None, 1).sale_number == "S1"


def test_mutate_no_seller(monkeypatch):
    monkeypatch.setattr(g, "current_user", _anon())
    with pytest.raises(PermissionError):
        g.CreateSale.mutate(None, customer_id=1, total_amount=10)


def test_mutate_customer_missing(monkeypatch):
    monkeypatch.setattr(g, "current_user", _owner())
    fq = MagicMock()
    fq.filter_by.return_value.first.return_value = None
    with patch.object(g, "tenant_query", return_value=fq):
        with pytest.raises(ValueError, match="Customer not found"):
            g.CreateSale.mutate(None, customer_id=999, total_amount=10)


def test_mutate_success_and_flush_error(monkeypatch, db_session, sample_customer, sample_tenant):
    from unittest.mock import patch

    monkeypatch.setattr(g, "current_user", _owner())
    fq = MagicMock()
    fq.filter_by.return_value.first.return_value = sample_customer
    monkeypatch.setattr(g, "assign_tenant_id", lambda sale: setattr(sale, "tenant_id", sample_tenant.id))
    with patch.object(g, "tenant_query", return_value=fq):
        with patch.object(g.db.session, "flush", side_effect=[None, RuntimeError("flush boom")]):
            out = g.CreateSale.mutate(None, customer_id=sample_customer.id, total_amount=25)
            assert out.success is True
            with pytest.raises(RuntimeError):
                g.CreateSale.mutate(None, customer_id=sample_customer.id, total_amount=25)


def test_build_schema_branches():
    assert g.build_schema(allow_mutations=True).mutation is not None
    assert g.build_schema(allow_mutations=False).mutation is None
