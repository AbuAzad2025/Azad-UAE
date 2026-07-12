from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


class _Col:
    def __eq__(self, other):
        return self

    def __ge__(self, other):
        return self

    def between(self, a, b):
        return self

    def desc(self):
        return self

    def has(self, **kwargs):
        return self


class TestRequirePermission:
    def test_unauthenticated_raises(self, mocker):
        user = MagicMock(is_authenticated=False)
        mocker.patch('services.graphql_service.current_user', user)
        from services.graphql_service import _require_permission

        with pytest.raises(PermissionError, match='Authentication'):
            _require_permission('manage_sales')

    def test_owner_bypasses(self, mocker):
        user = MagicMock(is_authenticated=True, is_owner=True)
        mocker.patch('services.graphql_service.current_user', user)
        from services.graphql_service import _require_permission

        _require_permission('manage_sales')

    def test_missing_permission_raises(self, mocker):
        user = MagicMock(is_authenticated=True, is_owner=False)
        user.has_permission.return_value = False
        mocker.patch('services.graphql_service.current_user', user)
        from services.graphql_service import _require_permission

        with pytest.raises(PermissionError, match='Missing permission'):
            _require_permission('manage_sales')


class TestQueryResolvers:
    def _sale(self):
        return SimpleNamespace(
            id=1, sale_number='S-1', customer_id=2,
            total_amount=Decimal('100'), amount_aed=Decimal('100'),
            status='confirmed', created_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
        )

    def test_resolve_all_sales(self, mocker):
        mocker.patch('services.graphql_service._require_permission')
        chain = MagicMock()
        chain.limit.return_value.offset.return_value.all.return_value = [self._sale()]
        mocker.patch('services.graphql_service.tenant_query', return_value=chain)
        from services.graphql_service import Query

        result = Query().resolve_all_sales(None, limit=10, offset=0)
        assert result[0].sale_number == 'S-1'

    def test_resolve_sale_none(self, mocker):
        mocker.patch('services.graphql_service._require_permission')
        chain = MagicMock()
        chain.filter_by.return_value.first.return_value = None
        mocker.patch('services.graphql_service.tenant_query', return_value=chain)
        from services.graphql_service import Query

        assert Query().resolve_sale(None, id=99) is None

    def test_resolve_all_customers(self, mocker):
        mocker.patch('services.graphql_service._require_permission')
        customer = SimpleNamespace(
            id=1, name='Acme', phone='050', email='a@b.com', address='UAE', balance=Decimal('10'),
        )
        chain = MagicMock()
        chain.limit.return_value.all.return_value = [customer]
        mocker.patch('services.graphql_service.tenant_query', return_value=chain)
        from services.graphql_service import Query

        result = Query().resolve_all_customers(None, limit=5)
        assert result[0].name == 'Acme'

    def test_resolve_customer_by_id(self, mocker):
        mocker.patch('services.graphql_service._require_permission')
        customer = SimpleNamespace(
            id=3, name='Co', phone=None, email=None, address=None, balance=None,
        )
        chain = MagicMock()
        chain.filter_by.return_value.first.return_value = customer
        mocker.patch('services.graphql_service.tenant_query', return_value=chain)
        from services.graphql_service import Query

        result = Query().resolve_customer(None, id=3)
        assert result.balance == 0

    def test_resolve_all_products(self, mocker):
        mocker.patch('services.graphql_service._require_permission')
        product = SimpleNamespace(
            id=4, name='Widget', part_number='W1',
            regular_price=Decimal('20'), cost_price=Decimal('10'),
            current_stock=5, is_active=True,
        )
        chain = MagicMock()
        chain.limit.return_value.all.return_value = [product]
        mocker.patch('services.graphql_service.tenant_query', return_value=chain)
        from services.graphql_service import Query

        result = Query().resolve_all_products(None, limit=5)
        assert result[0].current_stock == 5

    def test_resolve_product_by_id(self, mocker):
        mocker.patch('services.graphql_service._require_permission')
        product = SimpleNamespace(
            id=5, name='X', part_number=None,
            regular_price=None, cost_price=None,
            current_stock=0, is_active=False,
        )
        chain = MagicMock()
        chain.filter_by.return_value.first.return_value = product
        mocker.patch('services.graphql_service.tenant_query', return_value=chain)
        from services.graphql_service import Query

        result = Query().resolve_product(None, id=5)
        assert result.regular_price == 0


class TestCreateSaleMutation:
    def test_mutate_creates_sale(self, mocker, app):
        user = MagicMock(is_authenticated=True, id=42)
        mocker.patch('services.graphql_service.current_user', user)
        mocker.patch('services.graphql_service._require_permission')
        customer = SimpleNamespace(id=7)
        chain = MagicMock()
        chain.filter_by.return_value.first.return_value = customer
        mocker.patch('services.graphql_service.tenant_query', return_value=chain)
        mocker.patch('services.graphql_service.generate_number', return_value='INV-1', create=True)
        mocker.patch('utils.helpers.generate_number', return_value='INV-1')
        mocker.patch('services.graphql_service.assign_tenant_id')
        session = mocker.patch('services.graphql_service.db.session')
        from services.graphql_service import CreateSale

        with app.app_context():
            result = CreateSale.mutate(None, None, customer_id=7, total_amount=150.0)
        assert result.success is True
        session.add.assert_called_once()
        session.flush.assert_called_once()

    def test_mutate_customer_not_found(self, mocker):
        user = MagicMock(is_authenticated=True, id=1)
        mocker.patch('services.graphql_service.current_user', user)
        mocker.patch('services.graphql_service._require_permission')
        chain = MagicMock()
        chain.filter_by.return_value.first.return_value = None
        mocker.patch('services.graphql_service.tenant_query', return_value=chain)
        from services.graphql_service import CreateSale

        with pytest.raises(ValueError, match='Customer not found'):
            CreateSale.mutate(None, None, customer_id=1, total_amount=10.0)

    def test_mutate_unauthenticated_seller(self, mocker):
        user = MagicMock(is_authenticated=False, id=None)
        mocker.patch('services.graphql_service.current_user', user)
        mocker.patch('services.graphql_service._require_permission')
        customer = SimpleNamespace(id=1)
        chain = MagicMock()
        chain.filter_by.return_value.first.return_value = customer
        mocker.patch('services.graphql_service.tenant_query', return_value=chain)
        from services.graphql_service import CreateSale

        with pytest.raises(PermissionError, match='Authentication'):
            CreateSale.mutate(None, None, customer_id=1, total_amount=10.0)

    def test_mutate_commit_failure_rolls_back(self, mocker, app):
        user = MagicMock(is_authenticated=True, id=1)
        mocker.patch('services.graphql_service.current_user', user)
        mocker.patch('services.graphql_service._require_permission')
        customer = SimpleNamespace(id=1)
        chain = MagicMock()
        chain.filter_by.return_value.first.return_value = customer
        mocker.patch('services.graphql_service.tenant_query', return_value=chain)
        mocker.patch('utils.helpers.generate_number', return_value='INV-2')
        mocker.patch('services.graphql_service.assign_tenant_id')
        session = mocker.patch('services.graphql_service.db.session')
        session.flush.side_effect = RuntimeError('commit failed')
        from services.graphql_service import CreateSale

        with app.app_context():
            with pytest.raises(RuntimeError, match='commit failed'):
                CreateSale.mutate(None, None, customer_id=1, total_amount=10.0)


class TestBuildSchema:
    def test_schema_without_mutations(self):
        from services.graphql_service import build_schema

        schema = build_schema(allow_mutations=False)
        assert schema.mutation is None

    def test_schema_with_mutations(self):
        from services.graphql_service import build_schema

        schema = build_schema(allow_mutations=True)
        assert schema.mutation is not None
