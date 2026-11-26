"""Cost price must obey the same role rule on every product lookup API.

``/api/search`` already hid cost from users without ``can_see_costs()``, but
``/api/products`` and ``/api/products/<id>/info`` returned it unconditionally
to anyone holding ``view_reports`` (e.g. an accountant).
"""

from __future__ import annotations

import uuid


class TestCostPriceRedaction:
    @staticmethod
    def _restricted_client(app, db_session, sample_tenant):
        from models import Permission, Role, User

        unique = uuid.uuid4().hex[:8]
        perm = Permission.query.filter_by(code="view_reports").first()
        assert perm is not None
        role = Role(
            name=f"Reader {unique}",
            slug=f"reader-{unique}",
            is_active=True,
            permissions=[perm],
        )
        db_session.add(role)
        db_session.flush()
        user = User(
            username=f"reader-{unique}",
            email=f"reader-{unique}@example.com",
            full_name="Cost reader",
            role_id=role.id,
            tenant_id=sample_tenant.id,
            is_active=True,
        )
        user.set_password("password123")
        db_session.add(user)
        db_session.flush()

        client = app.test_client()
        resp = client.post(
            "/auth/login",
            data={"username": user.username, "password": "password123"},
        )
        assert resp.status_code in (200, 302)
        return client

    def test_super_admin_sees_cost_on_products(self, auth_client, sample_product):
        row = next(
            r for r in auth_client.get("/api/products").get_json()["data"]["results"] if r["id"] == sample_product.id
        )
        assert row["cost_price"] == 50.0

    def test_super_admin_sees_cost_on_product_info(self, auth_client, sample_product):
        data = auth_client.get(f"/api/products/{sample_product.id}/info").get_json()["data"]
        assert data["cost_price"] == 50.0

    def test_reader_does_not_see_cost_on_products(self, app, db_session, sample_tenant, sample_product):
        client = self._restricted_client(app, db_session, sample_tenant)
        row = next(r for r in client.get("/api/products").get_json()["data"]["results"] if r["id"] == sample_product.id)
        assert row["cost_price"] is None

    def test_reader_does_not_see_cost_on_product_info(self, app, db_session, sample_tenant, sample_product):
        client = self._restricted_client(app, db_session, sample_tenant)
        data = client.get(f"/api/products/{sample_product.id}/info").get_json()["data"]
        assert data["cost_price"] is None
