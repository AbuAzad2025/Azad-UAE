"""Unit tests for POST /ledger/fx-revaluation (month-end FX revaluation gate)."""

from __future__ import annotations

from unittest.mock import patch

import pytest


@pytest.fixture
def ledger_client(app_factory, bypass_permission_auth):
    from routes.ledger import ledger_bp

    app = app_factory(ledger_bp)
    return app.test_client()


class TestFxRevaluationRoute:
    def test_fx_revaluation_runs_and_returns_summary(self, ledger_client):
        with (
            patch("utils.tenanting.require_active_tenant_id", return_value=1),
            patch(
                "services.fx_revaluation_service.revaluate_open_items",
                return_value={
                    "ar_count": 2,
                    "ap_count": 1,
                    "ar_diff": "12.5",
                    "ap_diff": "-3.0",
                    "entry_ids": [1, 2],
                    "errors": [],
                    "skipped_existing_period": False,
                },
            ),
        ):
            resp = ledger_client.post("/ledger/fx-revaluation")
        assert resp.status_code == 200, resp.get_json()
        data = resp.get_json()["data"]
        assert data["ar_count"] == 2
        assert data["ap_count"] == 1
        assert data["ar_diff"] == 12.5
        assert data["entry_ids"] == [1, 2]
