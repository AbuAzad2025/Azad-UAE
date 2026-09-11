"""Coverage for small single-line/arc targets in ai_knowledge modules."""

from __future__ import annotations

import ai_knowledge.tool_registry as registry_mod
from ai_knowledge.tool_registry import _cached_tool_params


class TestCov4AutomotiveECUSingleton:
    def test_second_call_returns_cached_instance(self):
        """Arc 1279->1281 in knowledge_base.py: cached singleton is reused."""
        import ai_knowledge.knowledge_base as kb

        first = kb.get_automotive_ecu_knowledge()
        second = kb.get_automotive_ecu_knowledge()
        assert second is first


class TestCov4AdvancedLawsCorporate:
    def test_palestine_corporate_uses_income_tax_rates(self):
        """Arc 127->129 in advanced_laws.py: corporate via income_tax_rates."""
        from ai_knowledge.specialized.advanced_laws import AdvancedLaws

        assert AdvancedLaws.get_tax_info("palestine", "corporate") == "ضريبة الشركات: 15%"

    def test_israel_corporate_uses_income_tax_rates(self):
        from ai_knowledge.specialized.advanced_laws import AdvancedLaws

        assert AdvancedLaws.get_tax_info("israel", "corporate") == "ضريبة الشركات: 23%"

    def test_vat_and_gulf_branches(self):
        from ai_knowledge.specialized.advanced_laws import AdvancedLaws

        assert AdvancedLaws.get_tax_info("palestine", "vat") == "ضريبة القيمة المضافة: 16%"
        assert AdvancedLaws.get_tax_info("uae", "corporate") == "ضريبة الشركات: 9%"
        assert AdvancedLaws.get_tax_info("saudi", "vat") == "ضريبة القيمة المضافة: 15%"

    def test_unknown_country_returns_none_and_unknown_tax_type(self):
        from ai_knowledge.specialized.advanced_laws import AdvancedLaws

        assert AdvancedLaws.get_tax_info("france", "vat") is None
        assert AdvancedLaws.get_tax_info("palestine", "customs") == "معلومات ضريبية غير متاحة"

    def test_corporate_without_rate_tables_falls_through(self):
        """Arc 127->129: corporate lookup with neither rate table present."""
        from ai_knowledge.specialized.advanced_laws import AdvancedLaws

        original = AdvancedLaws.GULF_TAX_LAWS["uae"]
        AdvancedLaws.GULF_TAX_LAWS["uae"] = {"vat_rate": 5}
        try:
            assert AdvancedLaws.get_tax_info("uae", "corporate") == "معلومات ضريبية غير متاحة"
        finally:
            AdvancedLaws.GULF_TAX_LAWS["uae"] = original


class TestCov4CachedToolParams:
    def test_cache_hit_returns_same_object(self):
        """Outer cache hit in tool_registry.py: no schema rebuild."""
        from pydantic import BaseModel

        class _Cov4Args(BaseModel):
            x: int = 1

        name = "cov4_unique_tool_xyz"
        had_saved = name in registry_mod._SCHEMA_CACHE
        saved = registry_mod._SCHEMA_CACHE.pop(name, None)
        try:
            first = _cached_tool_params(name, _Cov4Args)
            second = _cached_tool_params(name, _Cov4Args)
            assert second is first
            assert first.get("properties", {}).get("x") is not None
        finally:
            registry_mod._SCHEMA_CACHE.pop(name, None)
            if had_saved:
                registry_mod._SCHEMA_CACHE[name] = saved

    def test_inner_cache_hit_skips_rebuild(self):
        """Arc 41->45 in tool_registry.py: outer miss but inner hit."""

        class _Cov4FlakyCache(dict):
            def __init__(self, seed):
                super().__init__(seed)
                self.calls = 0

            def get(self, key, default=None):
                self.calls += 1
                if self.calls == 1:
                    return None
                return super().get(key, default)

        cached = {"type": "object", "properties": {}}
        flaky = _Cov4FlakyCache({"cov4_inner_tool": dict(cached)})
        original = registry_mod._SCHEMA_CACHE
        registry_mod._SCHEMA_CACHE = flaky
        try:
            from pydantic import BaseModel

            class _Cov4InnerArgs(BaseModel):
                y: str = "a"

            result = _cached_tool_params("cov4_inner_tool", _Cov4InnerArgs)
            assert result is flaky["cov4_inner_tool"]
            assert flaky.calls == 2
        finally:
            registry_mod._SCHEMA_CACHE = original


class TestCov4CheckEmail:
    def test_valid_email_passes(self):
        """Line 63 in tool_schemas.py: valid address is returned as-is."""
        from ai_knowledge.tool_schemas import CreateCustomerArgs

        args = CreateCustomerArgs(name="عميل", email="user@example.com")
        assert args.email == "user@example.com"

    def test_empty_email_passes(self):
        from ai_knowledge.tool_schemas import CreateCustomerArgs

        args = CreateCustomerArgs(name="عميل", email="")
        assert args.email == ""
