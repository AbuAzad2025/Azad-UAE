from __future__ import annotations

from contextlib import ExitStack, contextmanager
from unittest.mock import patch

import pytest

from tests.unit.routes.conftest import app_factory, unauthenticated_client


@contextmanager
def _language_patches():
    with ExitStack() as stack:
        stack.enter_context(patch('routes.language.safe_redirect_target', side_effect=lambda url, default: url or '/'))
        yield


@pytest.fixture
def language_client(app_factory):
    from routes.language import language_bp
    app = app_factory(language_bp)
    return app.test_client()


class TestLanguageSet:
    def test_set_arabic(self, language_client):
        with _language_patches():
            resp = language_client.get('/language/set/ar', follow_redirects=False)
        assert resp.status_code == 302
        with language_client.session_transaction() as sess:
            assert sess.get('language') == 'ar'

    def test_set_english(self, language_client):
        with _language_patches():
            resp = language_client.get('/language/set/en?next=/dashboard')
        assert resp.status_code == 302
        with language_client.session_transaction() as sess:
            assert sess.get('language') == 'en'

    def test_invalid_language_ignored(self, language_client):
        with _language_patches():
            resp = language_client.get('/language/set/fr')
        assert resp.status_code == 302
        with language_client.session_transaction() as sess:
            assert sess.get('language') is None

    def test_uses_referrer_when_no_next(self, language_client):
        with _language_patches(), patch('routes.language.safe_redirect_target', return_value='/home'):
            resp = language_client.get('/language/set/en', headers={'Referer': '/home'})
        assert resp.status_code == 302

    def test_unauthenticated_locale_swap(self, language_client):
        with _language_patches(), unauthenticated_client(language_client):
            resp = language_client.get('/language/set/ar?next=/sales')
        assert resp.status_code == 302
        with language_client.session_transaction() as sess:
            assert sess.get('language') == 'ar'

    def test_unsafe_next_falls_back(self, language_client):
        with patch('routes.language.safe_redirect_target', return_value='/safe') as safe:
            resp = language_client.get('/language/set/en?next=//evil.com')
        assert resp.status_code == 302
        safe.assert_called_once()
