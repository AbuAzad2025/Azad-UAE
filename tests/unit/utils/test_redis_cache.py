from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from flask import Flask

from utils.redis_cache import (
    RedisCache,
    cache_customer_balance,
    cache_dashboard_stats,
    cache_model,
    cache_product_stock,
    cache_query_result,
    cached,
    get_cached_customer_balance,
    get_cached_dashboard_stats,
    get_cached_model,
    get_cached_product_stock,
    get_cached_query,
    invalidate_customer_cache,
    invalidate_model_cache,
    invalidate_product_cache,
    rate_limit_check,
)


@pytest.fixture
def flask_app():
    app = Flask(__name__)
    app.config["CACHE_DEFAULT_TIMEOUT"] = 300
    app.config["CACHE_KEY_PREFIX"] = "azad"
    app.logger = MagicMock()
    return app


@pytest.fixture
def redis_client():
    client = MagicMock(name="redis.Redis")
    client.keys.return_value = [b"azad:model:Product:1", b"azad:model:Product:2"]
    client.ttl.return_value = 45
    return client


class TestRedisCacheBasics:
    def test_get_returns_value(self, flask_app):
        with (
            flask_app.app_context(),
            patch("utils.redis_cache.cache.get", return_value="hit"),
        ):
            assert RedisCache.get("k") == "hit"

    def test_get_logs_and_returns_none_on_error(self, flask_app):
        with (
            flask_app.app_context(),
            patch("utils.redis_cache.cache.get", side_effect=RuntimeError("down")),
        ):
            assert RedisCache.get("k") is None
        flask_app.logger.warning.assert_called_once()

    def test_set_uses_default_timeout(self, flask_app):
        with flask_app.app_context(), patch("utils.redis_cache.cache.set") as set_fn:
            assert RedisCache.set("k", {"a": 1}) is True
        set_fn.assert_called_once_with("k", {"a": 1}, timeout=300)

    def test_set_custom_timeout_and_failure(self, flask_app):
        with flask_app.app_context(), patch("utils.redis_cache.cache.set") as set_fn:
            assert RedisCache.set("k", 1, timeout=90) is True
        set_fn.assert_called_once_with("k", 1, timeout=90)

        with (
            flask_app.app_context(),
            patch("utils.redis_cache.cache.set", side_effect=OSError("fail")),
        ):
            assert RedisCache.set("k", 1) is False

    def test_delete_success_and_failure(self, flask_app):
        with (
            flask_app.app_context(),
            patch("utils.redis_cache.cache.delete") as delete_fn,
        ):
            assert RedisCache.delete("k") is True
        delete_fn.assert_called_once_with("k")

        with (
            flask_app.app_context(),
            patch("utils.redis_cache.cache.delete", side_effect=OSError("fail")),
        ):
            assert RedisCache.delete("k") is False

    def test_delete_pattern_uses_redis_client(self, flask_app, redis_client):
        cache_backend = MagicMock()
        cache_backend._client = redis_client
        mock_cache = MagicMock()
        mock_cache.cache = cache_backend
        with flask_app.app_context(), patch("utils.redis_cache.cache", mock_cache):
            assert RedisCache.delete_pattern("model:Product:*") is True
        redis_client.keys.assert_called_once_with("azad:model:Product:*")
        redis_client.delete.assert_called_once()

    def test_delete_pattern_returns_false_without_client(self, flask_app):
        mock_cache = MagicMock()
        mock_cache.cache = MagicMock(spec=[])
        with flask_app.app_context(), patch("utils.redis_cache.cache", mock_cache):
            assert RedisCache.delete_pattern("x") is False

    def test_delete_pattern_logs_and_returns_false_on_error(self, flask_app):
        mock_cache = MagicMock()
        mock_cache.cache = MagicMock()
        mock_cache.cache._client = MagicMock()
        mock_cache.cache._client.keys.side_effect = RuntimeError("redis down")
        with flask_app.app_context(), patch("utils.redis_cache.cache", mock_cache):
            assert RedisCache.delete_pattern("bad:*") is False
        flask_app.logger.warning.assert_called()

    def test_get_many_and_set_many(self, flask_app):
        mock_cache = MagicMock()
        mock_cache.get_many.return_value = {"a": 1}
        with flask_app.app_context(), patch("utils.redis_cache.cache", mock_cache):
            assert RedisCache.get_many(["a"]) == {"a": 1}
        mock_cache.set_many.return_value = None
        with flask_app.app_context(), patch("utils.redis_cache.cache", mock_cache):
            assert RedisCache.set_many({"a": 1, "b": 2}) is True
        mock_cache.set_many.assert_called_with({"a": 1, "b": 2}, timeout=300)

    def test_increment_and_decrement(self, flask_app):
        mock_cache = MagicMock()
        mock_cache.inc.return_value = 3
        mock_cache.dec.return_value = 1
        with flask_app.app_context(), patch("utils.redis_cache.cache", mock_cache):
            assert RedisCache.increment("counter", 2) == 3
            assert RedisCache.decrement("counter") == 1

    def test_bulk_operations_return_defaults_on_error(self, flask_app):
        mock_cache = MagicMock()
        mock_cache.get_many.side_effect = RuntimeError()
        with flask_app.app_context(), patch("utils.redis_cache.cache", mock_cache):
            assert RedisCache.get_many(["a"]) == {}
        mock_cache.set_many.side_effect = RuntimeError()
        with flask_app.app_context(), patch("utils.redis_cache.cache", mock_cache):
            assert RedisCache.set_many({"a": 1}) is False
        mock_cache.inc.side_effect = RuntimeError()
        with flask_app.app_context(), patch("utils.redis_cache.cache", mock_cache):
            assert RedisCache.increment("x") is None
        mock_cache.dec.side_effect = RuntimeError()
        with flask_app.app_context(), patch("utils.redis_cache.cache", mock_cache):
            assert RedisCache.decrement("x") is None


class TestCachedDecorator:
    def test_cache_hit_skips_function(self, flask_app):
        calls = {"count": 0}

        @cached(timeout=120, key_prefix="demo")
        def sample():
            calls["count"] += 1
            return "fresh"

        with (
            flask_app.app_context(),
            patch("utils.redis_cache.RedisCache.get", return_value="cached"),
        ):
            assert sample() == "cached"
        assert calls["count"] == 0

    def test_cache_miss_stores_result_with_args(self, flask_app):
        @cached(timeout=60, key_prefix="items")
        def sample(a, b=2):
            return a + b

        with (
            flask_app.app_context(),
            patch("utils.redis_cache.RedisCache.get", return_value=None) as get_fn,
            patch("utils.redis_cache.RedisCache.set", return_value=True) as set_fn,
        ):
            assert sample(3, b=4) == 7

        get_fn.assert_called_once()
        set_fn.assert_called_once()
        assert set_fn.call_args.args[1] == 7
        assert set_fn.call_args.kwargs["timeout"] == 60


class TestModelAndQueryHelpers:
    def test_model_cache_roundtrip_and_invalidation(self, flask_app):
        with (
            flask_app.app_context(),
            patch("utils.redis_cache.RedisCache.set") as set_fn,
            patch("utils.redis_cache.RedisCache.get", return_value={"id": 1}),
        ):
            cache_model("Customer", 1, {"id": 1})
            assert get_cached_model("Customer", 1) == {"id": 1}
        set_fn.assert_called_with("model:Customer:1", {"id": 1}, timeout=3600)

        with (
            flask_app.app_context(),
            patch("utils.redis_cache.RedisCache.delete") as delete_fn,
        ):
            invalidate_model_cache("Customer", 1)
        delete_fn.assert_called_once_with("model:Customer:1")

        with (
            flask_app.app_context(),
            patch("utils.redis_cache.RedisCache.delete_pattern") as pattern_fn,
        ):
            invalidate_model_cache("Customer")
        pattern_fn.assert_called_once_with("model:Customer:*")

    def test_query_cache_roundtrip(self, flask_app):
        with (
            flask_app.app_context(),
            patch("utils.redis_cache.RedisCache.set") as set_fn,
            patch("utils.redis_cache.RedisCache.get", return_value=[1, 2]),
        ):
            cache_query_result("active_users", [1, 2], timeout=120)
            assert get_cached_query("active_users") == [1, 2]
        set_fn.assert_called_with("query:active_users", [1, 2], timeout=120)


class TestDomainCacheHelpers:
    def test_customer_product_dashboard_caches(self, flask_app):
        with (
            flask_app.app_context(),
            patch("utils.redis_cache.RedisCache.set") as set_fn,
            patch(
                "utils.redis_cache.RedisCache.get",
                side_effect=[100.5, 12, {"sales": 1}],
            ),
        ):
            cache_customer_balance(5, 100.5)
            cache_product_stock(9, 12)
            cache_dashboard_stats(2, {"sales": 1})
            assert get_cached_customer_balance(5) == 100.5
            assert get_cached_product_stock(9) == 12
            assert get_cached_dashboard_stats(2) == {"sales": 1}
        assert set_fn.call_count == 3

    def test_invalidation_helpers(self, flask_app):
        with (
            flask_app.app_context(),
            patch("utils.redis_cache.RedisCache.delete") as delete_fn,
            patch("utils.redis_cache.RedisCache.delete_pattern") as pattern_fn,
        ):
            invalidate_customer_cache(7)
            invalidate_product_cache(8)
        delete_fn.assert_any_call("customer_balance:7")
        delete_fn.assert_any_call("product_stock:8")
        assert pattern_fn.call_count == 2


class TestRateLimitCheck:
    def test_allows_requests_and_sets_expiry_on_first_hit(
        self, flask_app, redis_client
    ):
        cache_backend = MagicMock()
        cache_backend._client = redis_client
        mock_cache = MagicMock()
        mock_cache.cache = cache_backend
        with (
            flask_app.app_context(),
            patch("utils.redis_cache.RedisCache.increment", return_value=1),
            patch("utils.redis_cache.cache", mock_cache),
        ):
            allowed, remaining, reset = rate_limit_check("user:1", limit=10, window=60)
        assert allowed is True
        assert remaining == 9
        assert reset == 45
        redis_client.expire.assert_called_once_with("ratelimit:user:1", 60)

    def test_blocks_when_limit_exceeded(self, flask_app, redis_client):
        cache_backend = MagicMock()
        cache_backend._client = redis_client
        mock_cache = MagicMock()
        mock_cache.cache = cache_backend
        with (
            flask_app.app_context(),
            patch("utils.redis_cache.RedisCache.increment", return_value=11),
            patch("utils.redis_cache.cache", mock_cache),
        ):
            allowed, remaining, _ = rate_limit_check("user:2", limit=10, window=60)
        assert allowed is False
        assert remaining == 0

    def test_fails_open_on_error(self, flask_app):
        with (
            flask_app.app_context(),
            patch(
                "utils.redis_cache.RedisCache.increment",
                side_effect=RuntimeError("redis"),
            ),
        ):
            allowed, remaining, reset = rate_limit_check("user:3", limit=5, window=30)
        assert allowed is True
        assert remaining == 5
        assert reset == 30
