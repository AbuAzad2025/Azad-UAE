from __future__ import annotations

import pytest
from flask import Flask, session

from utils.shop_i18n import shop_lang, t


@pytest.fixture
def shop_app():
    app = Flask(__name__)
    app.config['SECRET_KEY'] = 'shop-test'
    return app


class TestShopLang:
    def test_defaults_to_arabic(self, shop_app):
        with shop_app.test_request_context():
            assert shop_lang() == 'ar'

    def test_shop_lang_session_key(self, shop_app):
        with shop_app.test_request_context():
            session['shop_lang'] = 'en'
            assert shop_lang() == 'en'

    def test_language_session_fallback(self, shop_app):
        with shop_app.test_request_context():
            session['language'] = 'EN'
            assert shop_lang() == 'en'

    def test_unknown_lang_normalizes_to_ar(self, shop_app):
        with shop_app.test_request_context():
            session['shop_lang'] = 'fr'
            assert shop_lang() == 'ar'

    def test_explicit_default_used_when_session_empty(self, shop_app):
        with shop_app.test_request_context():
            assert shop_lang(default='en') == 'en'


class TestTranslate:
    def test_known_key_arabic(self, shop_app):
        with shop_app.test_request_context():
            assert t('cart') == 'السلة'

    def test_known_key_english(self, shop_app):
        with shop_app.test_request_context():
            assert t('cart', lang='en') == 'Cart'

    def test_missing_key_returns_key(self, shop_app):
        with shop_app.test_request_context():
            assert t('not_a_real_key_xyz') == 'not_a_real_key_xyz'

    def test_partial_entry_falls_back_to_arabic(self, shop_app):
        with shop_app.test_request_context():
            assert t('cart', lang='xx') == 'السلة'
