import json
from unittest.mock import patch, MagicMock
import pytest

class TestPosIndex:
    def test_pos_index_requires_login(self, client):
        resp = client.get("/pos/", follow_redirects=False)
        assert resp.status_code in (302, 401, 403)
    def test_pos_index_loads_for_authenticated_user(self, app, client):
        with app.test_request_context():
            from flask_login import login_user
            from models.user import User
            user = User.query.filter_by(username="owner").first()
            if user:
                with client.session_transaction() as sess:
                    sess["_user_id"] = str(user.id)
                    sess["_fresh"] = True
                resp = client.get("/pos/")
                assert resp.status_code == 200
                assert b"POS" in resp.data or "نقطة البيع".encode("utf-8") in resp.data

class TestPosApiProducts:
    def test_api_products_requires_auth(self, client):
        resp = client.get("/pos/api/products?q=test")
        assert resp.status_code in (302, 401, 403)

class TestPosApiProductLookup:
    def test_api_product_lookup_requires_auth(self, client):
        resp = client.get("/pos/api/product?code=123")
        assert resp.status_code in (302, 401, 403)
    def test_api_product_lookup_missing_code(self, app, client):
        with app.test_request_context():
            from models.user import User
            user = User.query.filter_by(username="owner").first()
            if user:
                with client.session_transaction() as sess:
                    sess["_user_id"] = str(user.id)
                    sess["_fresh"] = True
                resp = client.get("/pos/api/product")
                assert resp.status_code == 400
                data = json.loads(resp.data)
                assert data["success"] is False

class TestPosApiCustomers:
    def test_api_customers_requires_auth(self, client):
        resp = client.get("/pos/api/customers?q=test")
        assert resp.status_code in (302, 401, 403)

class TestPosApiWalkin:
    def test_api_walkin_requires_auth(self, client):
        resp = client.get("/pos/api/walkin-customer")
        assert resp.status_code in (302, 401, 403)

class TestPosApiCheckout:
    def test_api_checkout_requires_auth(self, client):
        resp = client.post("/pos/api/checkout", json={})
        assert resp.status_code in (302, 401, 403)
    def test_api_checkout_rejects_non_json(self, app, client):
        with app.test_request_context():
            from models.user import User
            user = User.query.filter_by(username="owner").first()
            if user:
                with client.session_transaction() as sess:
                    sess["_user_id"] = str(user.id)
                    sess["_fresh"] = True
                resp = client.post("/pos/api/checkout", data="not-json")
                assert resp.status_code == 415
                data = json.loads(resp.data)
                assert data["success"] is False
    def test_api_checkout_rejects_empty_cart(self, app, client):
        with app.test_request_context():
            from models.user import User
            user = User.query.filter_by(username="owner").first()
            if user:
                with client.session_transaction() as sess:
                    sess["_user_id"] = str(user.id)
                    sess["_fresh"] = True
                resp = client.post(
                    "/pos/api/checkout",
                    json={"lines": []},
                    headers={"Content-Type": "application/json"},
                )
                assert resp.status_code == 400
                data = json.loads(resp.data)
                assert data["success"] is False
                assert "cart" in data["error"].lower() or "empty" in data["error"].lower() or "add" in data["error"].lower()
