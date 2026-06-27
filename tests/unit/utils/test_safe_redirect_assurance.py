"""Safe redirect URL validation — open-redirect prevention."""
from __future__ import annotations

import pytest

from utils.safe_redirect import is_safe_redirect_url, safe_redirect_target


class TestIsSafeRedirectUrl:
    @pytest.mark.parametrize(
        'url,expected',
        [
            (None, False),
            ('', False),
            ('   ', False),
            ('https://evil.com', False),
            ('//evil.com/path', False),
            ('http://evil.com', False),
            ('/dashboard', True),
            ('/sales/list?x=1', True),
            ('dashboard', False),
        ],
    )
    def test_url_matrix(self, url, expected):
        assert is_safe_redirect_url(url) is expected

    def test_rejects_parsed_scheme(self, mocker):
        parsed = mocker.MagicMock(scheme='http', netloc='')
        mocker.patch('utils.safe_redirect.urlparse', return_value=parsed)
        assert is_safe_redirect_url('/looks/relative') is False


class TestSafeRedirectTarget:
    def test_returns_safe_relative_url(self, app):
        with app.test_request_context('/'):
            assert safe_redirect_target('/reports') == '/reports'

    def test_falls_back_to_default_endpoint(self, app):
        with app.test_request_context('/'):
            target = safe_redirect_target('https://evil.com', default_endpoint='main.dashboard')
            assert target.endswith('/dashboard') or 'dashboard' in target

    def test_rejects_unsafe_and_uses_url_for(self, app, mocker):
        with app.test_request_context('/'):
            mocker.patch('utils.safe_redirect.url_for', return_value='/safe')
            assert safe_redirect_target('//bad') == '/safe'
