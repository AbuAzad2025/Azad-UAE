"""Cov4: redis_cache — fallback guards, decorator, helpers, rate limit."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import utils.redis_cache as rc
from utils.redis_cache import RedisCache, cached


def _boom(*a, **k):
    raise RuntimeError("cache down")


def test_get_set_delete_fallback(app):
    with app.test_request_context("/"):
        with patch.object(rc, "cache") as mc:
            mc.get.side_effect = RuntimeError("x")
            assert RedisCache.get("k") is None  # 18-22
            mc.set.side_effect = RuntimeError("x")
            assert RedisCache.set("k", "v") is False  # 27-34
            mc.delete.side_effect = RuntimeError("x")
            assert RedisCache.delete("k") is False  # 39-44
            mc.get_many.side_effect = RuntimeError("x")
            assert RedisCache.get_many(["a"]) == {}  # 63-67
            mc.set_many.side_effect = RuntimeError("x")
            assert RedisCache.set_many({"a": 1}) is False  # 73-79
            mc.inc.side_effect = RuntimeError("x")
            assert RedisCache.increment("k") is None  # 84-88
            mc.dec.side_effect = RuntimeError("x")
            assert RedisCache.decrement("k") is None  # 93-97


def test_set_default_timeout_and_pattern(app):
    with app.test_request_context("/"):
        app.config["CACHE_DEFAULT_TIMEOUT"] = 300
        app.config["CACHE_KEY_PREFIX"] = "testprefix"
        with patch.object(rc, "cache") as mc:
            mc.set.return_value = True
            assert RedisCache.set("k", "v") is True  # 28-30 default timeout
            mc.set_many.return_value = True
            assert RedisCache.set_many({"a": 1}) is True  # 73-75
        fake_client = MagicMock()
        fake_client.keys.return_value = []
        from types import SimpleNamespace as _SN

        with patch.object(rc, "cache", _SN(cache=_SN(_client=fake_client))):
            assert RedisCache.delete_pattern("p*") is True  # 49-55
        with patch.object(rc, "cache", _SN(cache=object())):
            assert RedisCache.delete_pattern("p*") is False  # no _client -> False
        boom = MagicMock()
        boom.cache._client.keys.side_effect = RuntimeError("x")
        with patch.object(rc, "cache", boom):
            assert RedisCache.delete_pattern("p*") is False  # 56-58


def test_cached_decorator_hit_miss(app):
    with app.test_request_context("/"):
        calls = {"n": 0}

        @cached(timeout=60, key_prefix="v")
        def _fn(a, b=1):
            calls["n"] += 1
            return a + b

        with patch.object(rc.RedisCache, "get", return_value=99):
            assert _fn(1) == 99  # 119-122 hit
        with (
            patch.object(rc.RedisCache, "get", return_value=None),
            patch.object(rc.RedisCache, "set", return_value=True),
        ):
            assert _fn(2, b=3) == 5  # 124-128 miss with args suffix 115-117
            assert _fn(2) == 3  # default b=1, null cache always misses


def test_model_query_balance_helpers(app):
    with app.test_request_context("/"):
        with (
            patch.object(rc.RedisCache, "set", return_value=True),
            patch.object(rc.RedisCache, "get", return_value="d"),
            patch.object(rc.RedisCache, "delete", return_value=True),
        ):
            rc.cache_model("User", 1, {"a": 1})  # 135-138
            assert rc.get_cached_model("User", 1) == "d"  # 141-144
            rc.invalidate_model_cache("User", 1)  # 147-151 with id
            rc.invalidate_model_cache("User")  # pattern
            rc.cache_query_result("q", [1])  # 157-160
            assert rc.get_cached_query("q") == "d"  # 163-166
            rc.cache_customer_balance(1, 5)  # 200-203
            assert rc.get_cached_customer_balance(1) == "d"  # 206-209
            rc.cache_product_stock(1, 5)  # 212-215
            assert rc.get_cached_product_stock(1) == "d"  # 218-221
            rc.cache_dashboard_stats(1, {})  # 224-227
            assert rc.get_cached_dashboard_stats(1) == "d"  # 230-233
            rc.invalidate_customer_cache(1)  # 236-239
            rc.invalidate_product_cache(2)  # 242-245


def test_rate_limit_paths(app):
    with app.test_request_context("/"):
        fake_client = MagicMock()
        fake_client.ttl.return_value = 50
        fake_cache = MagicMock()
        fake_cache.cache._client = fake_client
        with patch.object(rc.RedisCache, "increment", return_value=1), patch.object(rc, "cache", fake_cache):
            allowed, remaining, _ttl = rc.rate_limit_check("u", limit=2, window=60)  # 181-194
            assert allowed is True and remaining == 1
        with patch.object(rc.RedisCache, "increment", side_effect=RuntimeError("x")):
            allowed, remaining, window = rc.rate_limit_check("u")  # 195-197
            assert allowed is True and remaining == 60
