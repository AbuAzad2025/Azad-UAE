from __future__ import annotations

from models.tenant_store import TenantStore


class TestNormalizeRoutingFieldsGap100:
    def test_none_value_returns_none_direct(self):
        store = TenantStore(tenant_id=1, store_slug="tmp", warehouse_id=1)
        assert store._normalize_routing_fields("store_slug", None) is None
        assert store._normalize_routing_fields("subdomain", None) is None
        assert store._normalize_routing_fields("custom_domain", None) is None

    def test_whitespace_returns_none(self):
        store = TenantStore(tenant_id=1, store_slug="tmp", warehouse_id=1)
        assert store._normalize_routing_fields("store_slug", "   ") is None
        assert store._normalize_routing_fields("subdomain", " \t\n ") is None
        assert store._normalize_routing_fields("custom_domain", "") is None

    def test_strips_and_lowercases(self):
        store = TenantStore(tenant_id=1, store_slug="tmp", warehouse_id=1)
        assert store._normalize_routing_fields("store_slug", "  My-Slug  ") == "my-slug"
        assert store._normalize_routing_fields("subdomain", "  Sub.DOMAIN  ") == "sub.domain"
        assert store._normalize_routing_fields("custom_domain", "  EXAMPLE.COM  ") == "example.com"

    def test_assignment_triggers_validator_none_and_whitespace(self):
        store = TenantStore(tenant_id=1, store_slug="initial", warehouse_id=1)
        store.store_slug = None
        assert store.store_slug is None
        store.subdomain = "   "
        assert store.subdomain is None
        store.custom_domain = ""
        assert store.custom_domain is None

    def test_assignment_triggers_validator_normalization(self):
        store = TenantStore(tenant_id=1, store_slug="initial", warehouse_id=1)
        store.store_slug = "  Hello-World  "
        assert store.store_slug == "hello-world"
        store.subdomain = "  MySub  "
        assert store.subdomain == "mysub"
        store.custom_domain = "  MyDomain.Example.COM  "
        assert store.custom_domain == "mydomain.example.com"

    def test_bracket_like_content_preserved_lowercased(self):
        store = TenantStore(tenant_id=1, store_slug="tmp", warehouse_id=1)
        assert store._normalize_routing_fields("store_slug", "  [Test]  ") == "[test]"
        assert store._normalize_routing_fields("custom_domain", "  [BRACKET].COM  ") == "[bracket].com"

    def test_numeric_value_coerced(self):
        store = TenantStore(tenant_id=1, store_slug="tmp", warehouse_id=1)
        assert store._normalize_routing_fields("store_slug", 123) == "123"
