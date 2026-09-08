"""Coverage-99 boost for extensions.py standalone helpers (no app context)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from extensions import TenantAwareCache, get_locale, get_or_create


class TestGetLocaleOutOfContext:
    def test_returns_default(self):
        assert get_locale() == "ar"


class TestTenantAwareCacheDirect:
    def test_tenant_key_plain(self):
        cache = TenantAwareCache(MagicMock())
        assert cache._tenant_key("x") == "x"

    def test_get_with_plain_cache(self):
        raw = MagicMock()
        raw.get.return_value = "v"
        cache = TenantAwareCache(raw)
        assert cache.get("k") == "v"
        raw.get.assert_called_once_with("k")

    def test_set_with_plain_cache(self):
        raw = MagicMock()
        cache = TenantAwareCache(raw)
        cache.set("k", "v", timeout=10)
        raw.set.assert_called_once_with("k", "v", timeout=10)

    def test_delete_with_plain_cache(self):
        raw = MagicMock()
        cache = TenantAwareCache(raw)
        cache.delete("k")
        raw.delete.assert_called_once_with("k")

    def test_delete_many_with_plain_cache(self):
        raw = MagicMock()
        cache = TenantAwareCache(raw)
        cache.delete_many("a", "b")
        raw.delete_many.assert_called_once_with("a", "b")

    def test_get_many_passthrough(self):
        raw = MagicMock()
        raw.get_many.return_value = ["v1", "v2"]
        cache = TenantAwareCache(raw)
        result = cache.get_many("a", "b")
        assert result == {"a": "v1", "b": "v2"}

    def test_set_many_passthrough(self):
        raw = MagicMock()
        cache = TenantAwareCache(raw)
        cache.set_many({"k": "v"}, timeout=12)
        raw.set_many.assert_called_once_with({"k": "v"}, timeout=12)

    def test_getattr_passthrough(self):
        raw = MagicMock()
        cache = TenantAwareCache(raw)
        assert cache.some_unbound_attr is raw.some_unbound_attr

    def test_init_app(self):
        raw = MagicMock()
        cache = TenantAwareCache(raw)
        app = MagicMock()
        app.config = {"CACHE_TYPE": "null", "APP_ENV": "dev"}
        cache.init_app(app)
        raw.init_app.assert_called_once_with(app, config=None)


class TestGetOrCreate:
    def test_existing_instance(self):
        existing = MagicMock(name="existing")
        session = MagicMock()
        session.query.return_value.filter_by.return_value.first.return_value = existing
        inst, created = get_or_create(session, MagicMock, name="alice")
        assert inst is existing
        assert created is False

    def test_newly_created(self):
        new_inst = MagicMock(name="new")
        model = MagicMock()
        model.return_value = new_inst
        session = MagicMock()
        session.query.return_value.filter_by.return_value.first.return_value = None
        inst, created = get_or_create(session, model, defaults={"x": 1}, name="bob")
        assert inst is new_inst
        assert created is True
        model.assert_called_once_with(name="bob", x=1)

    def test_race_recovery(self):
        race_inst = MagicMock(name="race-existing")
        session = MagicMock()
        session.query.return_value.filter_by.return_value.first.side_effect = [
            None,
            race_inst,
        ]
        with patch.object(session, "flush", side_effect=RuntimeError("race")):
            inst, created = get_or_create(session, MagicMock, name="x")
        assert inst is race_inst
        assert created is False

    def test_race_no_recovery_propagates(self):
        session = MagicMock()
        session.query.return_value.filter_by.return_value.first.side_effect = [
            None,
            None,
        ]
        with patch.object(session, "flush", side_effect=RuntimeError("race")):
            with pytest.raises(RuntimeError):
                get_or_create(session, MagicMock, name="x")
