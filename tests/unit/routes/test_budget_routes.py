"""Tests for routes/budget.py."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def budget_client(app_factory, bypass_permission_auth):
    from routes.budget import budget_bp

    app = app_factory(budget_bp)
    return app.test_client()


class TestBudgetApiCreate:
    def test_api_create_success(self, budget_client):
        budget = MagicMock(id=7, budget_number="BUD-2026-001")
        with patch("routes.budget.BudgetService.create_budget", return_value=budget):
            resp = budget_client.post(
                "/budgets/api/create",
                json={"name_ar": "ميزانية", "fiscal_year": 2026},
            )
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["success"] is True
        assert data["data"]["id"] == 7
        assert data["data"]["budget_number"] == "BUD-2026-001"
        assert data["message"] == "تم إنشاء الميزانية"
        assert data["errors"] is None

    def test_api_create_validation_error(self, budget_client):
        with patch(
            "routes.budget.BudgetService.create_budget",
            side_effect=ValueError("invalid data"),
        ):
            resp = budget_client.post("/budgets/api/create", json={})
        assert resp.status_code == 400
        data = resp.get_json()
        assert data["success"] is False
        assert data["message"] == "invalid data"
        assert data["data"] is None
