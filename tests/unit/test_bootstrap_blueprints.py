import os
from unittest.mock import patch, MagicMock
import pytest


class TestRegisterBlueprints:
    def test_registers_all_blueprints(self, app):
        bp_names = [
            "auth", "main", "public", "sales", "pos", "returns",
            "customers", "partners", "suppliers", "purchases",
            "products", "warehouse", "branches", "payments",
            "cheques", "expenses", "payment_vault", "ledger",
            "advanced_ledger", "admin_ledger", "payroll",
            "reports", "treasury", "api_analytics", "gamification",
            "monitoring", "store", "shop", "tenants", "language",
            "whatsapp", "api_docs", "ai", "api", "api_enhanced",
            "graphql", "users", "owner",
        ]
        for name in bp_names:
            assert name in app.blueprints, f"Blueprint '{name}' not registered"

    def test_ai_blueprint_present(self, app):
        assert "ai" in app.blueprints

    def test_pos_blueprint_url_prefix(self, app):
        rules = list(app.url_map.iter_rules())
        pos_rules = [r for r in rules if r.endpoint.startswith("pos.")]
        assert len(pos_rules) > 0

    def test_auth_blueprint_url_prefix(self, app):
        rules = list(app.url_map.iter_rules())
        auth_rules = [r for r in rules if r.endpoint.startswith("auth.")]
        assert len(auth_rules) > 0

    def test_main_blueprint_has_routes(self, app):
        rules = list(app.url_map.iter_rules())
        main_rules = [r for r in rules if r.endpoint.startswith("main.")]
        assert len(main_rules) > 0


class TestImportBp:
    def test_imports_valid_blueprint(self, app):
        from bootstrap.blueprints import _import_bp
        bp = _import_bp(app, "routes.auth", "auth_bp")
        assert bp is not None
        assert hasattr(bp, "name")

    def test_raises_on_invalid_module(self, app):
        from bootstrap.blueprints import _import_bp
        with pytest.raises(Exception):
            _import_bp(app, "routes.nonexistent_xyz", "bp")

    def test_raises_on_missing_var(self, app):
        from bootstrap.blueprints import _import_bp
        with pytest.raises(Exception):
            _import_bp(app, "routes.auth", "nonexistent_bp_var")


class TestAiFallback:
    def test_creates_fallback_blueprint(self):
        from bootstrap.blueprints import _make_ai_fallback
        bp = _make_ai_fallback("Test error")
        assert bp is not None
        assert bp.name == "ai"
        assert bp.url_prefix == "/ai"

    def test_fallback_routes_exist(self):
        from flask import Flask
        from bootstrap.blueprints import _make_ai_fallback
        test_app = Flask(__name__)
        bp = _make_ai_fallback("Test error")
        bp.name = "ai_test"
        test_app.register_blueprint(bp)
        rules = list(test_app.url_map.iter_rules())
        ai_rules = [r for r in rules if r.endpoint.startswith("ai_test.")]
        assert len(ai_rules) >= 2


class TestAiDisabled:
    def test_ai_disabled_env_creates_fallback(self, app):
        from bootstrap.blueprints import register_blueprints
        with patch.dict(os.environ, {"DISABLE_AI": "1"}):
            test_app = MagicMock()
            test_app.blueprints = {}
            test_app.register_blueprint = lambda bp: test_app.blueprints.update({bp.name: bp})
            test_app.app_context = app.app_context
            register_blueprints(test_app)
            assert "ai" in test_app.blueprints
