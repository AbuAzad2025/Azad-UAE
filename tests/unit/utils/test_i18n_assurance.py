"""i18n helpers — gettext wrappers and dictionary t()."""
from __future__ import annotations

from unittest.mock import MagicMock


class TestGettextWrappers:
    def test_underscore_calls_gettext(self, mocker):
        mocker.patch('utils.i18n.gettext', return_value='حفظ')
        from utils.i18n import _
        assert _('Save') == 'حفظ'

    def test_lazy_calls_lazy_gettext(self, mocker):
        mocker.patch('utils.i18n.lazy_gettext', return_value='lazy')
        from utils.i18n import _l
        assert _l('Save') == 'lazy'


class TestGetCurrentLanguage:
    def test_reads_session_language(self, mocker):
        mocker.patch('utils.i18n.session', {'language': 'en'})
        from utils.i18n import get_current_language
        assert get_current_language() == 'en'

    def test_defaults_ar_on_runtime_error(self, mocker):
        mock_session = MagicMock()
        mock_session.get.side_effect = RuntimeError('no request')
        mocker.patch('utils.i18n.session', mock_session)
        from utils.i18n import get_current_language
        assert get_current_language() == 'ar'

    def test_defaults_ar_when_missing(self, mocker):
        mocker.patch('utils.i18n.session', {})
        from utils.i18n import get_current_language
        assert get_current_language() == 'ar'


class TestIsRtl:
    def test_arabic_is_rtl(self, mocker):
        mocker.patch('utils.i18n.get_current_language', return_value='ar')
        from utils.i18n import is_rtl
        assert is_rtl() is True

    def test_english_not_rtl(self, mocker):
        mocker.patch('utils.i18n.get_current_language', return_value='en')
        from utils.i18n import is_rtl
        assert is_rtl() is False


class TestTFunction:
    def test_known_key_arabic(self, mocker):
        mocker.patch('utils.i18n.get_current_language', return_value='ar')
        from utils.i18n import t
        assert t('Save') == 'حفظ'

    def test_known_key_english(self, mocker):
        mocker.patch('utils.i18n.get_current_language', return_value='en')
        from utils.i18n import t
        assert t('Save') == 'Save'

    def test_unknown_key_passthrough(self, mocker):
        mocker.patch('utils.i18n.get_current_language', return_value='ar')
        from utils.i18n import t
        assert t('UnknownKey') == 'UnknownKey'

    def test_format_kwargs(self, mocker):
        mocker.patch('utils.i18n.get_current_language', return_value='en')
        from utils.i18n import t
        assert t('Hello {name}', name='Ahmad') == 'Hello Ahmad'
