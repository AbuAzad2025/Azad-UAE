"""Unit tests for routes/owner/blueprint.py — owner blueprint definition.

Verifies the blueprint's public contract: name, url prefix, package re-export
identity, IP-guard wiring, and that importing the package registers owner url
rules from all sub-modules (core, backups, maintenance, ...).
"""

from __future__ import annotations


class TestOwnerBlueprintDefinition:
    def test_name_and_prefix(self):
        from routes.owner.blueprint import owner_bp

        assert owner_bp.name == "owner"
        assert owner_bp.url_prefix == "/owner"

    def test_package_reexports_same_object(self):
        import routes.owner
        from routes.owner.blueprint import owner_bp

        assert routes.owner.owner_bp is owner_bp

    def test_ip_guard_wired_as_before_request(self):
        import routes.owner

        assert callable(routes.owner._owner_ip_guard)
        # Blueprint-scoped before-request handlers are tracked on the blueprint.
        before_funcs = [fn for funcs in routes.owner.owner_bp.before_request_funcs.values() for fn in funcs]
        assert routes.owner._owner_ip_guard in before_funcs


class TestOwnerBlueprintRegistration:
    def test_registered_on_application(self, app):
        assert "owner" in app.blueprints

    def test_submodule_rules_exist(self, app):
        rules = {rule.rule for rule in app.url_map.iter_rules()}
        # routes/owner/backups.py
        assert "/owner/backups/list" in rules
        assert "/owner/backup-now" in rules
        # routes/owner/maintenance.py
        assert "/owner/maintenance/fix-cost-centers" in rules
        assert "/owner/maintenance/cleanup-test-dbs" in rules
