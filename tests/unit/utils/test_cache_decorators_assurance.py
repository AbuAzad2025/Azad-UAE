"""Cache decorators — tenant-scoped keys and invalidation."""
from __future__ import annotations

from unittest.mock import MagicMock


class TestTenantCacheSalt:
    def test_returns_tenant_id_from_g(self, app):
        from utils.cache_decorators import _tenant_cache_salt
        with app.test_request_context('/'):
            from flask import g
            g.active_tenant_id = 7
            assert _tenant_cache_salt() == '7'

    def test_returns_empty_outside_request(self):
        from utils.cache_decorators import _tenant_cache_salt
        assert _tenant_cache_salt() == ''


class TestCachedQuery:
    def test_cache_hit_skips_function(self, app, mocker):
        mocker.patch('utils.cache_decorators.cache.get', return_value='cached')
        from utils.cache_decorators import cached_query

        @cached_query(timeout=60, key_prefix='test')
        def expensive(x):
            return x * 2

        with app.app_context():
            assert expensive(5) == 'cached'

    def test_cache_miss_stores_result(self, app, mocker):
        mocker.patch('utils.cache_decorators.cache.get', return_value=None)
        mock_set = mocker.patch('utils.cache_decorators.cache.set')
        from utils.cache_decorators import cached_query

        @cached_query(timeout=30)
        def compute(a, b=1):
            return a + b

        with app.test_request_context('/'):
            from flask import g
            g.tenant_id = 3
            assert compute(2, b=3) == 5
        mock_set.assert_called_once()

    def test_cache_set_failure_still_returns(self, app, mocker):
        mocker.patch('utils.cache_decorators.cache.get', return_value=None)
        mocker.patch('utils.cache_decorators.cache.set', side_effect=RuntimeError('redis down'))
        from utils.cache_decorators import cached_query

        @cached_query()
        def fn():
            return 99

        with app.app_context():
            assert fn() == 99


class TestInvalidateCache:
    def test_delete_many_when_available(self, mocker):
        mock_cache = MagicMock()
        mock_cache.delete_many = MagicMock()
        mocker.patch('extensions.cache', mock_cache)
        from utils.cache_decorators import invalidate_cache
        invalidate_cache('prefix:*')
        mock_cache.delete_many.assert_called_once_with('prefix:*')

    def test_delete_fallback(self, mocker):
        mock_cache = MagicMock(spec=['delete'])
        mocker.patch('extensions.cache', mock_cache)
        from utils.cache_decorators import invalidate_cache
        invalidate_cache('single-key')
        mock_cache.delete.assert_called_once_with('single-key')

    def test_swallows_exceptions(self, mocker):
        mocker.patch('extensions.cache', side_effect=RuntimeError('no cache'))
        from utils.cache_decorators import invalidate_cache
        invalidate_cache('x')

    def test_delete_many_exception_swallowed(self, mocker):
        mock_cache = MagicMock()
        mock_cache.delete_many.side_effect = RuntimeError('fail')
        mocker.patch('extensions.cache', mock_cache)
        from utils.cache_decorators import invalidate_cache
        invalidate_cache('pattern')
