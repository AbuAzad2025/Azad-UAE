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
        # Assuming there is a way to get or create an owner user
        owner = User.query.filter_by(is_owner=True).first()
        if not owner:
             # Create a dummy owner if none exists
             owner = User(username='testowner', is_owner=True)
             from extensions import db
             db.session.add(owner)
             db.session.commit()
        return owner

def test_financial_overview_valid_owner(client, authenticated_owner):
    with client.session_transaction() as sess:
        sess['_user_id'] = str(authenticated_owner.id)
        sess['_fresh'] = True
    
    response = client.get(url_for('owner.financial_overview'))
    assert response.status_code == 200
    assert 'النظرة المالية الشاملة' in response.text

def test_financial_overview_unauthenticated(client):
    response = client.get(url_for('owner.financial_overview'))
    assert response.status_code == 302

def test_financial_overview_missing_role(client):
    with client.session_transaction() as sess:
        # Create a user without owner role
        from models import User
        user = User.query.filter_by(is_owner=False).first()
        if not user:
            from extensions import db
            user = User(username='testuser', is_owner=False)
            db.session.add(user)
            db.session.commit()
        sess['_user_id'] = str(user.id)
    
    # The current implementation uses @owner_required decorator, which calls abort(404)
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
