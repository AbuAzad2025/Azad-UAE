"""Stage 4 regressions: analytics RBAC, safe empty states, template/JS safety."""

from __future__ import annotations

import uuid
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture
def reports_only_client(client, db_session, sample_tenant):
    from models import Permission, Role, User

    unique = uuid.uuid4().hex[:8]
    permission = Permission.query.filter_by(code="view_reports").first()
    if permission is None:
        permission = Permission(code="view_reports", name="view_reports", name_ar="view_reports", category="ai-test")
        db_session.add(permission)
        db_session.flush()
    role = Role(name=f"Reports {unique}", slug=f"reports_{unique}", is_active=True)
    role.permissions.append(permission)
    db_session.add(role)
    db_session.flush()
    user = User(
        username=f"reports-{unique}",
        email=f"reports-{unique}@example.com",
        full_name="Reports Only",
        tenant_id=sample_tenant.id,
        role_id=role.id,
    )
    user.set_password("password123")
    db_session.add(user)
    db_session.commit()
    client.post(
        "/auth/login",
        data={"username": user.username, "password": "password123"},
        follow_redirects=False,
    )
    return client


def test_margin_endpoint_requires_cost_visibility(reports_only_client):
    assert reports_only_client.get("/ai/analyze-margins").status_code == 403


def test_margin_endpoint_allows_cost_visibility(auth_client, mocker):
    mocker.patch(
        "services.ai_service.AIService.analyze_profit_margins",
        return_value={"overall": {"margin": 20}},
    )
    resp = auth_client.get("/ai/analyze-margins")
    assert resp.status_code == 200
    assert resp.get_json()["data"]["overall"]["margin"] == 20


def test_margin_empty_data_keeps_envelope(auth_client, mocker):
    mocker.patch(
        "services.ai_service.AIService.analyze_profit_margins",
        return_value={"success": False, "message": "لا توجد مبيعات"},
    )
    resp = auth_client.get("/ai/analyze-margins")
    assert resp.status_code == 200
    assert resp.get_json()["success"] is True
    assert resp.get_json()["data"]["success"] is False


def test_business_insights_tolerates_malformed_items(auth_client, mocker):
    mocker.patch(
        "services.ai_service.AIService.generate_business_insights",
        return_value=[{"type": "warning"}, "garbage"],
    )
    resp = auth_client.get("/ai/business-insights")
    assert resp.status_code == 200
    insights = resp.get_json()["data"]["insights"]
    assert len(insights) == 1
    assert insights[0]["icon"] == "⚠️"


def test_analytics_requires_tenant_for_tenant_user(auth_client):
    with (
        patch("routes.ai_routes.analytics.get_active_tenant_id", return_value=None),
        patch("routes.ai_routes.analytics.is_platform_authority", return_value=False),
    ):
        resp = auth_client.get("/ai/predict-sales", headers={"Accept": "application/json"})
    assert resp.status_code == 403
    assert resp.get_json()["success"] is False


def test_assistant_template_is_local_first_and_xss_safe():
    source = (ROOT / "templates" / "ai" / "assistant.html").read_text(encoding="utf-8")

    assert "localStorage.getItem('ai_mode') || 'local'" in source
    assert "{% if ai_can_see_costs %}" in source
    assert "textContent = text" in source
    assert ".html(r." not in source
    assert ".html(data." not in source
    assert "aria-label=" in source


def test_action_response_is_json_even_when_stream_requested(ai_client, mock_ai_service):
    with (
        patch(
            "ai_knowledge.action_dispatcher.action_dispatcher.parse_chat_action",
            return_value=("customer_balance", {"name": "Ahmad"}),
        ),
        patch("routes.ai_routes.chat._user_can_ai_execute_actions", return_value=True),
        patch(
            "ai_knowledge.action_dispatcher.action_dispatcher.dispatch",
            return_value=type("R", (), {"success": True, "message": "done"})(),
        ),
    ):
        resp = ai_client.post(
            "/ai/chat",
            json={"message": "رصيد: أحمد", "stream": True},
            headers={"Accept": "text/event-stream"},
        )

    assert resp.status_code == 200
    assert resp.mimetype != "text/event-stream"
    assert resp.get_json()["data"]["action_executed"] is True
