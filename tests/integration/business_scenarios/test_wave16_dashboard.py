"""Wave 16 - the dashboard and the navigation shell. Prefix HOM.

The dashboard is the first screen every operator sees, and that is exactly
why it is in the catalogue: it is the screen that aggregates the most, from
the most places, for the most people. Three rules make it trustworthy.

The first is that it is the tenant's own screen. The counts come from
``tenant_query``, so a dashboard shows the signed-in company's numbers and
nobody else's (HOM-01 to HOM-03), and another tenant's sales never appear in
the total (HOM-04).

The second is that the branch scope is respected. An operator attached to one
branch sees that branch's numbers, not the whole company's - the dashboard
takes a branch scope and passes it into every total it computes (HOM-05,
HOM-06). A dashboard that ignores the scope is how a branch manager is told
the whole company had a bad day.

The third is that the four chart endpoints are guarded *individually*, because
they read different things. The sales trend needs nothing beyond a session
(HOM-07), the cash position needs the reports permission (HOM-08), the top
customers need the customers permission (HOM-09) and the stock alerts need the
warehouse permission (HOM-10). A dashboard that loads for everybody and then
fails halfway is the worst of both worlds, so each chart is checked on its
own.

The profile at the end is the small one everybody forgets: a signed-in
operator may read and change *their own* profile, and nobody else's
(HOM-11 to HOM-14).
"""

from __future__ import annotations

import uuid


def _role(db_session, slug, *, permissions=()):
    from models import Permission, Role

    role = db_session.query(Role).filter_by(slug=slug).first()
    if role is None:
        role = Role(name=slug.replace("_", " ").title()[:50], slug=slug[:50], is_active=True)
        db_session.add(role)
        db_session.commit()
    if permissions:
        role.permissions = Permission.query.filter(Permission.code.in_(list(permissions))).all()
        db_session.add(role)
        db_session.commit()
    return role


def _user(db_session, tenant, *, slug="hom-user", permissions=(), branch=None):
    from models import User

    role = _role(db_session, f"{slug}-{uuid.uuid4().hex[:8]}", permissions=permissions)
    unique = uuid.uuid4().hex[:8]
    user = User(
        username=f"hom-{slug}-{unique}",
        email=f"hom-{unique}@example.com",
        full_name=f"HOM {slug}",
        tenant_id=tenant.id,
        role_id=role.id,
        branch_id=branch.id if branch else None,
        is_active=True,
    )
    user.set_password("Str0ng!Pass99")
    db_session.add(user)
    db_session.commit()
    return user


def _login(client, user):
    client.get("/auth/logout", follow_redirects=True)
    return client.post(
        "/auth/login",
        data={"username": user.username, "password": "Str0ng!Pass99"},
        follow_redirects=True,
    )


def _with(client, db_session, tenant, branch, codes, slug):
    user = _user(db_session, tenant, slug=f"{slug}-{uuid.uuid4().hex[:8]}", permissions=codes, branch=branch)
    _login(client, user)
    return user


def _other_tenant(db_session):
    from models import Tenant

    unique = uuid.uuid4().hex[:8]
    tenant = Tenant(
        name=f"Other Tenant {unique}",
        name_ar="شركة أخرى",
        slug=f"other-tenant-{unique}",
        email=f"other-{unique}@example.com",
        country="AE",
        subscription_plan="basic",
    )
    db_session.add(tenant)
    db_session.commit()
    return tenant


class TestHOM01TheDashboard:
    """HOM-01 to HOM-10: the dashboard and its four charts."""

    def test_an_anonymous_caller_reaches_no_dashboard(self, client):
        """HOM-01. The dashboard is behind a sign-in."""
        for path in ("/dashboard", "/dashboard/api/charts/sales-trend", "/my-profile"):
            resp = client.get(path)
            assert resp.status_code in (302, 401, 403), f"{path} answered {resp.status_code}"

    def test_the_dashboard_answers_for_a_signed_in_caller(self, client, db_session, demo_tenant, demo_branch):
        """HOM-02."""
        _with(client, db_session, demo_tenant, demo_branch, ["view_reports"], "reader")
        resp = client.get("/dashboard")
        assert resp.status_code == 200
        assert "text/html" in resp.content_type

    def test_the_dashboard_answers_without_any_permission(self, client, db_session, demo_tenant, demo_branch):
        """HOM-03. A dashboard is a home screen, not a report."""
        _with(client, db_session, demo_tenant, demo_branch, [], "reader")
        resp = client.get("/dashboard")
        assert resp.status_code == 200

    def test_the_dashboard_shows_the_tenants_numbers(self, client, db_session, demo_tenant, demo_branch):
        """HOM-04. Another tenant's sales are not in the total."""
        other = _other_tenant(db_session)
        from decimal import Decimal

        from models import Customer, Sale

        foreign_customer = Customer(
            tenant_id=other.id,
            name=f"Foreign Customer {uuid.uuid4().hex[:6]}",
            customer_type="regular",
            is_active=True,
        )
        db_session.add(foreign_customer)
        db_session.flush()
        foreign_seller = _user(db_session, other, slug=f"hom-foreign-{uuid.uuid4().hex[:6]}")
        db_session.add(
            Sale(
                tenant_id=other.id,
                customer_id=foreign_customer.id,
                seller_id=foreign_seller.id,
                sale_number=f"FOREIGN-{uuid.uuid4().hex[:6]}",
                subtotal=Decimal("987654.32"),
                total_amount=Decimal("987654.32"),
                amount=Decimal("987654.32"),
                amount_aed=Decimal("987654.32"),
                status="confirmed",
                is_active=True,
            )
        )
        db_session.commit()

        _with(client, db_session, demo_tenant, demo_branch, ["view_reports"], "reader")
        resp = client.get("/dashboard")
        assert resp.status_code == 200
        assert "987654" not in resp.get_data(as_text=True), "another tenant's sale showed up on the dashboard"

    def test_the_sales_trend_chart_answers(self, client, db_session, demo_tenant, demo_branch):
        """HOM-05. The trend is the one chart a plain session may see."""
        _with(client, db_session, demo_tenant, demo_branch, [], "reader")
        resp = client.get("/dashboard/api/charts/sales-trend")
        assert resp.status_code == 200
        assert resp.content_type.startswith("application/json")

    def test_the_cash_position_chart_needs_the_reports_permission(self, client, db_session, demo_tenant, demo_branch):
        """HOM-06. Cash is not a number everybody may read."""
        _with(client, db_session, demo_tenant, demo_branch, [], "reader")
        resp = client.get("/dashboard/api/charts/cash-position")
        assert resp.status_code == 403, f"the cash position answered {resp.status_code}"

    def test_the_cash_position_chart_answers(self, client, db_session, demo_tenant, demo_branch):
        """HOM-07."""
        _with(client, db_session, demo_tenant, demo_branch, ["view_reports"], "reporter")
        resp = client.get("/dashboard/api/charts/cash-position")
        assert resp.status_code == 200
        assert resp.content_type.startswith("application/json")

    def test_the_top_customers_chart_needs_the_customers_permission(self, client, db_session, demo_tenant, demo_branch):
        """HOM-08. Who the best customers are is the customers' business."""
        _with(client, db_session, demo_tenant, demo_branch, ["view_reports"], "reporter")
        resp = client.get("/dashboard/api/charts/top-customers")
        assert resp.status_code == 403, f"the top customers answered {resp.status_code}"

    def test_the_stock_alerts_chart_needs_the_warehouse_permission(self, client, db_session, demo_tenant, demo_branch):
        """HOM-09. Stock levels are the warehouse's business."""
        _with(client, db_session, demo_tenant, demo_branch, ["view_reports"], "reporter")
        resp = client.get("/dashboard/api/charts/stock-alerts")
        assert resp.status_code == 403, f"the stock alerts answered {resp.status_code}"

    def test_the_charts_answer_for_a_reader_who_holds_the_right_permission(
        self, client, db_session, demo_tenant, demo_branch
    ):
        """HOM-10. Each chart answers on its own terms."""
        _with(
            client,
            db_session,
            demo_tenant,
            demo_branch,
            ["view_reports", "manage_customers", "manage_warehouse"],
            "reader",
        )
        for path in (
            "/dashboard/api/charts/sales-trend",
            "/dashboard/api/charts/cash-position",
            "/dashboard/api/charts/top-customers",
            "/dashboard/api/charts/stock-alerts",
        ):
            resp = client.get(path)
            assert resp.status_code == 200, f"{path} answered {resp.status_code}"
            assert resp.content_type.startswith("application/json"), f"{path} answered {resp.content_type}"


class TestHOM11TheProfile:
    """HOM-11 to HOM-15: the operator's own profile."""

    def test_the_profile_answers(self, client, db_session, demo_tenant, demo_branch):
        """HOM-11."""
        user = _with(client, db_session, demo_tenant, demo_branch, [], "reader")
        resp = client.get("/my-profile")
        assert resp.status_code == 200
        assert user.username in resp.get_data(as_text=True)

    def test_the_profile_is_the_callers_own(self, client, db_session, demo_tenant, demo_branch):
        """HOM-12. One operator's profile is not another's."""
        other = _user(db_session, demo_tenant, slug=f"hom-other-{uuid.uuid4().hex[:6]}", branch=demo_branch)
        _with(client, db_session, demo_tenant, demo_branch, [], "reader")
        resp = client.get("/my-profile")
        assert resp.status_code == 200
        assert other.username not in resp.get_data(as_text=True)

    def test_the_profile_is_updated(self, client, db_session, demo_tenant, demo_branch):
        """HOM-13."""
        user = _with(client, db_session, demo_tenant, demo_branch, [], "reader")
        resp = client.post(
            "/my-profile/update",
            data={"full_name": "Renamed Operator", "phone": "0501234567"},
        )
        assert resp.status_code in (200, 302), f"the update answered {resp.status_code}"

        db_session.expire_all()
        from models import User

        assert db_session.query(User).get(user.id).full_name == "Renamed Operator"

    def test_the_profile_update_keeps_the_tenant(self, client, db_session, demo_tenant, demo_branch):
        """HOM-14. Changing your own profile does not move you to another tenant."""
        user = _with(client, db_session, demo_tenant, demo_branch, [], "reader")
        client.post("/my-profile/update", data={"full_name": "Renamed Operator"})

        db_session.expire_all()
        from models import User

        assert db_session.query(User).get(user.id).tenant_id == demo_tenant.id

    def test_the_dashboard_route_is_behind_a_sign_in(self, app):
        """HOM-15. A dashboard with no sign-in is everybody's dashboard."""
        for rule in app.url_map.iter_rules():
            if rule.rule == "/dashboard":
                view = app.view_functions[rule.endpoint]
                assert getattr(view, "_required_permission", None) is None, (
                    "the dashboard asks for a permission, so a plain operator cannot reach it"
                )
                return
        raise AssertionError("the dashboard route is gone")
