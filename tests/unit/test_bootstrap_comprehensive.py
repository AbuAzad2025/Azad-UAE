"""Tests for bootstrap/blueprints module."""
import pytest


class TestImportBp:
    def test_import_bp_success(self, app):
        from bootstrap.blueprints import _import_bp
        bp = _import_bp(app, "routes.main", "main_bp")
        assert bp is not None
        assert bp.name == "main"

    def test_import_bp_failure(self, app):
        from bootstrap.blueprints import _import_bp
        with pytest.raises(Exception):
            _import_bp(app, "routes.nonexistent", "bp")


class TestRegisterBlueprints:
    def test_blueprints_exist(self, app):
        bp_names = [bp.name for bp in app.blueprints.values()]
        assert "main" in bp_names
        assert "auth" in bp_names
        assert "printing" in bp_names

    def test_blueprint_url_prefixes(self, app):
        assert app.blueprints["auth"].url_prefix == "/auth"
        assert app.blueprints["printing"].url_prefix == "/printing"


class TestAiFallback:
    def test_make_ai_fallback(self, app):
        from bootstrap.blueprints import _make_ai_fallback
        bp = _make_ai_fallback("Test error")
        assert bp is not None
        assert bp.name == "ai"

    def test_ai_fallback_has_routes(self, app):
        from bootstrap.blueprints import _make_ai_fallback
        bp = _make_ai_fallback("Error")
        assert len(bp.deferred_functions) > 0
