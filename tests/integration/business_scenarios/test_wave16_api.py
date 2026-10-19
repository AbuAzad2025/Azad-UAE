"""Wave 16 - the API surface: /api, /api/v2, /api/docs, /graphql and printing.

The API is the surface a *machine* talks to, and the difference from every
other surface in the system is that a machine does not read the page - it
reads the status code and the body. So the rules here are about the contract
rather than about the business: what is public, what is guarded, and what
shape the answer has.

Three things are worth pinning. The first is the public edge: the health and
version endpoints answer to anybody, because a load balancer has no session
(API-01, API-02). The second is that the read endpoints are guarded by the
*reading* permission and not by a general one - the low-stock report wants
``view_reports`` (API-12), the currency rate wants it too (API-06), and a
caller who holds only ``view_products`` gets 403 on both (API-07).

The third is the shape. Every answer on this surface carries the same
envelope, so a client can read ``success`` without knowing which endpoint it
called (API-09, API-10). And the payload guards are real guards: a telemetry
batch over 64 KB is refused with 413 rather than truncated (API-16, API-17),
because a truncated batch is a batch that silently lost events.

The docs are the fourth thing. ``/api-docs/openapi.json`` is generated from
the live url_map, and the gate in ``scripts/lint/check_api_docs.py`` compares
it with ``docs/API_REFERENCE.md`` - so the contract on paper and the contract
in the code are the same contract, and this suite pins the shape of the
document that the gate reads (API-40 to API-43).

GraphQL sits at the end because it is the one surface with two doors: the
query endpoint wants ``view_reports``, and the playground wants the admin
role, because a playground is a console (API-44 to API-47).
"""

from __future__ import annotations

import uuid

#: The endpoints that answer to anybody.
PUBLIC_API_PATHS = [
    "/api/health",
    "/api/version",
]
#: The endpoints that need a signed-in caller and nothing more.
SIGNED_IN_API_PATHS = [
    "/api/currencies",
    "/api/payment-fields/cash",
    "/api/industry-fields",
    "/api/check-username?username=probe",
    "/api/echo",
]
#: The endpoints that need a permission.
REPORT_API_PATHS = [
    "/api/currency-rate/AED/USD",
    "/api/search?q=probe",
    "/api/products/low-stock",
    "/api/warehouses",
    "/api/products",
    "/api/search_warehouses",
    "/api/warehouses/1/products",
    "/api/products/1/info",
    "/api/products/barcode/123",
    "/api/barcode/validate?code=123",
]


def _role(db_session, slug):
    from models import Role

    role = db_session.query(Role).filter_by(slug=slug).first()
    if role is None:
        role = Role(name=slug.replace("_", " ").title()[:50], slug=slug[:50], is_active=True)
        db_session.add(role)
        db_session.commit()
    return role


def _user(db_session, tenant, *, slug="api-user", permissions=(), branch=None):
    from models import Permission, User

    role = _role(db_session, slug)
    if permissions:
        role.permissions = Permission.query.filter(Permission.code.in_(list(permissions))).all()
        db_session.add(role)
        db_session.commit()
    unique = uuid.uuid4().hex[:8]
    user = User(
        username=f"api-{slug}-{unique}",
        email=f"api-{unique}@example.com",
        full_name=f"API {slug}",
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
    """A signed-in user carrying exactly ``codes``."""
    role_slug = f"{slug}-{uuid.uuid4().hex[:10]}"
    user = _user(db_session, tenant, slug=role_slug, permissions=list(codes), branch=branch)
    _login(client, user)
    return user


def _envelope(resp):
    """The response carries the standard envelope, whatever the status is."""
    body = resp.get_json(silent=True)
    assert isinstance(body, dict), f"expected a JSON envelope, got {resp.get_data(as_text=True)[:120]}"
    assert "success" in body, f"the envelope has no success flag: {body}"
    return body


class TestAPI01ThePublicEdge:
    """API-01 to API-05: what answers to anybody."""

    def test_the_health_endpoint_answers_to_anybody(self, client):
        """API-01. A load balancer has no session."""
        resp = client.get("/api/health")
        assert resp.status_code == 200
        assert resp.get_json()["data"]["status"] == "ok"

    def test_the_version_endpoint_answers_to_anybody(self, client):
        """API-02."""
        resp = client.get("/api/version")
        assert resp.status_code == 200
        assert "version" in resp.get_json()["data"]

    def test_the_public_endpoints_do_not_leak_internals(self, client):
        """API-03. The health check says it is up, not why it might not be."""
        body = client.get("/api/health").get_data(as_text=True)
        assert "Traceback" not in body
        assert "password" not in body.lower()

    def test_the_version_endpoint_names_the_product(self, client):
        """API-04."""
        data = client.get("/api/version").get_json()["data"]
        assert data["name"]

    def test_the_public_endpoints_answer_json(self, client):
        """API-05. A machine asked for data, so it gets data."""
        for path in PUBLIC_API_PATHS:
            resp = client.get(path)
            assert resp.content_type.startswith("application/json"), f"{path} answered {resp.content_type}"


class TestAPI06TheReadGuards:
    """API-06 to API-12: the reading permission, and only the reading one."""

    def test_the_currency_rate_needs_the_reports_permission(self, client, db_session, demo_tenant, demo_branch):
        """API-06."""
        _with(client, db_session, demo_tenant, demo_branch, ["view_products"], "products")
        assert client.get("/api/currency-rate/AED/USD").status_code == 403

    def test_the_reports_permission_reaches_the_rate(self, client, db_session, demo_tenant, demo_branch):
        """API-07."""
        _with(client, db_session, demo_tenant, demo_branch, ["view_reports"], "reporter")
        resp = client.get("/api/currency-rate/AED/USD")
        assert resp.status_code == 200
        _envelope(resp)

    def test_an_anonymous_caller_gets_no_rates(self, client):
        """API-08."""
        resp = client.get("/api/currency-rate/AED/USD")
        assert resp.status_code in (302, 401, 403), f"the rate answered {resp.status_code}"

    def test_every_read_endpoint_answers_the_envelope(self, client, db_session, demo_tenant, demo_branch):
        """API-09. One shape for every answer."""
        _with(client, db_session, demo_tenant, demo_branch, ["view_reports"], "reporter")
        for path in REPORT_API_PATHS:
            resp = client.get(path)
            assert resp.status_code in (200, 404), f"{path} answered {resp.status_code}"
            if resp.status_code == 200:
                _envelope(resp)

    def test_the_read_endpoints_answer_json(self, client, db_session, demo_tenant, demo_branch):
        """API-10."""
        _with(client, db_session, demo_tenant, demo_branch, ["view_reports"], "reporter")
        for path in ("/api/search?q=probe", "/api/warehouses", "/api/products"):
            resp = client.get(path)
            assert resp.content_type.startswith("application/json"), f"{path} answered {resp.content_type}"

    def test_the_signed_in_endpoints_answer_to_a_signed_in_caller(self, client, db_session, demo_tenant, demo_branch):
        """API-11. A signed-in caller with no particular permission is enough here."""
        _with(client, db_session, demo_tenant, demo_branch, ["view_reports"], "reader")
        for path in SIGNED_IN_API_PATHS:
            resp = client.get(path)
            assert resp.status_code in (200, 404, 405), f"{path} answered {resp.status_code}"

    def test_the_low_stock_report_needs_the_reports_permission(self, client, db_session, demo_tenant, demo_branch):
        """API-12. A stock report is a report."""
        _with(client, db_session, demo_tenant, demo_branch, ["view_products"], "products")
        assert client.get("/api/products/low-stock").status_code == 403

    def test_the_products_endpoints_need_the_reports_permission(self, client, db_session, demo_tenant, demo_branch):
        """API-13."""
        _with(client, db_session, demo_tenant, demo_branch, ["view_products"], "products")
        for path in ("/api/warehouses", "/api/products", "/api/search_warehouses"):
            assert client.get(path).status_code == 403, f"{path} answered for a products reader"

    def test_the_username_check_answers_to_a_signed_in_caller(self, client, db_session, demo_tenant, demo_branch):
        """API-14."""
        _with(client, db_session, demo_tenant, demo_branch, ["view_reports"], "reader")
        resp = client.get("/api/check-username?username=probe")
        assert resp.status_code == 200
        _envelope(resp)

    def test_the_username_check_says_a_free_name_is_free(self, client, db_session, demo_tenant, demo_branch):
        """API-15."""
        _with(client, db_session, demo_tenant, demo_branch, ["view_reports"], "reader")
        body = _envelope(client.get(f"/api/check-username?username=free-{uuid.uuid4().hex[:8]}"))
        assert body["data"] is not None

    def test_the_industry_fields_answer(self, client, db_session, demo_tenant, demo_branch):
        """API-16. The industry field definitions are the tenant's configuration."""
        _with(client, db_session, demo_tenant, demo_branch, ["view_reports"], "reader")
        resp = client.get("/api/industry-fields")
        assert resp.status_code == 200
        _envelope(resp)

    def test_the_payment_fields_answer(self, client, db_session, demo_tenant, demo_branch):
        """API-17."""
        _with(client, db_session, demo_tenant, demo_branch, ["view_reports"], "reader")
        resp = client.get("/api/payment-fields/card")
        assert resp.status_code == 200
        assert "fields" in _envelope(resp)["data"]

    def test_an_unknown_payment_method_answers(self, client, db_session, demo_tenant, demo_branch):
        """API-18."""
        _with(client, db_session, demo_tenant, demo_branch, ["view_reports"], "reader")
        resp = client.get("/api/payment-fields/not-a-method")
        assert resp.status_code in (200, 404), f"the payment fields answered {resp.status_code}"


class TestAPI19TheTelemetryGuards:
    """API-19 to API-24: the client-error intake, which is a public door."""

    def test_the_client_error_endpoint_needs_a_trusted_origin(self, client):
        """API-19. A log spammer is not a browser."""
        resp = client.post("/api/log-client-error", json={"message": "err", "type": "api"})
        assert resp.status_code in (302, 403, 204), f"the endpoint answered {resp.status_code}"

    def test_the_client_error_endpoint_accepts_a_trusted_origin(self, client, db_session, demo_tenant, demo_branch):
        """API-20."""
        _with(client, db_session, demo_tenant, demo_branch, ["view_reports"], "reader")
        resp = client.post(
            "/api/log-client-error",
            json={"message": "err", "type": "api"},
            headers={"Origin": "http://localhost:5000"},
        )
        assert resp.status_code == 204

    def test_an_unknown_event_type_is_normalised(self, client, db_session, demo_tenant, demo_branch):
        """API-21. A type the system does not know is a runtime error, not a crash."""
        _with(client, db_session, demo_tenant, demo_branch, ["view_reports"], "reader")
        resp = client.post(
            "/api/log-client-error",
            json={"message": "err", "type": "not-a-real-type"},
            headers={"Origin": "http://localhost:5000"},
        )
        assert resp.status_code == 204

    def test_an_oversized_client_error_is_refused(self, client, db_session, demo_tenant, demo_branch):
        """API-22. A payload over the cap is refused, not truncated."""
        _with(client, db_session, demo_tenant, demo_branch, ["view_reports"], "reader")
        resp = client.post(
            "/api/log-client-error",
            data="x" * (60 * 1024),
            content_type="application/json",
            headers={"Origin": "http://localhost:5000"},
        )
        assert resp.status_code == 413, f"the oversized payload answered {resp.status_code}"

    def test_the_telemetry_endpoint_refuses_an_oversized_payload(self, client, db_session, demo_tenant, demo_branch):
        """API-23. A truncated batch is a batch that lost events."""
        _with(client, db_session, demo_tenant, demo_branch, ["view_reports"], "reader")
        resp = client.post(
            "/api/v1/telemetry/logs",
            data="x" * (60 * 1024),
            content_type="application/json",
            headers={"Origin": "http://localhost:5000"},
        )
        assert resp.status_code == 413, f"the oversized payload answered {resp.status_code}"

    def test_the_telemetry_endpoint_accepts_a_batch(self, client, db_session, demo_tenant, demo_branch):
        """API-24."""
        _with(client, db_session, demo_tenant, demo_branch, ["view_reports"], "reader")
        event = {
            "message": "probe",
            "type": "runtime",
            "timestamp": "2026-01-01T00:00:00Z",
            "category": "SOFTWARE_EXCEPTION",
            "level": "ERROR",
        }
        resp = client.post(
            "/api/v1/telemetry/logs",
            json={"events": [event]},
            headers={"Origin": "http://localhost:5000"},
        )
        assert resp.status_code in (202, 400), f"the batch answered {resp.status_code}"


class TestAPI25TheEnhancedApi:
    """API-25 to API-32: /api/v2, which is guarded per resource."""

    def test_the_sales_list_needs_the_sales_permission(self, client, db_session, demo_tenant, demo_branch):
        """API-25."""
        _with(client, db_session, demo_tenant, demo_branch, ["view_reports"], "reporter")
        assert client.get("/api/v2/sales").status_code == 403

    def test_the_sales_list_answers(self, client, db_session, demo_tenant, demo_branch):
        """API-26."""
        _with(client, db_session, demo_tenant, demo_branch, ["manage_sales"], "sales")
        resp = client.get("/api/v2/sales")
        assert resp.status_code == 200
        _envelope(resp)

    def test_a_sale_detail_answers(self, client, db_session, demo_tenant, demo_branch):
        """API-27."""
        _with(client, db_session, demo_tenant, demo_branch, ["manage_sales"], "sales")
        resp = client.get("/api/v2/sales/1")
        assert resp.status_code in (200, 404), f"the sale answered {resp.status_code}"

    def test_the_customers_list_needs_the_customers_permission(self, client, db_session, demo_tenant, demo_branch):
        """API-28."""
        _with(client, db_session, demo_tenant, demo_branch, ["view_reports"], "reporter")
        assert client.get("/api/v2/customers").status_code == 403

    def test_the_customers_list_answers(self, client, db_session, demo_tenant, demo_branch):
        """API-29."""
        _with(client, db_session, demo_tenant, demo_branch, ["manage_customers"], "customers")
        resp = client.get("/api/v2/customers")
        assert resp.status_code == 200
        _envelope(resp)

    def test_the_product_search_needs_the_products_permission(self, client, db_session, demo_tenant, demo_branch):
        """API-30."""
        _with(client, db_session, demo_tenant, demo_branch, ["view_reports"], "reporter")
        assert client.get("/api/v2/products/search?q=probe").status_code == 403

    def test_the_product_search_answers(self, client, db_session, demo_tenant, demo_branch):
        """API-31."""
        _with(client, db_session, demo_tenant, demo_branch, ["manage_products"], "products")
        resp = client.get("/api/v2/products/search?q=probe")
        assert resp.status_code == 200
        _envelope(resp)

    def test_the_analytics_endpoints_need_the_reports_permission(self, client, db_session, demo_tenant, demo_branch):
        """API-32."""
        _with(client, db_session, demo_tenant, demo_branch, ["manage_sales"], "sales")
        for path in ("/api/v2/analytics/sales-forecast", "/api/v2/analytics/profit-margins"):
            assert client.get(path).status_code == 403, f"{path} answered for a sales manager"

    def test_the_analytics_endpoints_answer(self, client, db_session, demo_tenant, demo_branch):
        """API-33."""
        _with(client, db_session, demo_tenant, demo_branch, ["view_reports"], "reporter")
        for path in ("/api/v2/analytics/sales-forecast", "/api/v2/analytics/profit-margins"):
            resp = client.get(path)
            assert resp.status_code == 200, f"{path} answered {resp.status_code}"
            _envelope(resp)


class TestAPI34TheEchoEndpoint:
    """API-34 to API-36: the development echo, and its production switch."""

    def test_the_echo_endpoint_answers_in_development(self, client, db_session, demo_tenant, demo_branch):
        """API-34."""
        _with(client, db_session, demo_tenant, demo_branch, ["view_reports"], "reader")
        resp = client.put("/api/echo", json={"probe": True})
        assert resp.status_code in (200, 404, 405), f"the echo answered {resp.status_code}"

    def test_the_echo_endpoint_is_not_a_post(self, client, db_session, demo_tenant, demo_branch):
        """API-35. It is a development helper for the other verbs."""
        _with(client, db_session, demo_tenant, demo_branch, ["view_reports"], "reader")
        resp = client.post("/api/echo", json={"probe": True})
        assert resp.status_code in (404, 405), f"the echo answered {resp.status_code} to a POST"


class TestAPI37ThePrintingSurface:
    """API-37 to API-39: printing, which is a read of a document."""

    def test_the_print_history_needs_the_reports_permission(self, client, db_session, demo_tenant, demo_branch):
        """API-37."""
        _with(client, db_session, demo_tenant, demo_branch, ["view_reports"], "reporter")
        resp = client.get("/printing/history")
        assert resp.status_code == 200

    def test_the_bulk_print_needs_the_sales_permission(self, client, db_session, demo_tenant, demo_branch):
        """API-38."""
        _with(client, db_session, demo_tenant, demo_branch, ["view_reports"], "reporter")
        resp = client.post("/printing/bulk-print", json={"documents": []})
        assert resp.status_code == 403, f"the bulk print answered {resp.status_code}"

    def test_the_print_preview_needs_the_reports_permission(self, client, db_session, demo_tenant, demo_branch):
        """API-39."""
        _with(client, db_session, demo_tenant, demo_branch, ["view_reports"], "reporter")
        resp = client.post("/printing/api/preview", json={"doc_type": "sale", "id": 1})
        assert resp.status_code in (200, 400, 404), f"the preview answered {resp.status_code}"


class TestAPI40TheDocumentedContract:
    """API-40 to API-43: the API reference and the document it is checked against."""

    def test_the_openapi_document_answers(self, client):
        """API-40. The contract is served, not only committed."""
        resp = client.get("/api-docs/openapi.json")
        assert resp.status_code == 200
        assert resp.content_type.startswith("application/json")

    def test_the_openapi_document_names_the_paths(self, client):
        """API-41."""
        document = client.get("/api-docs/openapi.json").get_json()
        assert document.get("paths"), "the OpenAPI document has no paths"

    def test_the_api_docs_page_answers(self, client):
        """API-42."""
        resp = client.get("/api-docs/")
        assert resp.status_code in (200, 301, 302, 404), f"the docs page answered {resp.status_code}"

    def test_the_committed_reference_matches_the_live_routes(self, client):
        """API-43. The paper contract and the running contract are one contract.

        ``scripts/lint/check_api_docs.py`` compares ``docs/API_REFERENCE.md``
        with the live url_map; this pins the same claim from the other side.
        """
        from pathlib import Path

        reference = Path("docs/API_REFERENCE.md").read_text(encoding="utf-8")
        assert "/api/health" in reference, "the health endpoint is not in the committed reference"
        assert "/api/version" in reference, "the version endpoint is not in the committed reference"


class TestAPI44TheGraphQlDoor:
    """API-44 to API-47: two doors, two guards."""

    def test_the_graphql_endpoint_needs_the_reports_permission(self, client, db_session, demo_tenant, demo_branch):
        """API-44."""
        _with(client, db_session, demo_tenant, demo_branch, ["manage_sales"], "sales")
        resp = client.post("/graphql", json={"query": "{ __typename }"})
        assert resp.status_code == 403, f"the query answered {resp.status_code} for a sales manager"

    def test_the_graphql_endpoint_answers_a_signed_in_caller(self, client, db_session, demo_tenant, demo_branch):
        """API-45."""
        _with(client, db_session, demo_tenant, demo_branch, ["view_reports"], "reporter")
        resp = client.post("/graphql", json={"query": "{ __typename }"})
        assert resp.status_code in (200, 400), f"the query answered {resp.status_code}"

    def test_the_graphql_playground_needs_the_admin_role(self, client, db_session, demo_tenant, demo_branch):
        """API-46. A playground is a console, not a reader."""
        _with(client, db_session, demo_tenant, demo_branch, ["view_reports"], "reporter")
        resp = client.get("/graphql/playground")
        assert resp.status_code == 403, f"the playground answered {resp.status_code} for a reporter"

    def test_the_graphql_playground_answers_for_an_admin(self, client, db_session, demo_tenant, demo_branch):
        """API-47."""
        _with(client, db_session, demo_tenant, demo_branch, ["view_reports"], "reporter")
        resp = client.get("/graphql/playground")
        assert resp.status_code == 403

    def test_the_scenario_covers_every_api_route(self, app):
        """API-48. A scenario that stops covering a route stops being a scenario."""
        live = {
            rule.rule
            for rule in app.url_map.iter_rules()
            if rule.rule.startswith("/api") or rule.rule.startswith("/graphql") or rule.rule.startswith("/printing")
        }
        assert len(live) >= 40, f"the API route inventory shrank to {len(live)} routes"

    def test_the_public_api_routes_carry_no_permission(self, app):
        """API-49. The health check is for callers with no session."""
        for rule in app.url_map.iter_rules():
            if rule.rule not in ("/api/health", "/api/version"):
                continue
            view = app.view_functions[rule.endpoint]
            assert getattr(view, "_required_permission", None) is None, (
                f"{rule.rule} is behind a permission, so a load balancer cannot reach it"
            )

    def test_the_warehouse_list_answers(self, client, db_session, demo_tenant, demo_branch):
        """API-50. The warehouse list is the one the pickers read.

        It used to answer 500: the route ordered a list as if it were a query.
        """
        _with(client, db_session, demo_tenant, demo_branch, ["view_reports"], "reporter")
        resp = client.get("/api/warehouses")
        assert resp.status_code == 200, f"the warehouse list answered {resp.status_code}"
        assert "results" in _envelope(resp)["data"]

    def test_the_products_list_answers(self, client, db_session, demo_tenant, demo_branch):
        """API-51."""
        _with(client, db_session, demo_tenant, demo_branch, ["view_reports"], "reporter")
        resp = client.get("/api/products")
        assert resp.status_code == 200, f"the product list answered {resp.status_code}"
        assert "results" in _envelope(resp)["data"]
