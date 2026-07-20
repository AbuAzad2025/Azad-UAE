"""Unit tests for routes/ai_routes/blueprint.py — AI blueprint definition.

Verifies the blueprint's public contract: name, url prefix, package re-export
identity, and that importing the package registers the AI url rules.
"""

from __future__ import annotations


class TestAiBlueprintDefinition:
    def test_name_and_prefix(self):
        from routes.ai_routes.blueprint import ai_bp

        assert ai_bp.name == "ai"
        assert ai_bp.url_prefix == "/ai"

    def test_package_reexports_same_object(self):
        import routes.ai_routes
        from routes.ai_routes.blueprint import ai_bp

        assert routes.ai_routes.ai_bp is ai_bp

    def test_analytics_module_imported_from_package(self):
        import routes.ai_routes
        from routes.ai_routes import analytics

        assert routes.ai_routes.analytics is analytics


class TestAiBlueprintRegistration:
    def test_registered_on_application(self, app):
        assert "ai" in app.blueprints

    def test_analytics_rules_exist(self, app):
        rules = {rule.rule: rule for rule in app.url_map.iter_rules()}
        assert "/ai/predict-sales" in rules
        assert rules["/ai/predict-sales"].endpoint == "ai.predict_sales"
        assert "GET" in rules["/ai/predict-sales"].methods

    def test_smart_price_rule_is_post(self, app):
        rules = {rule.rule: rule for rule in app.url_map.iter_rules()}
        assert "/ai/smart-price" in rules
        assert "POST" in rules["/ai/smart-price"].methods
