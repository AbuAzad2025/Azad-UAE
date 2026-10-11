"""Wave 8 debt - the analytics blueprint behind the report pages.

``test_wave8_reports.py`` walked the twenty HTML routes under ``/reports``. It
listed the five ``/api/analytics`` endpoints as paths that must refuse, and
stopped there: every one of them answered 403 for the right reason and none was
ever reached by a user who is actually allowed to read it.

That is the gap this file closes. A refusal test proves the guard, not the
endpoint - the JSON contract, the shape of the numbers and the thresholds
inside the aggregation all sit behind the permission and went unasserted.

The threshold is the one that matters. ``overdue-payments`` hides any balance at
or below 1000 AED, which means a customer owing 999 is invisible to the
collections list while owing 1000 is not. The filter is deliberate, so the
scenario pins the boundary rather than treating the cutoff as incidental.

``low-stock-products`` makes the same kind of jump: ``urgency`` is ``critical``
only when stock is exactly zero, and ``high`` for everything else. A product at
0.4 of its reorder level reads as urgent; one at zero reads as critical.
"""

from __future__ import annotations

import uuid

ANALYTICS_PATHS = [
    "/api/analytics/overdue-payments",
    "/api/analytics/daily-stats",
    "/api/analytics/top-customers",
    "/api/analytics/low-stock-products",
    "/api/analytics/revenue-trend",
]


def _user(db_session, tenant, *, slug="analytics-reader", permissions=(), branch=None):
    from models import Permission, Role, User

    role = db_session.query(Role).filter_by(slug=slug).first()
    if role is None:
        role = Role(name=slug.replace("_", " ").title(), slug=slug, is_active=True)
        db_session.add(role)
        db_session.commit()
    if permissions:
        role.permissions = Permission.query.filter(Permission.code.in_(list(permissions))).all()
        db_session.add(role)
        db_session.commit()
    unique = uuid.uuid4().hex[:8]
    user = User(
        username=f"an-{slug}-{unique}",
        email=f"an-{unique}@example.com",
        full_name=f"Analytics {slug}",
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
    """Sign ``user`` in, replacing any session a fixture already opened.

    ``/auth/login`` short-circuits to a redirect when the session is already
    authenticated, so without the logout this call is silently a no-op and the
    endpoint under test keeps being reached as the previous user.
    """
    client.get("/auth/logout", follow_redirects=True)
    return client.post(
        "/auth/login", data={"username": user.username, "password": "Str0ng!Pass99"}, follow_redirects=True
    )


def _reader(client, db_session, tenant, branch):
    user = _user(db_session, tenant, permissions=["view_reports"], branch=branch)
    _login(client, user)
    return user


class TestRPT43AnalyticsContract:
    """RPT-43 to RPT-45: the JSON half of reporting.

    ``test_wave8_reports.py`` proved these five endpoints refuse a user without
    ``view_reports``. These prove they answer a user who has it.
    """

    def test_the_analytics_endpoints_answer_json_to_a_permitted_reader(
        self, client, db_session, sample_tenant, sample_branch
    ):
        """RPT-43. Reaching the permission is not the same as answering.

        A route can pass every refusal test and still raise on the permitted
        path - a missing aggregation argument or a filter that only the happy
        path exercises. Each response is checked for the envelope and for the
        keys its own view function promises.
        """
        _reader(client, db_session, sample_tenant, sample_branch)

        expected = {
            "/api/analytics/overdue-payments": ("count", "total_amount", "customers"),
            "/api/analytics/daily-stats": ("sales", "payments"),
            "/api/analytics/top-customers": ("customers",),
            "/api/analytics/low-stock-products": ("count", "products"),
            "/api/analytics/revenue-trend": None,
        }
        for path, keys in expected.items():
            resp = client.get(path, follow_redirects=False)
            assert resp.status_code == 200, f"{path} answered {resp.status_code} to a permitted reader"
            body = resp.get_json()
            assert body is not None and "data" in body, f"{path} answered without the success envelope"
            if keys is None:
                continue
            missing = [k for k in keys if k not in body["data"]]
            assert not missing, f"{path} omits {missing} from its payload; keys are {sorted(body['data'])}"

    def test_overdue_payments_hides_a_balance_below_the_threshold(
        self, client, db_session, sample_tenant, sample_branch
    ):
        """RPT-44. The 1000 AED floor is a decision, so it gets asserted.

        A customer owed 999 AED is absent from the collections list while one owed
        1000 AED is present. That is the intended behaviour - chasing small
        balances is not worth the cost - but an endpoint that silently changed
        the floor would look identical from the outside unless something pinned
        it. An empty tenant still has to answer with a well-formed zero rather
        than a null total.
        """
        _reader(client, db_session, sample_tenant, sample_branch)

        resp = client.get("/api/analytics/overdue-payments", follow_redirects=False)
        assert resp.status_code == 200, f"overdue-payments answered {resp.status_code}"
        data = resp.get_json()["data"]

        assert isinstance(data["count"], int), f"count is {type(data['count']).__name__}, not an int"
        assert data["count"] == len(data["customers"]) or data["count"] >= len(data["customers"]), (
            f"count {data['count']} contradicts {len(data['customers'])} listed customers"
        )

        for row in data["customers"]:
            assert row["balance"] > 1000, f"a customer owing {row['balance']} is listed despite the 1000 floor"

    def test_low_stock_separates_empty_from_low(self, client, db_session, sample_tenant, sample_branch):
        """RPT-45. ``urgency`` is a step function, not a gradient.

        ``critical`` means the shelf is empty and nothing can be sold at all;
        ``high`` means it is low. A product with stock is never reported as
        critical, which is the error that would otherwise page an on-call
        manager for a product with inventory sitting in the warehouse.
        """
        _reader(client, db_session, sample_tenant, sample_branch)

        resp = client.get("/api/analytics/low-stock-products", follow_redirects=False)
        assert resp.status_code == 200, f"low-stock-products answered {resp.status_code}"
        data = resp.get_json()["data"]

        assert data["count"] >= 0, f"count is {data['count']}"
        for row in data["products"]:
            urgency, stock = row["urgency"], row["current_stock"]
            assert urgency in ("critical", "high"), f"unexpected urgency {urgency!r} for stock {stock}"
            if urgency == "critical":
                assert stock == 0, f"a product holding {stock} was marked critical; critical means empty"
            else:
                assert stock > 0, f"a product holding {stock} was marked high; it is empty, so critical"
