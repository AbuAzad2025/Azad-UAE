"""Unit tests for utils/feature_guards.py — SaaS feature gating.

DB-backed: verifies web 403, API JSON FEATURE_LOCKED, unlocked pass-through,
no-tenant passthrough, and blueprint-level install_feature_gate coverage.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from flask import Blueprint
from werkzeug.exceptions import Forbidden

from utils.feature_guards import feature_required, install_feature_gate


def _patch_tenant(tenant_id):
    return patch("utils.tenanting.get_active_tenant_id", return_value=tenant_id)


class TestFeatureRequired:
    def test_unlocked_feature_runs_view(self, app, db_session, sample_tenant):
        sample_tenant.enable_payroll = True
        db_session.commit()

        @feature_required("payroll")
        def _view():
            return "ok"

        with app.test_request_context("/payroll/"):
            with _patch_tenant(sample_tenant.id):
                assert _view() == "ok"

    def test_locked_feature_web_aborts_403(self, app, db_session, sample_tenant):
        sample_tenant.enable_payroll = False
        db_session.commit()

        @feature_required("payroll")
        def _view():
            return "ok"

        with app.test_request_context("/payroll/"):
            with _patch_tenant(sample_tenant.id), pytest.raises(Forbidden):
                _view()

    def test_locked_feature_api_returns_json_403(self, app, db_session, sample_tenant):
        sample_tenant.enable_cheques = False
        db_session.commit()

        @feature_required("cheques")
        def _view():
            return "ok"

        with app.test_request_context("/cheques/api/list", headers={"Accept": "application/json"}):
            with _patch_tenant(sample_tenant.id):
                resp, status = _view()
                assert status == 403
                assert resp.get_json() == {"error": "FEATURE_LOCKED", "feature": "cheques"}

    def test_no_tenant_context_passes_through(self, app):
        @feature_required("payroll")
        def _view():
            return "ok"

        with app.test_request_context("/payroll/"):
            with _patch_tenant(None):
                assert _view() == "ok"

    def test_missing_flag_column_defaults_enabled(self, app, db_session, sample_tenant):
        @feature_required("nonexistent_feature")
        def _view():
            return "ok"

        with app.test_request_context("/x/"):
            with _patch_tenant(sample_tenant.id):
                assert _view() == "ok"


class TestInstallFeatureGate:
    def test_gate_covers_all_blueprint_routes(self, app, db_session, sample_tenant):
        sample_tenant.enable_store = False
        db_session.commit()

        bp = Blueprint("gate_test", __name__, url_prefix="/gate-test")
        install_feature_gate(bp, "store")

        hooks = bp.before_request_funcs.get(None) or []
        assert hooks, "install_feature_gate must register a before_request hook"
        hook = hooks[0]

        with _patch_tenant(sample_tenant.id):
            # Web request → 403 abort.
            with app.test_request_context("/gate-test/"):
                with pytest.raises(Forbidden):
                    hook()
            # API request → JSON FEATURE_LOCKED.
            with app.test_request_context("/gate-test/api/items", headers={"Accept": "application/json"}):
                resp, status = hook()
                assert status == 403
                assert resp.get_json()["error"] == "FEATURE_LOCKED"

            # Unlocking the flag re-opens every gated route on the next request.
            sample_tenant.enable_store = True
            db_session.commit()
            with app.test_request_context("/gate-test/"):
                assert hook() is None
