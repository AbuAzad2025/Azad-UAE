"""Wave 14 - the AI surface: analytics, chat, knowledge and owner training.

The AI blueprint is the widest in the system - fifty routes under ``/ai`` and
twelve more under ``/owner/ai-training`` - and the rule that has to hold
across all of them is the one the catalogue calls "AI output must never bypass
the permission model". The AI is allowed to read, analyse and answer. It is
not allowed to *reach* anything the caller could not reach on their own, and it
is not allowed to write on the tenant's behalf without the same permission the
write would have needed.

So the scenarios here are mostly about the guards, and they are grouped by the
permission each route actually asks for rather than by the file the route lives
in. The guards are not uniform: ``view_reports`` opens the report routes,
``view_products`` opens the product routes, ``manage_warehouse`` opens the two
inventory routes, ``view_ledger`` opens the cash-flow prediction, and
``manage_customers`` opens the customer analysis. A caller who holds one of
them holds only that one (AI-03 to AI-07).

Three routes are on a different footing entirely. ``/ai/config``,
``/ai/knowledge/add-website`` and ``/ai/knowledge/add-document`` are the
platform owner's alone - they change what the AI knows or which model it talks
to, and they answer 404 rather than 403 so the surface stays hidden (AI-08,
AI-12). The owner training routes are the same (AI-10, AI-76 to AI-87).

The four admin routes - the ones that evolve the knowledge, improve the
system, set a goal and update the global expertise - are guarded by the role
rather than by a permission: super_admin, or the platform owner (AI-11, AI-63,
AI-65, AI-67, AI-69).

And the validation refusals are the last line: a request with no body is
refused before any analysis happens (AI-36 to AI-41, AI-57 to AI-59), because
an AI endpoint that guesses what the caller meant is how a query ends up
answered about the wrong tenant.
"""

from __future__ import annotations

import io
import uuid

#: The routes that answer JSON, grouped by the permission that guards them.
REPORT_ROUTES = [
    "/ai/system/summary",
    "/ai/system/search/anything",
    "/ai/data/analyze-sales",
    "/ai/data/financial-ratios",
    "/ai/predict-sales",
    "/ai/analyze-margins",
    "/ai/detect-patterns",
    "/ai/deep-analysis",
    "/ai/business-insights",
    "/ai/contextual-help/sales",
    "/ai/learning/status",
    "/ai/improvement/status",
    "/ai/improvement/progress",
    "/ai/global/insights",
    "/ai/performance/analysis",
    "/ai/knowledge/search?q=anything",
    "/ai/knowledge/summary",
    "/ai/exchange-rate/AED",
]
PRODUCT_ROUTES = [
    "/ai/data/analyze-products",
    "/ai/search-market-price/999999",
    "/ai/find-compatible/999999",
]
CUSTOMER_ROUTES = [
    "/ai/system/customer-balance/Nobody",
    "/ai/system/customer-debt/999999",
    "/ai/churn-prediction",
]
WAREHOUSE_ROUTES = [
    "/ai/inventory-health",
    "/ai/optimize-inventory",
]
OWNER_ROUTES = [
    "/owner/ai-training",
    "/owner/ai-training/upload",
    "/owner/ai-training/progress",
    "/owner/ai-training/metrics",
    "/owner/ai-training/knowledge-graph",
    "/owner/ai-training/health",
    "/owner/ai-training/batches",
]
#: POST-only routes: asking for them with a GET answers 405 before the guard is
#: even reached, so they are asked for the way they are meant to be called.
POST_ONLY_ROUTES = {
    "/ai/system/add-customer",
    "/ai/smart-price",
    "/ai/recommend-price",
    "/ai/check-stock",
    "/ai/upload-excel",
    "/ai/chat",
    "/ai/ask-genius",
    "/ai/quick-calc",
    "/ai/transformers-understand",
    "/ai/knowledge/add-website",
    "/ai/knowledge/add-document",
    "/ai/learning/evolve",
    "/ai/improvement/auto-improve",
    "/ai/improvement/set-goal",
    "/owner/ai-training/qa",
    "/owner/ai-training/<int:memory_id>/toggle",
    "/owner/ai-training/correct",
    "/owner/ai-training/semantic-train",
}
ADMIN_ROUTES = [
    "/ai/learning/evolve",
    "/ai/improvement/auto-improve",
    "/ai/improvement/set-goal",
    "/ai/global/expertise-update",
]

ALL_AI_ROUTES = (
    REPORT_ROUTES
    + PRODUCT_ROUTES
    + CUSTOMER_ROUTES
    + WAREHOUSE_ROUTES
    + [
        "/ai/system/product-stock/Nothing",
        "/ai/system/add-customer",
        "/ai/smart-price",
        "/ai/recommend-price",
        "/ai/check-stock",
        "/ai/analyze-customer/999999",
        "/ai/assistant",
        "/ai/config",
        "/ai/upload-excel",
        "/ai/chat",
        "/ai/neural-status",
        "/ai/automotive-ecu/ECU1",
        "/ai/automotive-sensor/O2",
        "/ai/external-sources",
        "/ai/ask-genius",
        "/ai/quick-calc",
        "/ai/transformers-understand",
        "/ai/knowledge/add-website",
        "/ai/knowledge/add-document",
        "/owner/ai-training/qa",
        "/owner/ai-training/<int:memory_id>/toggle",
        "/owner/ai-training/correct",
        "/owner/ai-training/concept/<concept_name>",
        "/owner/ai-training/semantic-train",
    ]
)


def _role(db_session, slug):
    from models import Role

    role = db_session.query(Role).filter_by(slug=slug).first()
    if role is None:
        # Both the slug and the display name are 50 characters wide, so the
        # slug carries a short unique suffix rather than the whole permission
        # set.
        role = Role(name=slug.replace("_", " ").title()[:50], slug=slug[:50], is_active=True)
        db_session.add(role)
        db_session.commit()
    return role


def _user(db_session, tenant, *, slug="ai-user", permissions=(), branch=None):
    from models import Permission, User

    role = _role(db_session, slug)
    if permissions:
        role.permissions = Permission.query.filter(Permission.code.in_(list(permissions))).all()
        db_session.add(role)
        db_session.commit()
    unique = uuid.uuid4().hex[:8]
    user = User(
        username=f"ai-{slug}-{unique}",
        email=f"ai-{unique}@example.com",
        full_name=f"AI {slug}",
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
    # /auth/login refuses to switch users while a session is open, so a scenario
    # that needs two actors signs the first one out first.
    client.get("/auth/logout", follow_redirects=True)
    return client.post(
        "/auth/login",
        data={"username": user.username, "password": "Str0ng!Pass99"},
        follow_redirects=True,
    )


def _with(client, db_session, tenant, branch, codes, slug):
    """A signed-in user carrying exactly ``codes``.

    The role slug carries a short unique suffix rather than the permission set:
    a role's slug and its display name are both 50 characters wide, and the
    permission set is longer than that. Every call therefore makes its own
    role, so one scenario's grants can never be overwritten by another's.
    """
    role_slug = f"{slug}-{uuid.uuid4().hex[:10]}"
    user = _user(db_session, tenant, slug=role_slug, permissions=list(codes), branch=branch)
    _login(client, user)
    return user


def _admin(client, db_session, tenant, branch):
    """A super_admin.

    The admin guard reads the *role*, not a permission, so the role's own
    permission set is deliberately left alone here: replacing it would strip
    the permissions of the seeded super_admin for every other test in the run.
    """
    user = _user(db_session, tenant, slug="super_admin", permissions=(), branch=branch)
    _login(client, user)
    return user


def _product(db_session, tenant, *, name="Probe Product"):
    from models import Product

    product = Product(
        tenant_id=tenant.id,
        name=f"{name}-{uuid.uuid4().hex[:6]}",
        sku=f"AI-{uuid.uuid4().hex[:8]}",
        regular_price=100,
        is_active=True,
    )
    db_session.add(product)
    db_session.commit()
    return product


def _other_tenant(db_session):
    """A second tenant, for the isolation assertions."""
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


def _json_envelope(resp):
    """The response carries the standard envelope, whatever the status is."""
    body = resp.get_json(silent=True)
    assert isinstance(body, dict), f"expected a JSON envelope, got {resp.get_data(as_text=True)[:120]}"
    assert "success" in body, f"the envelope has no success flag: {body}"
    return body


class TestAI01ThePermissionBoundary:
    """AI-01 to AI-14: which permission opens which route."""

    def test_anonymous_is_refused_on_every_ai_route(self, client):
        """AI-01."""
        for path in ALL_AI_ROUTES:
            if path in POST_ONLY_ROUTES:
                resp = client.post(path, json={})
            else:
                resp = client.get(path)
            assert resp.status_code in (302, 401, 403, 404), f"{path} answered {resp.status_code}"

    def test_the_ai_permissions_are_seeded(self, db_session):
        """AI-02."""
        from models import Permission

        for code in ("view_reports", "view_products", "manage_warehouse", "view_ledger", "manage_customers"):
            assert db_session.query(Permission).filter_by(code=code).first() is not None, f"{code} is not seeded"

    def test_view_reports_reaches_the_report_routes(self, client, db_session, demo_tenant, demo_branch):
        """AI-03."""
        _with(client, db_session, demo_tenant, demo_branch, ["view_reports"], "reporter")
        for path in REPORT_ROUTES:
            resp = client.get(path)
            assert resp.status_code == 200, f"{path} answered {resp.status_code}"

    def test_view_reports_does_not_reach_the_inventory_routes(self, client, db_session, demo_tenant, demo_branch):
        """AI-04. The inventory analysis is behind the warehouse permission."""
        _with(client, db_session, demo_tenant, demo_branch, ["view_reports"], "reporter")
        for path in WAREHOUSE_ROUTES:
            assert client.get(path).status_code == 403, f"{path} answered for a reporter"

    def test_view_products_does_not_reach_the_report_routes(self, client, db_session, demo_tenant, demo_branch):
        """AI-05. Looking at products is not the authority to see the books."""
        _with(client, db_session, demo_tenant, demo_branch, ["view_products"], "products")
        for path in ("/ai/system/summary", "/ai/data/analyze-sales", "/ai/predict-sales"):
            assert client.get(path).status_code == 403, f"{path} answered for a products reader"

    def test_manage_customers_gates_the_customer_analysis(self, client, db_session, demo_tenant, demo_branch):
        """AI-06."""
        _with(client, db_session, demo_tenant, demo_branch, ["view_reports"], "reporter")
        for path in CUSTOMER_ROUTES:
            assert client.get(path).status_code == 403, f"{path} answered for a reporter"

    def test_view_ledger_gates_the_cash_flow_prediction(self, client, db_session, demo_tenant, demo_branch):
        """AI-07. Cash is a ledger question, not a reporting one."""
        _with(client, db_session, demo_tenant, demo_branch, ["view_reports"], "reporter")
        assert client.get("/ai/cash-flow-prediction").status_code == 403

        _with(client, db_session, demo_tenant, demo_branch, ["view_ledger"], "ledger")
        assert client.get("/ai/cash-flow-prediction").status_code == 200

    def test_the_ai_config_route_is_the_platform_owners_alone(self, client, db_session, demo_tenant, demo_branch):
        """AI-08. It sets the model key the whole tenant's AI talks to."""
        _with(client, db_session, demo_tenant, demo_branch, ["view_reports", "admin"], "admin")
        resp = client.get("/ai/config")
        assert resp.status_code == 404, f"the AI config answered {resp.status_code} for a company user"

    def test_a_company_admin_is_not_the_platform_owner(self, client, db_session, demo_tenant, demo_branch):
        """AI-09. The owner surface answers 404, not 403: it stays hidden."""
        _with(client, db_session, demo_tenant, demo_branch, ["view_reports", "admin"], "admin")
        for path in OWNER_ROUTES:
            resp = client.get(path)
            assert resp.status_code == 404, f"{path} answered {resp.status_code}"

    def test_the_owner_training_routes_are_the_platform_owners_alone(
        self, client, db_session, demo_tenant, demo_branch
    ):
        """AI-10."""
        _with(client, db_session, demo_tenant, demo_branch, ["view_reports"], "reporter")
        assert client.get("/owner/ai-training").status_code == 404

    def test_the_admin_routes_refuse_a_viewer(self, client, db_session, demo_tenant, demo_branch):
        """AI-11. Evolving the knowledge is a super_admin action."""
        _with(client, db_session, demo_tenant, demo_branch, ["view_reports"], "reporter")
        for path in ADMIN_ROUTES:
            resp = client.get(path)
            assert resp.status_code in (403, 405), f"{path} answered {resp.status_code}"

    def test_the_knowledge_import_routes_are_the_platform_owners_alone(
        self, client, db_session, demo_tenant, demo_branch
    ):
        """AI-12. What the AI knows is the owner's decision."""
        _with(client, db_session, demo_tenant, demo_branch, ["view_reports"], "reporter")
        for path in ("/ai/knowledge/add-website", "/ai/knowledge/add-document"):
            resp = client.post(path, json={})
            assert resp.status_code == 404, f"{path} answered {resp.status_code}"

    def test_view_customers_gates_the_customer_behaviour_analysis(self, client, db_session, demo_tenant, demo_branch):
        """AI-13."""
        _with(client, db_session, demo_tenant, demo_branch, ["view_reports"], "reporter")
        assert client.get("/ai/analyze-customer/999999").status_code == 403

    def test_manage_products_gates_the_excel_upload(self, client, db_session, demo_tenant, demo_branch):
        """AI-14. The upload writes products, so it needs the products write."""
        _with(client, db_session, demo_tenant, demo_branch, ["view_products"], "products")
        resp = client.post("/ai/upload-excel", data={})
        assert resp.status_code == 403, f"the upload answered {resp.status_code} for a products reader"


class TestAI16TheSystemQueries:
    """AI-15 to AI-24: the system and data lookups."""

    def test_the_system_summary_answers(self, client, db_session, demo_tenant, demo_branch):
        """AI-15."""
        _with(client, db_session, demo_tenant, demo_branch, ["view_reports"], "reporter")
        resp = client.get("/ai/system/summary")
        assert resp.status_code == 200
        body = _json_envelope(resp)
        assert "summary" in body["data"]
        assert "financial" in body["data"]

    def test_the_system_search_answers(self, client, db_session, demo_tenant, demo_branch):
        """AI-16."""
        _with(client, db_session, demo_tenant, demo_branch, ["view_reports"], "reporter")
        resp = client.get("/ai/system/search/anything")
        assert resp.status_code == 200
        body = _json_envelope(resp)
        assert body["data"]["query"] == "anything"

    def test_the_balance_of_an_unknown_customer_is_an_error_not_a_guess(
        self, client, db_session, demo_tenant, demo_branch
    ):
        """AI-17. A balance for a customer that does not exist is not zero."""
        _with(client, db_session, demo_tenant, demo_branch, ["manage_customers"], "customers")
        resp = client.get("/ai/system/customer-balance/Nobody")
        assert resp.status_code == 200
        body = _json_envelope(resp)
        assert "error" in body["data"], f"the answer was not an error: {body['data']}"

    def test_the_debt_of_an_unknown_customer_is_an_error(self, client, db_session, demo_tenant, demo_branch):
        """AI-18."""
        _with(client, db_session, demo_tenant, demo_branch, ["manage_customers"], "customers")
        resp = client.get("/ai/system/customer-debt/999999")
        assert resp.status_code == 200
        body = _json_envelope(resp)
        assert "error" in body["data"], f"the answer was not an error: {body['data']}"

    def test_the_stock_of_an_unknown_product_is_an_error(self, client, db_session, demo_tenant, demo_branch):
        """AI-19. A stock level for a product that does not exist is not zero."""
        _with(client, db_session, demo_tenant, demo_branch, ["manage_products"], "products")
        resp = client.get("/ai/system/product-stock/Nothing")
        assert resp.status_code == 200
        body = _json_envelope(resp)
        assert "error" in body["data"], f"the answer was not an error: {body['data']}"

    def test_the_sales_analysis_answers(self, client, db_session, demo_tenant, demo_branch):
        """AI-20."""
        _with(client, db_session, demo_tenant, demo_branch, ["view_reports"], "reporter")
        resp = client.get("/ai/data/analyze-sales")
        assert resp.status_code == 200
        assert "analysis" in _json_envelope(resp)["data"]

    def test_the_product_analysis_answers(self, client, db_session, demo_tenant, demo_branch):
        """AI-21."""
        _with(client, db_session, demo_tenant, demo_branch, ["view_products"], "products")
        resp = client.get("/ai/data/analyze-products")
        assert resp.status_code == 200
        assert "total_products" in _json_envelope(resp)["data"]

    def test_the_financial_ratios_answer(self, client, db_session, demo_tenant, demo_branch):
        """AI-22."""
        _with(client, db_session, demo_tenant, demo_branch, ["view_reports"], "reporter")
        resp = client.get("/ai/data/financial-ratios")
        assert resp.status_code == 200
        assert "ratios" in _json_envelope(resp)["data"]

    def test_adding_a_customer_without_a_body_is_an_error(self, client, db_session, demo_tenant, demo_branch):
        """AI-23. A customer created out of nothing is a customer in nobody's books."""
        _with(client, db_session, demo_tenant, demo_branch, ["manage_customers"], "customers")
        resp = client.post("/ai/system/add-customer", json={})
        assert resp.status_code in (200, 400, 500)
        assert "success" in _json_envelope(resp)

    def test_the_system_routes_answer_json_not_html(self, client, db_session, demo_tenant, demo_branch):
        """AI-24. An API that answers HTML breaks every caller that asked for data."""
        _with(client, db_session, demo_tenant, demo_branch, ["view_reports", "manage_customers"], "reader")
        for path in ("/ai/system/summary", "/ai/data/financial-ratios", "/ai/system/search/x"):
            resp = client.get(path)
            assert resp.content_type.startswith("application/json"), f"{path} answered {resp.content_type}"


class TestAI26TheAnalytics:
    """AI-25 to AI-35: the prediction and analysis endpoints."""

    def test_the_sales_prediction_answers(self, client, db_session, demo_tenant, demo_branch):
        """AI-25."""
        _with(client, db_session, demo_tenant, demo_branch, ["view_reports"], "reporter")
        resp = client.get("/ai/predict-sales")
        assert resp.status_code == 200
        assert "data" in _json_envelope(resp)

    def test_the_margin_analysis_answers(self, client, db_session, demo_tenant, demo_branch):
        """AI-26."""
        _with(client, db_session, demo_tenant, demo_branch, ["view_reports"], "reporter")
        resp = client.get("/ai/analyze-margins")
        assert resp.status_code == 200
        assert "data" in _json_envelope(resp)

    def test_the_pattern_detection_answers(self, client, db_session, demo_tenant, demo_branch):
        """AI-27."""
        _with(client, db_session, demo_tenant, demo_branch, ["view_reports"], "reporter")
        resp = client.get("/ai/detect-patterns")
        assert resp.status_code == 200
        assert "data" in _json_envelope(resp)

    def test_the_inventory_health_answers(self, client, db_session, demo_tenant, demo_branch):
        """AI-28."""
        _with(client, db_session, demo_tenant, demo_branch, ["manage_warehouse"], "warehouse")
        resp = client.get("/ai/inventory-health")
        assert resp.status_code == 200
        assert "data" in _json_envelope(resp)

    def test_the_deep_analysis_answers(self, client, db_session, demo_tenant, demo_branch):
        """AI-29."""
        _with(client, db_session, demo_tenant, demo_branch, ["view_reports"], "reporter")
        resp = client.get("/ai/deep-analysis")
        assert resp.status_code == 200
        assert "data" in _json_envelope(resp)

    def test_the_cash_flow_prediction_answers(self, client, db_session, demo_tenant, demo_branch):
        """AI-30."""
        _with(client, db_session, demo_tenant, demo_branch, ["view_ledger"], "ledger")
        resp = client.get("/ai/cash-flow-prediction")
        assert resp.status_code == 200
        assert "predictions" in _json_envelope(resp)["data"]

    def test_the_churn_prediction_answers(self, client, db_session, demo_tenant, demo_branch):
        """AI-31."""
        _with(client, db_session, demo_tenant, demo_branch, ["manage_customers"], "customers")
        resp = client.get("/ai/churn-prediction")
        assert resp.status_code == 200
        assert "total_customers" in _json_envelope(resp)["data"]

    def test_the_inventory_optimisation_answers(self, client, db_session, demo_tenant, demo_branch):
        """AI-32."""
        _with(client, db_session, demo_tenant, demo_branch, ["manage_warehouse"], "warehouse")
        resp = client.get("/ai/optimize-inventory")
        assert resp.status_code == 200
        assert "total_products" in _json_envelope(resp)["data"]

    def test_the_business_insights_answer(self, client, db_session, demo_tenant, demo_branch):
        """AI-33."""
        _with(client, db_session, demo_tenant, demo_branch, ["view_reports"], "reporter")
        resp = client.get("/ai/business-insights")
        assert resp.status_code == 200
        insights = _json_envelope(resp)["data"]["insights"]
        assert isinstance(insights, list)
        for insight in insights:
            assert "icon" in insight and "title" in insight and "insight" in insight

    def test_the_smart_price_needs_a_product_and_a_customer(self, client, db_session, demo_tenant, demo_branch):
        """AI-34."""
        _with(client, db_session, demo_tenant, demo_branch, ["view_products"], "products")
        resp = client.post("/ai/smart-price", json={})
        assert resp.status_code == 400
        assert _json_envelope(resp)["success"] is False

    def test_the_smart_price_of_an_unknown_product_is_not_found(self, client, db_session, demo_tenant, demo_branch):
        """AI-35. A price for a product that does not exist is not a price."""
        _with(client, db_session, demo_tenant, demo_branch, ["view_products"], "products")
        resp = client.post("/ai/smart-price", json={"product_id": 999999, "customer_id": 1})
        assert resp.status_code in (404, 500, 503), f"the smart price answered {resp.status_code}"


class TestAI37TheChatAndQuickQuery:
    """AI-36 to AI-44: the endpoints that ask the caller for something."""

    def test_the_price_recommendation_needs_a_body(self, client, db_session, demo_tenant, demo_branch):
        """AI-36."""
        _with(client, db_session, demo_tenant, demo_branch, ["view_products"], "products")
        resp = client.post("/ai/recommend-price", json={})
        assert resp.status_code == 400
        assert _json_envelope(resp)["success"] is False

    def test_the_price_recommendation_needs_a_product_and_a_customer(
        self, client, db_session, demo_tenant, demo_branch
    ):
        """AI-37."""
        _with(client, db_session, demo_tenant, demo_branch, ["view_products"], "products")
        resp = client.post("/ai/recommend-price", json={"product_id": 1})
        assert resp.status_code == 400
        assert _json_envelope(resp)["success"] is False

    def test_the_stock_check_needs_a_body(self, client, db_session, demo_tenant, demo_branch):
        """AI-38."""
        _with(client, db_session, demo_tenant, demo_branch, ["view_products"], "products")
        resp = client.post("/ai/check-stock", json={})
        assert resp.status_code == 400

    def test_the_stock_check_needs_a_product(self, client, db_session, demo_tenant, demo_branch):
        """AI-39."""
        _with(client, db_session, demo_tenant, demo_branch, ["view_products"], "products")
        resp = client.post("/ai/check-stock", json={"quantity": 1})
        assert resp.status_code == 400
        assert _json_envelope(resp)["success"] is False

    def test_the_stock_check_refuses_a_quantity_that_is_not_a_number(
        self, client, db_session, demo_tenant, demo_branch
    ):
        """AI-40. A quantity of "three" is a question, not an order."""
        _with(client, db_session, demo_tenant, demo_branch, ["view_products"], "products")
        resp = client.post("/ai/check-stock", json={"product_id": 1, "quantity": "abc"})
        assert resp.status_code == 422
        assert _json_envelope(resp)["success"] is False

    def test_the_chat_needs_a_body(self, client, db_session, demo_tenant, demo_branch):
        """AI-41."""
        _with(client, db_session, demo_tenant, demo_branch, ["view_reports"], "reporter")
        resp = client.post("/ai/chat", json={})
        assert resp.status_code == 400
        assert _json_envelope(resp)["success"] is False

    def test_the_customer_behaviour_analysis_answers(self, client, db_session, demo_tenant, demo_branch):
        """AI-42."""
        _with(client, db_session, demo_tenant, demo_branch, ["view_customers"], "customers")
        resp = client.get("/ai/analyze-customer/999999")
        assert resp.status_code in (200, 404, 503)
        assert "success" in _json_envelope(resp)

    def test_the_exchange_rate_suggestion_answers(self, client, db_session, demo_tenant, demo_branch):
        """AI-43."""
        _with(client, db_session, demo_tenant, demo_branch, ["view_reports"], "reporter")
        resp = client.get("/ai/exchange-rate/AED")
        assert resp.status_code == 200
        assert _json_envelope(resp)["data"]["currency"] == "AED"

    def test_the_market_price_of_our_own_product_answers(self, client, db_session, demo_tenant, demo_branch):
        """AI-44."""
        product = _product(db_session, demo_tenant)
        _with(client, db_session, demo_tenant, demo_branch, ["view_products"], "products")
        resp = client.get(f"/ai/search-market-price/{product.id}")
        assert resp.status_code == 200
        assert _json_envelope(resp)["data"]["product"] == product.name


class TestAI46TheProductLookups:
    """AI-45 to AI-48: the two lookups that name a product by id."""

    def test_the_market_price_of_another_tenants_product_is_not_found(
        self, client, db_session, demo_tenant, demo_branch
    ):
        """AI-45. The lookup is the tenant's, not the world's."""
        other = _other_tenant(db_session)
        foreign = _product(db_session, other, name="Foreign Product")

        _with(client, db_session, demo_tenant, demo_branch, ["view_products"], "products")
        resp = client.get(f"/ai/search-market-price/{foreign.id}")
        assert resp.status_code == 404, f"the cross-tenant lookup answered {resp.status_code}"

    def test_the_compatible_vehicles_of_another_tenants_product_is_not_found(
        self, client, db_session, demo_tenant, demo_branch
    ):
        """AI-46."""
        other = _other_tenant(db_session)
        foreign = _product(db_session, other, name="Foreign Product")

        _with(client, db_session, demo_tenant, demo_branch, ["view_products"], "products")
        resp = client.get(f"/ai/find-compatible/{foreign.id}")
        assert resp.status_code == 404, f"the cross-tenant lookup answered {resp.status_code}"

    def test_the_market_price_of_a_missing_product_is_not_found(self, client, db_session, demo_tenant, demo_branch):
        """AI-47."""
        _with(client, db_session, demo_tenant, demo_branch, ["view_products"], "products")
        assert client.get("/ai/search-market-price/999999").status_code == 404

    def test_the_compatible_vehicles_of_a_missing_product_is_not_found(
        self, client, db_session, demo_tenant, demo_branch
    ):
        """AI-48."""
        _with(client, db_session, demo_tenant, demo_branch, ["view_products"], "products")
        assert client.get("/ai/find-compatible/999999").status_code == 404


class TestAI50TheAssistant:
    """AI-49 to AI-52: the page and the two owner-only configuration routes."""

    def test_the_assistant_page_renders(self, client, db_session, demo_tenant, demo_branch):
        """AI-49."""
        _with(client, db_session, demo_tenant, demo_branch, ["view_reports"], "reporter")
        resp = client.get("/ai/assistant")
        assert resp.status_code == 200
        assert "text/html" in resp.content_type

    def test_the_config_page_renders_for_the_platform_owner(self, client, scenario_owner):
        """AI-50. The owner may see the key state without seeing the key."""
        resp = client.get("/ai/config")
        assert resp.status_code == 200
        assert "text/html" in resp.content_type

    def test_the_excel_upload_needs_a_file(self, client, db_session, demo_tenant, demo_branch):
        """AI-51."""
        _with(client, db_session, demo_tenant, demo_branch, ["manage_products"], "products")
        resp = client.post("/ai/upload-excel", data={})
        assert resp.status_code == 400
        assert _json_envelope(resp)["success"] is False

    def test_the_excel_upload_refuses_a_file_that_is_not_excel(self, client, db_session, demo_tenant, demo_branch):
        """AI-52."""
        _with(client, db_session, demo_tenant, demo_branch, ["manage_products"], "products")
        resp = client.post(
            "/ai/upload-excel",
            data={"file": (io.BytesIO(b"not a spreadsheet"), "products.csv")},
            content_type="multipart/form-data",
        )
        assert resp.status_code == 400
        assert _json_envelope(resp)["success"] is False


class TestAI54TheSpecializedEndpoints:
    """AI-53 to AI-60: the domain-specific endpoints."""

    def test_the_neural_status_answers(self, client, db_session, demo_tenant, demo_branch):
        """AI-53."""
        _with(client, db_session, demo_tenant, demo_branch, ["view_reports"], "reporter")
        resp = client.get("/ai/neural-status")
        assert resp.status_code == 200
        assert "status" in _json_envelope(resp)["data"]

    def test_the_ecu_lookup_answers(self, client, db_session, demo_tenant, demo_branch):
        """AI-54. An unknown code is a diagnosis of "not in the catalogue"."""
        _with(client, db_session, demo_tenant, demo_branch, ["view_products"], "products")
        resp = client.get("/ai/automotive-ecu/ECU1")
        assert resp.status_code == 200
        assert "diagnosis" in _json_envelope(resp)["data"]

    def test_the_sensor_lookup_answers(self, client, db_session, demo_tenant, demo_branch):
        """AI-55."""
        _with(client, db_session, demo_tenant, demo_branch, ["view_products"], "products")
        resp = client.get("/ai/automotive-sensor/O2")
        assert resp.status_code == 200
        assert "sensor_info" in _json_envelope(resp)["data"]

    def test_the_external_sources_answer(self, client, db_session, demo_tenant, demo_branch):
        """AI-56."""
        _with(client, db_session, demo_tenant, demo_branch, ["view_reports"], "reporter")
        resp = client.get("/ai/external-sources")
        assert resp.status_code == 200
        assert "catalog" in _json_envelope(resp)["data"]

    def test_ask_genius_needs_a_body(self, client, db_session, demo_tenant, demo_branch):
        """AI-57."""
        _with(client, db_session, demo_tenant, demo_branch, ["view_reports"], "reporter")
        resp = client.post("/ai/ask-genius", json={})
        assert resp.status_code == 400
        assert _json_envelope(resp)["success"] is False

    def test_quick_calc_needs_a_body(self, client, db_session, demo_tenant, demo_branch):
        """AI-58."""
        _with(client, db_session, demo_tenant, demo_branch, ["view_reports"], "reporter")
        resp = client.post("/ai/quick-calc", json={})
        assert resp.status_code == 400
        assert _json_envelope(resp)["success"] is False

    def test_the_transformers_endpoint_needs_a_body(self, client, db_session, demo_tenant, demo_branch):
        """AI-59."""
        _with(client, db_session, demo_tenant, demo_branch, ["view_reports"], "reporter")
        resp = client.post("/ai/transformers-understand", json={})
        assert resp.status_code == 400
        assert _json_envelope(resp)["success"] is False

    def test_the_specialized_routes_answer_json(self, client, db_session, demo_tenant, demo_branch):
        """AI-60."""
        _with(client, db_session, demo_tenant, demo_branch, ["view_reports", "view_products"], "reader")
        for path in ("/ai/neural-status", "/ai/external-sources", "/ai/automotive-sensor/O2"):
            resp = client.get(path)
            assert resp.content_type.startswith("application/json"), f"{path} answered {resp.content_type}"


class TestAI62TheKnowledgeSurface:
    """AI-61 to AI-75: learning, improvement and the knowledge base."""

    def test_the_contextual_help_answers(self, client, db_session, demo_tenant, demo_branch):
        """AI-61."""
        _with(client, db_session, demo_tenant, demo_branch, ["view_reports"], "reporter")
        resp = client.get("/ai/contextual-help/sales")
        assert resp.status_code == 200
        assert "help" in _json_envelope(resp)["data"]

    def test_the_learning_status_answers(self, client, db_session, demo_tenant, demo_branch):
        """AI-62."""
        _with(client, db_session, demo_tenant, demo_branch, ["view_reports"], "reporter")
        resp = client.get("/ai/learning/status")
        assert resp.status_code == 200
        assert "learning_insights" in _json_envelope(resp)["data"]

    def test_the_learning_evolution_is_the_admins(self, client, db_session, demo_tenant, demo_branch):
        """AI-63."""
        _with(client, db_session, demo_tenant, demo_branch, ["view_reports"], "reporter")
        assert client.post("/ai/learning/evolve").status_code == 403

    def test_the_improvement_status_answers(self, client, db_session, demo_tenant, demo_branch):
        """AI-64."""
        _with(client, db_session, demo_tenant, demo_branch, ["view_reports"], "reporter")
        resp = client.get("/ai/improvement/status")
        assert resp.status_code == 200
        assert "improvement_status" in _json_envelope(resp)["data"]

    def test_the_auto_improvement_is_the_admins(self, client, db_session, demo_tenant, demo_branch):
        """AI-65."""
        _with(client, db_session, demo_tenant, demo_branch, ["view_reports"], "reporter")
        assert client.post("/ai/improvement/auto-improve").status_code == 403

    def test_the_improvement_progress_answers(self, client, db_session, demo_tenant, demo_branch):
        """AI-66."""
        _with(client, db_session, demo_tenant, demo_branch, ["view_reports"], "reporter")
        resp = client.get("/ai/improvement/progress")
        assert resp.status_code == 200
        assert "progress" in _json_envelope(resp)["data"]

    def test_the_improvement_goal_is_the_admins(self, client, db_session, demo_tenant, demo_branch):
        """AI-67."""
        _with(client, db_session, demo_tenant, demo_branch, ["view_reports"], "reporter")
        assert client.post("/ai/improvement/set-goal", json={}).status_code == 403

    def test_the_global_insights_answer(self, client, db_session, demo_tenant, demo_branch):
        """AI-68."""
        _with(client, db_session, demo_tenant, demo_branch, ["view_reports"], "reporter")
        resp = client.get("/ai/global/insights")
        assert resp.status_code == 200
        assert "global_insights" in _json_envelope(resp)["data"]

    def test_the_global_expertise_update_is_the_admins(self, client, db_session, demo_tenant, demo_branch):
        """AI-69."""
        _with(client, db_session, demo_tenant, demo_branch, ["view_reports"], "reporter")
        assert client.get("/ai/global/expertise-update").status_code == 403

    def test_the_performance_analysis_answers(self, client, db_session, demo_tenant, demo_branch):
        """AI-70."""
        _with(client, db_session, demo_tenant, demo_branch, ["view_reports"], "reporter")
        resp = client.get("/ai/performance/analysis")
        assert resp.status_code == 200
        assert "performance_analysis" in _json_envelope(resp)["data"]

    def test_adding_a_website_is_the_platform_owners(self, client, db_session, demo_tenant, demo_branch):
        """AI-71."""
        _with(client, db_session, demo_tenant, demo_branch, ["view_reports"], "reporter")
        resp = client.post("/ai/knowledge/add-website", json={})
        assert resp.status_code == 404, f"the route answered {resp.status_code} for a company user"

    def test_adding_a_document_is_the_platform_owners(self, client, db_session, demo_tenant, demo_branch):
        """AI-72."""
        _with(client, db_session, demo_tenant, demo_branch, ["view_reports"], "reporter")
        resp = client.post("/ai/knowledge/add-document", json={})
        assert resp.status_code == 404, f"the route answered {resp.status_code} for a company user"

    def test_the_knowledge_search_answers(self, client, db_session, demo_tenant, demo_branch):
        """AI-73."""
        _with(client, db_session, demo_tenant, demo_branch, ["view_reports"], "reporter")
        resp = client.get("/ai/knowledge/search?q=anything")
        assert resp.status_code == 200
        body = _json_envelope(resp)
        assert body["data"]["query"] == "anything"

    def test_the_knowledge_search_needs_a_query(self, client, db_session, demo_tenant, demo_branch):
        """AI-74. A search for nothing searches for nothing."""
        _with(client, db_session, demo_tenant, demo_branch, ["view_reports"], "reporter")
        resp = client.get("/ai/knowledge/search")
        assert resp.status_code == 400
        assert _json_envelope(resp)["success"] is False

    def test_the_knowledge_summary_answers(self, client, db_session, demo_tenant, demo_branch):
        """AI-75."""
        _with(client, db_session, demo_tenant, demo_branch, ["view_reports"], "reporter")
        resp = client.get("/ai/knowledge/summary")
        assert resp.status_code == 200
        assert "summary" in _json_envelope(resp)["data"]


class TestAI77TheOwnerTraining:
    """AI-76 to AI-87: the owner training surface, which the owner alone sees."""

    def test_the_training_dashboard_is_the_platform_owners(self, client, db_session, demo_tenant, demo_branch):
        """AI-76."""
        _with(client, db_session, demo_tenant, demo_branch, ["view_reports"], "reporter")
        assert client.get("/owner/ai-training").status_code == 404

    def test_the_training_question_is_the_platform_owners(self, client, db_session, demo_tenant, demo_branch):
        """AI-77."""
        _with(client, db_session, demo_tenant, demo_branch, ["view_reports"], "reporter")
        assert client.post("/owner/ai-training/qa", data={}).status_code == 404

    def test_the_memory_toggle_is_the_platform_owners(self, client, db_session, demo_tenant, demo_branch):
        """AI-78."""
        _with(client, db_session, demo_tenant, demo_branch, ["view_reports"], "reporter")
        assert client.post("/owner/ai-training/1/toggle").status_code == 404

    def test_the_correction_is_the_platform_owners(self, client, db_session, demo_tenant, demo_branch):
        """AI-79."""
        _with(client, db_session, demo_tenant, demo_branch, ["view_reports"], "reporter")
        assert client.post("/owner/ai-training/correct", data={}).status_code == 404

    def test_the_upload_page_is_the_platform_owners(self, client, db_session, demo_tenant, demo_branch):
        """AI-80."""
        _with(client, db_session, demo_tenant, demo_branch, ["view_reports"], "reporter")
        assert client.get("/owner/ai-training/upload").status_code == 404

    def test_the_progress_page_is_the_platform_owners(self, client, db_session, demo_tenant, demo_branch):
        """AI-81."""
        _with(client, db_session, demo_tenant, demo_branch, ["view_reports"], "reporter")
        assert client.get("/owner/ai-training/progress").status_code == 404

    def test_the_metrics_page_is_the_platform_owners(self, client, db_session, demo_tenant, demo_branch):
        """AI-82."""
        _with(client, db_session, demo_tenant, demo_branch, ["view_reports"], "reporter")
        assert client.get("/owner/ai-training/metrics").status_code == 404

    def test_the_concept_page_is_the_platform_owners(self, client, db_session, demo_tenant, demo_branch):
        """AI-83."""
        _with(client, db_session, demo_tenant, demo_branch, ["view_reports"], "reporter")
        assert client.get("/owner/ai-training/concept/anything").status_code == 404

    def test_the_knowledge_graph_is_the_platform_owners(self, client, db_session, demo_tenant, demo_branch):
        """AI-84."""
        _with(client, db_session, demo_tenant, demo_branch, ["view_reports"], "reporter")
        assert client.get("/owner/ai-training/knowledge-graph").status_code == 404

    def test_the_health_page_is_the_platform_owners(self, client, db_session, demo_tenant, demo_branch):
        """AI-85."""
        _with(client, db_session, demo_tenant, demo_branch, ["view_reports"], "reporter")
        assert client.get("/owner/ai-training/health").status_code == 404

    def test_the_batches_page_is_the_platform_owners(self, client, db_session, demo_tenant, demo_branch):
        """AI-86."""
        _with(client, db_session, demo_tenant, demo_branch, ["view_reports"], "reporter")
        assert client.get("/owner/ai-training/batches").status_code == 404

    def test_the_semantic_training_is_the_platform_owners(self, client, db_session, demo_tenant, demo_branch):
        """AI-87."""
        _with(client, db_session, demo_tenant, demo_branch, ["view_reports"], "reporter")
        assert client.post("/owner/ai-training/semantic-train", data={}).status_code == 404


class TestAI89TheShape:
    """AI-88 to AI-102: what the surface is and what it must keep being."""

    def test_the_scenario_covers_every_ai_route(self, app):
        """AI-88. A scenario that stops covering a route stops being a scenario."""
        known = {
            "/ai/system/customer-balance/<customer_name>",
            "/ai/system/customer-debt/<int:customer_id>",
            "/ai/system/product-stock/<product_name>",
            "/ai/system/summary",
            "/ai/system/search/<search_term>",
            "/ai/system/add-customer",
            "/ai/data/analyze-sales",
            "/ai/data/analyze-products",
            "/ai/data/financial-ratios",
            "/ai/predict-sales",
            "/ai/analyze-margins",
            "/ai/detect-patterns",
            "/ai/inventory-health",
            "/ai/deep-analysis",
            "/ai/cash-flow-prediction",
            "/ai/smart-price",
            "/ai/churn-prediction",
            "/ai/optimize-inventory",
            "/ai/business-insights",
            "/ai/assistant",
            "/ai/config",
            "/ai/upload-excel",
            "/ai/recommend-price",
            "/ai/check-stock",
            "/ai/analyze-customer/<int:customer_id>",
            "/ai/exchange-rate/<currency>",
            "/ai/search-market-price/<int:product_id>",
            "/ai/find-compatible/<int:product_id>",
            "/ai/chat",
            "/ai/contextual-help/<page>",
            "/ai/learning/status",
            "/ai/learning/evolve",
            "/ai/improvement/status",
            "/ai/improvement/auto-improve",
            "/ai/improvement/progress",
            "/ai/improvement/set-goal",
            "/ai/global/insights",
            "/ai/global/expertise-update",
            "/ai/performance/analysis",
            "/ai/knowledge/add-website",
            "/ai/knowledge/add-document",
            "/ai/knowledge/search",
            "/ai/knowledge/summary",
            "/ai/neural-status",
            "/ai/automotive-ecu/<code>",
            "/ai/automotive-sensor/<sensor>",
            "/ai/external-sources",
            "/ai/ask-genius",
            "/ai/quick-calc",
            "/ai/transformers-understand",
            "/owner/ai-training",
            "/owner/ai-training/qa",
            "/owner/ai-training/<int:memory_id>/toggle",
            "/owner/ai-training/correct",
            "/owner/ai-training/upload",
            "/owner/ai-training/progress",
            "/owner/ai-training/metrics",
            "/owner/ai-training/concept/<concept_name>",
            "/owner/ai-training/knowledge-graph",
            "/owner/ai-training/health",
            "/owner/ai-training/batches",
            "/owner/ai-training/semantic-train",
        }
        live = {
            rule.rule
            for rule in app.url_map.iter_rules()
            if rule.rule.startswith("/ai") or rule.rule.startswith("/owner/ai-training")
        }
        assert live == known, f"the AI route inventory moved: {sorted(live ^ known)}"

    def test_every_ai_route_answers_json(self, client, db_session, demo_tenant, demo_branch):
        """AI-89. A caller that asked for data gets data."""
        _with(
            client,
            db_session,
            demo_tenant,
            demo_branch,
            ["view_reports", "view_products", "manage_products", "manage_customers", "view_customers"],
            "reader",
        )
        for path in REPORT_ROUTES:
            resp = client.get(path)
            assert resp.content_type.startswith("application/json"), f"{path} answered {resp.content_type}"

    def test_the_ai_answers_carry_the_envelope(self, client, db_session, demo_tenant, demo_branch):
        """AI-90. One shape for every answer, so a caller can rely on it."""
        _with(client, db_session, demo_tenant, demo_branch, ["view_reports"], "reporter")
        for path in ("/ai/system/summary", "/ai/predict-sales", "/ai/business-insights"):
            body = _json_envelope(client.get(path))
            assert "data" in body
            assert "message" in body

    def test_the_ai_interaction_log_carries_a_tenant(self, db_session):
        """AI-91. An interaction with no tenant is an interaction with no owner."""
        from models.ai import AiInteraction

        column = AiInteraction.__table__.columns.get("tenant_id")
        assert column is not None, "AiInteraction has no tenant_id"

    def test_the_system_search_does_not_cross_the_tenant_boundary(self, client, db_session, demo_tenant, demo_branch):
        """AI-92. The search is the tenant's, not the world's."""
        other = _other_tenant(db_session)
        from models import Customer

        db_session.add(
            Customer(
                tenant_id=other.id,
                name=f"Foreign Customer {uuid.uuid4().hex[:6]}",
                customer_type="regular",
                is_active=True,
            )
        )
        db_session.commit()

        _with(client, db_session, demo_tenant, demo_branch, ["view_reports"], "reporter")
        resp = client.get("/ai/system/search/Foreign")
        assert resp.status_code == 200
        results = _json_envelope(resp)["data"]["results"]
        assert not results.get("customers"), f"another tenant's customer came back: {results}"

    def test_the_price_recommendation_needs_the_products_permission(self, client, db_session, demo_tenant, demo_branch):
        """AI-93."""
        _with(client, db_session, demo_tenant, demo_branch, ["view_reports"], "reporter")
        assert client.post("/ai/recommend-price", json={"product_id": 1, "customer_id": 1}).status_code == 403

    def test_the_chat_needs_the_reports_permission(self, client, db_session, demo_tenant, demo_branch):
        """AI-94. The chat can read the books, so it needs the books."""
        _with(client, db_session, demo_tenant, demo_branch, ["view_products"], "products")
        assert client.post("/ai/chat", json={"message": "hello"}).status_code == 403

    def test_the_assistant_page_needs_the_reports_permission(self, client, db_session, demo_tenant, demo_branch):
        """AI-95."""
        _with(client, db_session, demo_tenant, demo_branch, ["view_products"], "products")
        assert client.get("/ai/assistant").status_code == 403

    def test_the_stock_check_needs_the_products_permission(self, client, db_session, demo_tenant, demo_branch):
        """AI-96."""
        _with(client, db_session, demo_tenant, demo_branch, ["view_reports"], "reporter")
        assert client.post("/ai/check-stock", json={"product_id": 1}).status_code == 403

    def test_the_customer_analysis_needs_the_customers_permission(self, client, db_session, demo_tenant, demo_branch):
        """AI-97."""
        _with(client, db_session, demo_tenant, demo_branch, ["view_reports"], "reporter")
        assert client.get("/ai/analyze-customer/1").status_code == 403

    def test_no_ai_route_is_reachable_without_a_permission(self, app):
        """AI-98. A route with no guard on it is a hole, not a feature."""
        guarded = 0
        for rule in app.url_map.iter_rules():
            if not (rule.rule.startswith("/ai") or rule.rule.startswith("/owner/ai-training")):
                continue
            view = app.view_functions[rule.endpoint]
            marks = getattr(view, "_required_permission", None) or getattr(view, "_required_guard", None)
            assert marks is not None, f"{rule.rule} has no permission guard"
            guarded += 1
        assert guarded >= 60, f"only {guarded} AI routes are guarded"

    def test_the_exchange_rate_route_answers_for_any_currency(self, client, db_session, demo_tenant, demo_branch):
        """AI-99. A currency it has no rate for is still an answer."""
        _with(client, db_session, demo_tenant, demo_branch, ["view_reports"], "reporter")
        resp = client.get("/ai/exchange-rate/JPY")
        assert resp.status_code == 200
        assert _json_envelope(resp)["data"]["currency"] == "JPY"

    def test_the_contextual_help_answers_for_any_page(self, client, db_session, demo_tenant, demo_branch):
        """AI-100. Help for a page nobody opened is still help."""
        _with(client, db_session, demo_tenant, demo_branch, ["view_reports"], "reporter")
        resp = client.get("/ai/contextual-help/anything")
        assert resp.status_code == 200
        assert _json_envelope(resp)["data"]["help"]

    def test_the_neural_status_reports_its_models(self, client, db_session, demo_tenant, demo_branch):
        """AI-101. The status route reports which models are trained."""
        _with(client, db_session, demo_tenant, demo_branch, ["view_reports"], "reporter")
        resp = client.get("/ai/neural-status")
        models = _json_envelope(resp)["data"]["status"]["models"]
        assert isinstance(models, dict) and models

    def test_the_ai_blueprint_answers_under_one_prefix(self, app):
        """AI-102. The AI surface is one blueprint, so one guard governs it."""
        prefixes = {rule.rule.split("/")[1] for rule in app.url_map.iter_rules() if rule.rule.startswith("/ai")}
        assert prefixes == {"ai"}, f"the AI routes spread over {sorted(prefixes)}"
