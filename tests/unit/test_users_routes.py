"""Unit tests for routes/users.py."""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest

from extensions import db


STRONG_PASSWORD = 'Password1!@#xy'


def _users_routes():
    from routes import users
    return users


@pytest.fixture
def manage_users_permission(db_session):
    from models import Permission
    perm = Permission.query.filter_by(code='manage_users').first()
    if not perm:
        perm = Permission(
            code='manage_users',
            name='Manage Users',
            name_ar='إدارة المستخدمين',
            category='admin',
        )
        db_session.add(perm)
        db_session.flush()
    return perm


@pytest.fixture
def users_manager(db_session, sample_tenant, sample_branch, manage_users_permission):
    from models import Role, User

    unique = uuid.uuid4().hex[:8]
    role = Role.query.filter_by(slug='manager').first()
    if not role:
        role = Role(name='Manager', slug='manager', is_active=True)
        db_session.add(role)
        db_session.flush()
    if manage_users_permission not in role.permissions:
        role.permissions.append(manage_users_permission)
        db_session.flush()

    user = User(
        username=f'mgr_{unique}',
        email=f'mgr_{unique}@example.com',
        full_name='Users Manager',
        role_id=role.id,
        tenant_id=sample_tenant.id,
        branch_id=sample_branch.id,
        is_active=True,
    )
    user.set_password(STRONG_PASSWORD)
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture
def users_client(client, users_manager, sample_tenant):
    """Authenticated client without slow HTTP login (saves ~3s per test)."""
    with client.session_transaction() as sess:
        sess['_user_id'] = str(users_manager.id)
        sess['active_tenant_id'] = sample_tenant.id
    with client:
        yield client


def _tenant_username(tenant, local: str) -> str:
    from utils.username_policy import tenant_username_prefix
    return f'{tenant_username_prefix(tenant)}_{local}'


class TestHelpers:
    def test_clean_branch_id(self):
        users_routes = _users_routes()
        assert users_routes._clean_branch_id(None) is None
        assert users_routes._clean_branch_id('') is None
        assert users_routes._clean_branch_id('None') is None
        assert users_routes._clean_branch_id('12') == 12

    def test_validate_user_branch_missing_role(self, app):
        users_routes = _users_routes()
        with app.app_context():
            with pytest.raises(ValueError, match='الدور'):
                users_routes._validate_user_branch(None, None)

    def test_validate_user_branch_requires_branch(self, app, db_session, users_manager, sample_branch):
        users_routes = _users_routes()
        from models import Role
        seller = Role.query.filter_by(slug='seller').first()
        if not seller:
            seller = Role(name='Seller', slug='seller', is_active=True)
            db_session.add(seller)
            db_session.flush()
        with app.test_request_context():
            from flask_login import login_user
            login_user(users_manager)
            with pytest.raises(ValueError, match='فرع'):
                users_routes._validate_user_branch(seller.id, None)

    def test_validate_user_branch_invalid_branch(self, app, db_session, users_manager):
        users_routes = _users_routes()
        from models import Role
        seller = Role.query.filter_by(slug='seller').first()
        if not seller:
            seller = Role(name='Seller', slug='seller', is_active=True)
            db_session.add(seller)
            db_session.flush()
        with app.test_request_context():
            from flask_login import login_user
            login_user(users_manager)
            with pytest.raises(ValueError, match='خارج نطاق'):
                users_routes._validate_user_branch(seller.id, 999999999)

    def test_available_branches_and_username_example(self, app, users_manager, sample_branch):
        users_routes = _users_routes()
        with app.test_request_context():
            from flask_login import login_user
            login_user(users_manager)
            branches = users_routes._available_branches()
            assert any(b.id == sample_branch.id for b in branches)
            assert '_ahmad' in users_routes._username_example()

    def test_ensure_user_in_scope_blocks_other_branch(self, app, db_session, users_manager, sample_tenant):
        users_routes = _users_routes()
        from models import Branch, Role, User
        other_branch = Branch(
            tenant_id=sample_tenant.id,
            name=f'Other {uuid.uuid4().hex[:6]}',
            code=f'O{uuid.uuid4().hex[:4].upper()}',
            is_active=True,
        )
        db_session.add(other_branch)
        db_session.flush()
        role = Role.query.filter_by(slug='seller').first()
        if not role:
            role = Role(name='Seller', slug='seller', is_active=True)
            db_session.add(role)
            db_session.flush()
        target = User(
            username=f'other_{uuid.uuid4().hex[:8]}',
            email=f'other_{uuid.uuid4().hex[:8]}@example.com',
            role_id=role.id,
            tenant_id=sample_tenant.id,
            branch_id=other_branch.id,
            is_active=True,
        )
        target.set_password('x')
        db_session.add(target)
        db_session.flush()

        with app.test_request_context():
            from flask_login import login_user
            login_user(users_manager)
            with pytest.raises(Exception):
                users_routes._ensure_user_in_scope(target)


class TestIndex:
    def test_index_lists_users(self, users_client):
        resp = users_client.get('/users/')
        assert resp.status_code == 200

    def test_index_search(self, users_client, users_manager):
        resp = users_client.get(f'/users/?search={users_manager.username[:6]}')
        assert resp.status_code == 200


class TestCreate:
    def test_create_get(self, users_client):
        assert users_client.get('/users/create').status_code == 200

    def test_create_missing_role(self, users_client):
        resp = users_client.post('/users/create', data={
            'username': 'x',
            'password': STRONG_PASSWORD,
        })
        assert resp.status_code == 200

    def test_create_reserved_username(self, users_client, sample_tenant, sample_branch):
        from models import Role
        role = Role.query.filter_by(slug='seller').first()
        resp = users_client.post('/users/create', data={
            'role_id': role.id,
            'branch_id': sample_branch.id,
            'username': 'owner',
            'email': 'o@example.com',
            'password': STRONG_PASSWORD,
        })
        assert resp.status_code == 200

    def test_create_invalid_username(self, users_client, sample_tenant, sample_branch):
        from models import Role
        role = Role.query.filter_by(slug='seller').first()
        resp = users_client.post('/users/create', data={
            'role_id': role.id,
            'branch_id': sample_branch.id,
            'username': 'bad',
            'email': 'bad@example.com',
            'password': STRONG_PASSWORD,
        })
        assert resp.status_code == 200

    def test_create_tenant_limit(self, users_client, sample_tenant, sample_branch, mocker):
        from models import Role
        from utils.tenant_limits import TenantLimitError
        role = Role.query.filter_by(slug='seller').first()
        mocker.patch('routes.users.check_users_limit', side_effect=TenantLimitError('users', 1, 1))
        resp = users_client.post('/users/create', data={
            'role_id': role.id,
            'branch_id': sample_branch.id,
            'username': _tenant_username(sample_tenant, f'limit{uuid.uuid4().hex[:6]}'),
            'email': f'limit_{uuid.uuid4().hex[:6]}@example.com',
            'password': STRONG_PASSWORD,
        })
        assert resp.status_code == 200

    def test_create_duplicate_username(self, users_client, sample_tenant, sample_branch, users_manager):
        from models import Role
        role = Role.query.filter_by(slug='seller').first()
        resp = users_client.post('/users/create', data={
            'role_id': role.id,
            'branch_id': sample_branch.id,
            'username': users_manager.username,
            'email': f'dup_{uuid.uuid4().hex[:6]}@example.com',
            'password': STRONG_PASSWORD,
        })
        assert resp.status_code == 200

    def test_create_weak_password(self, users_client, sample_tenant, sample_branch):
        from models import Role
        role = Role.query.filter_by(slug='seller').first()
        resp = users_client.post('/users/create', data={
            'role_id': role.id,
            'branch_id': sample_branch.id,
            'username': _tenant_username(sample_tenant, f'weak{uuid.uuid4().hex[:6]}'),
            'email': f'weak_{uuid.uuid4().hex[:6]}@example.com',
            'password': 'short',
        })
        assert resp.status_code == 200

    def test_create_higher_role_rejected(self, users_client, db_session, sample_branch):
        from models import Role
        dev = Role.query.filter_by(slug='developer').first()
        if not dev:
            dev = Role(name='Developer', slug='developer', is_active=True)
            db_session.add(dev)
            db_session.flush()
        resp = users_client.post('/users/create', data={
            'role_id': dev.id,
            'branch_id': sample_branch.id,
            'username': f'dev_{uuid.uuid4().hex[:8]}',
            'email': f'dev_{uuid.uuid4().hex[:8]}@example.com',
            'password': STRONG_PASSWORD,
        })
        assert resp.status_code == 200

    def test_create_success(self, users_client, sample_tenant, sample_branch, mocker):
        from models import Role, User
        role = Role.query.filter_by(slug='seller').first()
        username = _tenant_username(sample_tenant, f'new{uuid.uuid4().hex[:6]}')
        mocker.patch('routes.users.LoggingCore.log_audit')
        mocker.patch('routes.users.log_mutation')
        resp = users_client.post('/users/create', data={
            'role_id': role.id,
            'branch_id': sample_branch.id,
            'username': username,
            'email': f'{username}@example.com',
            'full_name': 'New User',
            'password': STRONG_PASSWORD,
            'is_active': '1',
        }, follow_redirects=False)
        assert resp.status_code == 302
        assert User.query.filter_by(username=username).first() is not None

    def test_create_exception_handler(self, users_client, sample_tenant, sample_branch, mocker):
        from models import Role
        role = Role.query.filter_by(slug='seller').first()
        mocker.patch('routes.users.assign_tenant_id', side_effect=RuntimeError('boom'))
        resp = users_client.post('/users/create', data={
            'role_id': role.id,
            'branch_id': sample_branch.id,
            'username': _tenant_username(sample_tenant, f'err{uuid.uuid4().hex[:6]}'),
            'email': f'err_{uuid.uuid4().hex[:6]}@example.com',
            'password': STRONG_PASSWORD,
        })
        assert resp.status_code == 200


class TestView:
    def test_view_user(self, users_client, users_manager):
        resp = users_client.get(f'/users/{users_manager.id}')
        assert resp.status_code == 200

    def test_view_other_branch_forbidden(self, users_client, db_session, sample_tenant, users_manager):
        from werkzeug.exceptions import Forbidden
        from models import Branch, Role, User
        branch = Branch(
            tenant_id=sample_tenant.id,
            name=f'Far {uuid.uuid4().hex[:6]}',
            code=f'F{uuid.uuid4().hex[:4].upper()}',
            is_active=True,
        )
        db_session.add(branch)
        db_session.flush()
        role = Role.query.filter_by(slug='seller').first()
        target = User(
            username=f'far_{uuid.uuid4().hex[:8]}',
            email=f'far_{uuid.uuid4().hex[:8]}@example.com',
            role_id=role.id,
            tenant_id=sample_tenant.id,
            branch_id=branch.id,
            is_active=True,
        )
        target.set_password('x')
        db_session.add(target)
        db_session.commit()
        with pytest.raises(Forbidden):
            users_client.get(f'/users/{target.id}')


class TestEdit:
    def test_edit_get(self, users_client, db_session, sample_tenant, sample_branch):
        from models import Role, User
        role = Role.query.filter_by(slug='seller').first()
        target = User(
            username=f'edit_{uuid.uuid4().hex[:8]}',
            email=f'edit_{uuid.uuid4().hex[:8]}@example.com',
            role_id=role.id,
            tenant_id=sample_tenant.id,
            branch_id=sample_branch.id,
            is_active=True,
        )
        target.set_password('x')
        db_session.add(target)
        db_session.commit()
        assert users_client.get(f'/users/{target.id}/edit').status_code == 200

    def test_edit_success(self, users_client, db_session, sample_tenant, sample_branch, mocker):
        from models import Role, User
        role = Role.query.filter_by(slug='seller').first()
        target = User(
            username=f'upd_{uuid.uuid4().hex[:8]}',
            email=f'upd_{uuid.uuid4().hex[:8]}@example.com',
            role_id=role.id,
            tenant_id=sample_tenant.id,
            branch_id=sample_branch.id,
            is_active=True,
        )
        target.set_password('x')
        db_session.add(target)
        db_session.commit()
        mocker.patch('routes.users.LoggingCore.log_audit')
        resp = users_client.post(f'/users/{target.id}/edit', data={
            'email': f'changed_{uuid.uuid4().hex[:6]}@example.com',
            'full_name': 'Changed',
            'role_id': role.id,
            'branch_id': sample_branch.id,
            'is_active': '1',
        }, follow_redirects=False)
        assert resp.status_code == 302

    def test_edit_weak_password(self, users_client, db_session, sample_tenant, sample_branch):
        from models import Role, User
        role = Role.query.filter_by(slug='seller').first()
        target = User(
            username=f'pwd_{uuid.uuid4().hex[:8]}',
            email=f'pwd_{uuid.uuid4().hex[:8]}@example.com',
            role_id=role.id,
            tenant_id=sample_tenant.id,
            branch_id=sample_branch.id,
            is_active=True,
        )
        target.set_password('x')
        db_session.add(target)
        db_session.commit()
        resp = users_client.post(f'/users/{target.id}/edit', data={
            'email': target.email,
            'role_id': role.id,
            'branch_id': sample_branch.id,
            'new_password': 'weak',
            'is_active': '1',
        })
        assert resp.status_code == 200

    def test_edit_higher_role_rejected(self, users_client, db_session, sample_tenant, sample_branch):
        from models import Role, User
        seller = Role.query.filter_by(slug='seller').first()
        target = User(
            username=f'seller_{uuid.uuid4().hex[:8]}',
            email=f'seller_{uuid.uuid4().hex[:8]}@example.com',
            role_id=seller.id,
            tenant_id=sample_tenant.id,
            branch_id=sample_branch.id,
            is_active=True,
        )
        target.set_password('x')
        db_session.add(target)
        db_session.flush()
        dev = Role.query.filter_by(slug='developer').first()
        if not dev:
            dev = Role(name='Developer', slug='developer', is_active=True)
            db_session.add(dev)
            db_session.flush()
        db_session.commit()
        resp = users_client.post(f'/users/{target.id}/edit', data={
            'email': target.email,
            'role_id': dev.id,
            'branch_id': sample_branch.id,
            'is_active': '1',
        })
        assert resp.status_code == 200

    def test_edit_exception(self, users_client, db_session, sample_tenant, sample_branch, mocker):
        from models import Role, User
        role = Role.query.filter_by(slug='seller').first()
        target = User(
            username=f'exc_{uuid.uuid4().hex[:8]}',
            email=f'exc_{uuid.uuid4().hex[:8]}@example.com',
            role_id=role.id,
            tenant_id=sample_tenant.id,
            branch_id=sample_branch.id,
            is_active=True,
        )
        target.set_password('x')
        db_session.add(target)
        db_session.commit()
        mocker.patch.object(db.session, 'commit', side_effect=RuntimeError('db'))
        resp = users_client.post(f'/users/{target.id}/edit', data={
            'email': target.email,
            'role_id': role.id,
            'branch_id': sample_branch.id,
            'is_active': '1',
        })
        assert resp.status_code == 200


class TestToggleActive:
    def test_toggle_active(self, users_client, db_session, sample_tenant, sample_branch, mocker):
        from models import Role, User
        role = Role.query.filter_by(slug='seller').first()
        target = User(
            username=f'tog_{uuid.uuid4().hex[:8]}',
            email=f'tog_{uuid.uuid4().hex[:8]}@example.com',
            role_id=role.id,
            tenant_id=sample_tenant.id,
            branch_id=sample_branch.id,
            is_active=True,
        )
        target.set_password('x')
        db_session.add(target)
        db_session.commit()
        mocker.patch('routes.users.LoggingCore.log_audit')
        resp = users_client.post(f'/users/{target.id}/toggle-active', follow_redirects=False)
        assert resp.status_code == 302
        db.session.refresh(target)
        assert target.is_active is False


class TestDelete:
    def test_delete_self_forbidden(self, users_client, users_manager):
        resp = users_client.post(f'/users/{users_manager.id}/delete', follow_redirects=False)
        assert resp.status_code == 302

    def test_delete_higher_role_forbidden(self, users_client, db_session, sample_tenant, sample_branch):
        from models import Role, User
        dev = Role.query.filter_by(slug='developer').first()
        if not dev:
            dev = Role(name='Developer', slug='developer', is_active=True)
            db_session.add(dev)
            db_session.flush()
        target = User(
            username=f'devu_{uuid.uuid4().hex[:8]}',
            email=f'devu_{uuid.uuid4().hex[:8]}@example.com',
            role_id=dev.id,
            tenant_id=sample_tenant.id,
            branch_id=sample_branch.id,
            is_active=True,
        )
        target.set_password('x')
        db_session.add(target)
        db_session.commit()
        resp = users_client.post(f'/users/{target.id}/delete', follow_redirects=False)
        assert resp.status_code == 302

    def test_delete_deactivates_when_has_sales(self, users_client, db_session, sample_tenant, sample_branch, mocker):
        from unittest.mock import MagicMock
        from models import Role, User
        role = Role.query.filter_by(slug='seller').first()
        target = User(
            username=f'sales_{uuid.uuid4().hex[:8]}',
            email=f'sales_{uuid.uuid4().hex[:8]}@example.com',
            role_id=role.id,
            tenant_id=sample_tenant.id,
            branch_id=sample_branch.id,
            is_active=True,
        )
        target.set_password('x')
        db_session.add(target)
        db_session.commit()
        target_id = target.id
        sale_q = MagicMock()
        sale_q.filter.return_value = sale_q
        sale_q.count.return_value = 1
        sale_mock = MagicMock()
        sale_mock.query.filter_by.return_value = sale_q
        mocker.patch('models.Sale', sale_mock)
        audit = mocker.patch('routes.users.LoggingCore.log_audit')
        mocker.patch.object(db.session, 'commit', return_value=None)
        assert users_client.post(f'/users/{target_id}/delete', follow_redirects=False).status_code == 302
        audit.assert_called_once_with('deactivate', 'users', target_id)

    def test_delete_hard_when_no_sales(self, users_client, db_session, sample_tenant, sample_branch, mocker):
        from unittest.mock import MagicMock
        from models import Role, User
        role = Role.query.filter_by(slug='seller').first()
        target = User(
            username=f'del_{uuid.uuid4().hex[:8]}',
            email=f'del_{uuid.uuid4().hex[:8]}@example.com',
            role_id=role.id,
            tenant_id=sample_tenant.id,
            branch_id=sample_branch.id,
            is_active=True,
        )
        target.set_password('x')
        db_session.add(target)
        db_session.commit()
        target_id = target.id
        sale_cls = mocker.patch('models.Sale')
        sale_q = MagicMock()
        sale_q.filter.return_value = sale_q
        sale_q.count.return_value = 0
        sale_cls.query.filter_by.return_value = sale_q
        audit = mocker.patch('routes.users.LoggingCore.log_audit')
        mocker.patch.object(db.session, 'commit', return_value=None)
        resp = users_client.post(f'/users/{target_id}/delete', follow_redirects=False)
        assert resp.status_code == 302
        audit.assert_called_once_with('delete', 'users', target_id)

    def test_delete_exception(self, users_client, db_session, sample_tenant, sample_branch, mocker):
        from models import Role, User
        role = Role.query.filter_by(slug='seller').first()
        target = User(
            username=f'delf_{uuid.uuid4().hex[:8]}',
            email=f'delf_{uuid.uuid4().hex[:8]}@example.com',
            role_id=role.id,
            tenant_id=sample_tenant.id,
            branch_id=sample_branch.id,
            is_active=True,
        )
        target.set_password('x')
        db_session.add(target)
        db_session.commit()
        mocker.patch.object(db.session, 'commit', side_effect=RuntimeError('db'))
        resp = users_client.post(f'/users/{target.id}/delete', follow_redirects=False)
        assert resp.status_code == 302
