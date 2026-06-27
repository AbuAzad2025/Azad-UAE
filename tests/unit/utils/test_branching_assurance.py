"""Branch scoping — global users, warehouse access, stock maps."""
from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock

import pytest


class _Col:
    def __eq__(self, other):
        return self

    def __lt__(self, other):
        return self


def _user(**kwargs):
    user = MagicMock()
    user.is_authenticated = kwargs.get('is_authenticated', True)
    user.is_owner = kwargs.get('is_owner', False)
    user.branch_id = kwargs.get('branch_id', 3)
    role = MagicMock()
    role.slug = kwargs.get('role_slug', 'cashier')
    user.role = role
    user.is_super_admin = MagicMock(return_value=kwargs.get('is_super_admin', False))
    return user


class TestGlobalUser:
    def test_is_global_user_owner(self):
        from utils.branching import is_global_user
        assert is_global_user(_user(is_owner=True)) is True

    def test_is_global_user_super_admin(self):
        from utils.branching import is_global_user
        assert is_global_user(_user(role_slug='super_admin')) is True

    def test_is_global_user_false(self):
        from utils.branching import is_global_user
        assert is_global_user(_user(is_authenticated=False)) is False

    def test_role_requires_branch(self):
        from utils.branching import role_requires_branch
        assert role_requires_branch(is_owner=True) is False
        assert role_requires_branch(role=MagicMock(slug='cashier')) is True


class TestBranchScope:
    def test_branch_scope_id_for_global(self, app, mocker):
        mocker.patch('utils.branching.get_active_branch_id', return_value=5)
        mocker.patch('utils.branching.is_global_user', return_value=True)
        from utils.branching import branch_scope_id_for
        assert branch_scope_id_for(_user()) == 5

    def test_report_branch_scope_home_branch(self, mocker):
        mocker.patch('utils.branching.branch_scope_id_for', return_value=None)
        mocker.patch('utils.branching.is_global_user', return_value=True)
        from utils.branching import report_branch_scope_id_for
        assert report_branch_scope_id_for(_user(branch_id=4)) == 4

    def test_get_active_branch_mode_default(self, app):
        from utils.branching import get_active_branch_mode
        with app.test_request_context():
            assert get_active_branch_mode() == 'single'

    def test_should_show_all_branch_columns(self, app, mocker):
        mocker.patch('utils.branching.is_global_user', return_value=True)
        mocker.patch('utils.branching.get_active_branch_mode', return_value='all')
        from utils.branching import should_show_all_branch_columns
        with app.test_request_context():
            assert should_show_all_branch_columns(_user()) is True


class TestBranchAccess:
    def test_user_can_access_branch_all(self, mocker):
        mocker.patch('utils.branching.is_global_user', return_value=True)
        from utils.branching import user_can_access_branch
        assert user_can_access_branch('all', _user()) is True

    def test_user_can_access_branch_invalid(self):
        from utils.branching import user_can_access_branch
        assert user_can_access_branch('bad-id', _user()) is False

    def test_set_active_branch_all_mode(self, app, mocker):
        mocker.patch('utils.branching.is_global_user', return_value=True)
        from utils.branching import set_active_branch, ACTIVE_BRANCH_MODE_SESSION_KEY
        with app.test_request_context():
            from flask import session
            set_active_branch(None, user=_user(), allow_all=True)
            assert session[ACTIVE_BRANCH_MODE_SESSION_KEY] == 'all'

    def test_set_active_branch_denied(self, app, mocker):
        mocker.patch('utils.branching.user_can_access_branch', return_value=False)
        from utils.branching import set_active_branch
        with app.test_request_context():
            with pytest.raises(ValueError):
                set_active_branch(99, user=_user())

    def test_clear_active_branch(self, app):
        from utils.branching import clear_active_branch, ACTIVE_BRANCH_SESSION_KEY
        with app.test_request_context():
            from flask import session
            session[ACTIVE_BRANCH_SESSION_KEY] = 1
            clear_active_branch()
            assert ACTIVE_BRANCH_SESSION_KEY not in session


class TestWarehouseAndStock:
    def test_get_branch_stock_map_empty(self):
        from utils.branching import get_branch_stock_map
        assert get_branch_stock_map(warehouse_ids=[]) == {}

    def test_get_branch_stock_map_values(self, mocker):
        q = MagicMock()
        q.filter.return_value = q
        q.group_by.return_value.all.return_value = [(1, Decimal('5')), (2, None)]
        mocker.patch('utils.branching.db.session.query', return_value=q)
        from utils.branching import get_branch_stock_map
        result = get_branch_stock_map(product_ids=[1], warehouse_ids=[10])
        assert result[1] == Decimal('5')
        assert result[2] == Decimal('0')

    def test_get_product_stock(self, mocker):
        mocker.patch('utils.branching.get_branch_stock_map', return_value={7: Decimal('12')})
        from utils.branching import get_product_stock
        assert get_product_stock(7, warehouse_id=1) == Decimal('12')
        assert get_product_stock(99, warehouse_ids=[1]) == Decimal('0')

    def test_user_can_access_warehouse_false(self):
        from utils.branching import user_can_access_warehouse
        assert user_can_access_warehouse(None, _user()) is False

    def test_ensure_warehouse_access_invalid(self, mocker):
        mocker.patch('utils.branching.get_accessible_warehouses_query').return_value.filter.return_value.first.return_value = None
        from utils.branching import ensure_warehouse_access
        with pytest.raises(ValueError, match='المستودع'):
            ensure_warehouse_access(1, _user())

    def test_get_visible_products_no_branch(self, mocker):
        mocker.patch('utils.branching.apply_tenant_scope', side_effect=lambda q, *a, **k: q)
        mocker.patch('utils.branching.get_accessible_warehouse_ids', return_value=[1])
        mocker.patch('utils.branching.branch_scope_id_for', return_value=None)
        product_q = MagicMock()
        product_q.filter.return_value = product_q
        mocker.patch('models.Product.query', product_q)
        from utils.branching import get_visible_products_query
        get_visible_products_query(_user())

    def test_get_accessible_branches_query_no_branch(self, mocker):
        branch_model = MagicMock()
        q = MagicMock()
        q.filter_by.return_value = q
        q.filter.return_value = q
        branch_model.query = q
        branch_model.is_active = MagicMock()
        branch_model.tenant_id = MagicMock()
        branch_model.id = _Col()
        mocker.patch('utils.branching.Branch', branch_model, create=True)
        mocker.patch('models.Branch', branch_model, create=True)
        mocker.patch('utils.branching.get_active_tenant_id', return_value=1)
        mocker.patch('utils.branching.is_global_user', return_value=False)
        from utils.branching import get_accessible_branches_query
        get_accessible_branches_query(_user(branch_id=None))
        q.filter.assert_called()


class TestBranchingExtended:
    def test_is_global_user_super_admin_callable(self):
        user = _user()
        user.is_super_admin = lambda: True
        user.role.slug = 'cashier'
        from utils.branching import is_global_user
        assert is_global_user(user) is True

    def test_branch_scope_non_global_uses_user_branch(self, mocker):
        mocker.patch('utils.branching.is_global_user', return_value=False)
        mocker.patch('utils.branching.get_active_branch_id', return_value=None)
        from utils.branching import branch_scope_id_for
        assert branch_scope_id_for(_user(branch_id=8)) == 8

    def test_get_accessible_branches(self, mocker):
        branch = MagicMock()
        branch_model = MagicMock()
        q = MagicMock()
        q.filter_by.return_value = q
        q.filter.return_value = q
        q.order_by.return_value.all.return_value = [branch]
        branch_model.query = q
        mocker.patch('models.Branch', branch_model)
        mocker.patch('utils.branching.get_active_tenant_id', return_value=1)
        mocker.patch('utils.branching.is_global_user', return_value=True)
        from utils.branching import get_accessible_branches
        assert get_accessible_branches(_user()) == [branch]

    def test_get_active_branch_id_global_session(self, app, mocker):
        mocker.patch('utils.branching.is_global_user', return_value=True)
        mocker.patch('utils.branching.get_active_branch_mode', return_value='single')
        mocker.patch('utils.branching.user_can_access_branch', return_value=True)
        from utils.branching import get_active_branch_id, ACTIVE_BRANCH_SESSION_KEY
        with app.test_request_context():
            from flask import session
            session[ACTIVE_BRANCH_SESSION_KEY] = 4
            assert get_active_branch_id(_user()) == 4

    def test_get_active_branch(self, mocker):
        mocker.patch('utils.branching.get_active_branch_id', return_value=2)
        mocker.patch('utils.branching.db.session.get', return_value=MagicMock(id=2))
        branch_model = MagicMock()
        mocker.patch('models.Branch', branch_model)
        from utils.branching import get_active_branch
        assert get_active_branch(_user()).id == 2

    def test_set_active_branch_for_regular_user(self, app, mocker):
        mocker.patch('utils.branching.is_global_user', return_value=False)
        mocker.patch('utils.branching.user_can_access_branch', return_value=True)
        from utils.branching import set_active_branch, ACTIVE_BRANCH_SESSION_KEY
        with app.test_request_context():
            from flask import session
            set_active_branch(3, user=_user(branch_id=3))
            assert session[ACTIVE_BRANCH_SESSION_KEY] == 3

    def test_get_accessible_warehouses(self, mocker):
        wh_model = MagicMock()
        q = MagicMock()
        q.filter_by.return_value = q
        q.filter.return_value = q
        q.order_by.return_value.all.return_value = []
        wh_model.query = q
        mocker.patch('models.Warehouse', wh_model)
        mocker.patch('utils.branching.get_active_tenant_id', return_value=1)
        mocker.patch('utils.branching.branch_scope_id_for', return_value=2)
        from utils.branching import get_accessible_warehouses
        assert get_accessible_warehouses(_user()) == []

    def test_ensure_warehouse_access_success(self, mocker):
        warehouse = MagicMock(id=1)
        mocker.patch('utils.branching.get_accessible_warehouses_query').return_value.filter.return_value.first.return_value = warehouse
        wh_model = MagicMock()
        mocker.patch('models.Warehouse', wh_model)
        from utils.branching import ensure_warehouse_access
        assert ensure_warehouse_access(1, _user()) is warehouse

    def test_user_can_access_warehouse_true(self, mocker):
        mocker.patch('utils.branching.get_accessible_warehouses_query').return_value.filter.return_value = MagicMock()
        mocker.patch('utils.branching.db.session.query').return_value.scalar.return_value = True
        wh_model = MagicMock()
        mocker.patch('models.Warehouse', wh_model)
        from utils.branching import user_can_access_warehouse
        assert user_can_access_warehouse(1, _user()) is True

    def test_get_visible_products_empty_warehouses(self, mocker):
        mocker.patch('utils.branching.apply_tenant_scope', side_effect=lambda q, *a, **k: q)
        mocker.patch('utils.branching.get_accessible_warehouse_ids', return_value=[])
        mocker.patch('utils.branching.branch_scope_id_for', return_value=5)
        product_q = MagicMock()
        product_q.filter.return_value = product_q
        mocker.patch('models.Product.query', product_q)
        from utils.branching import get_visible_products_query
        get_visible_products_query(_user())
        product_q.filter.assert_called()

    def test_get_main_branch(self, mocker):
        branch_model = MagicMock()
        q = MagicMock()
        q.filter_by.return_value = q
        q.filter.return_value = q
        q.order_by.return_value.first.return_value = MagicMock(id=1)
        branch_model.query = q
        mocker.patch('models.Branch', branch_model)
        mocker.patch('utils.branching.get_active_tenant_id', return_value=1)
        mocker.patch('utils.branching.current_user', _user())
        from utils.branching import get_main_branch
        assert get_main_branch().id == 1
