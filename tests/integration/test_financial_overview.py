import pytest
from flask import url_for
from app import create_app
from models import User
from unittest.mock import MagicMock, patch
from werkzeug.exceptions import NotFound

@pytest.fixture(scope='module')
def app():
    app = create_app()
    app.config.update({"TESTING": True, "WTF_CSRF_ENABLED": False})
    return app

@pytest.fixture
def client(app):
    return app.test_client()

@pytest.fixture
def authenticated_owner(app):
    with app.app_context():
        from extensions import db
        from models import Role
        # Use existing platform owner from DB
        owner = User.query.filter_by(is_owner=True, tenant_id=None).first()
        if not owner:
            owner = User.query.filter_by(is_owner=True).first()
        if not owner:
            role = Role.query.filter_by(slug='admin').first()
            owner = User(username='testowner', email='owner@test.com', is_owner=True, tenant_id=None, role_id=role.id if role else None)
            owner.set_password('p')
            db.session.add(owner)
            db.session.commit()
        return owner

def test_financial_overview_valid_owner(client, authenticated_owner):
    with client.session_transaction() as sess:
        from flask_login import login_user
        sess['_user_id'] = str(authenticated_owner.id)
        sess['_fresh'] = True
    
    response = client.get(url_for('owner.financial_overview'))
    assert response.status_code == 200

def test_financial_overview_unauthenticated(client):
    response = client.get(url_for('owner.financial_overview'))
    assert response.status_code == 302

def test_financial_overview_missing_role(client):
    with client.session_transaction() as sess:
        from models import User
        user = User.query.filter_by(username='testuser').first()
        if not user:
            from extensions import db
            from models import Role
            role = Role.query.filter(Role.slug.like('seller')).first()
            user = User(username='testuser', email='user@test.com', is_owner=False, role_id=role.id if role else None)
            user.set_password('p')
            db.session.add(user)
            db.session.commit()
        sess['_user_id'] = str(user.id)
    
    with pytest.raises(NotFound):
        client.get(url_for('owner.financial_overview'))

def test_financial_overview_custom_period(client, authenticated_owner):
    with client.session_transaction() as sess:
        sess['_user_id'] = str(authenticated_owner.id)
        sess['_fresh'] = True
    response = client.get(url_for('owner.financial_overview', period='year'))
    assert response.status_code == 200

def test_financial_overview_no_data(client, authenticated_owner):
    with client.session_transaction() as sess:
        sess['_user_id'] = str(authenticated_owner.id)
        sess['_fresh'] = True
    with patch('routes.owner.db.session.query') as mock_query:
        # Mock empty results for sales, purchases, receipts
        mock_empty = MagicMock()
        mock_empty.filter.return_value.filter.return_value.first.return_value = [0.0, 0.0, 0]
        # Adjusting mock to match the structure in routes/owner.py
        mock_query.return_value.filter.return_value.filter.return_value.first.return_value = [0.0, 0.0, 0]
        response = client.get(url_for('owner.financial_overview'))
        assert response.status_code == 200

def test_financial_overview_invalid_period(client, authenticated_owner):
    with client.session_transaction() as sess:
        sess['_user_id'] = str(authenticated_owner.id)
        sess['_fresh'] = True
    response = client.get(url_for('owner.financial_overview', period='invalid'))
    assert response.status_code == 200 # Should fallback to default 'month'
