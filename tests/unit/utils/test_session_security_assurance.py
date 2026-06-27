"""Session security — rotate_session preserves auth keys."""
from __future__ import annotations

from unittest.mock import MagicMock


class TestRotateSession:
    def test_clears_and_restores_flask_login_keys(self, mocker):
        mock_session = {}
        mock_session['_flashes'] = [('info', 'hello')]
        mock_session['_user_id'] = '42'
        mock_session['_remember'] = 'set'
        mock_session['_fresh'] = True
        mock_session['csrf_token'] = 'old-token'

        mocker.patch('utils.session_security.session', mock_session)

        from utils.session_security import rotate_session

        rotate_session()

        assert 'csrf_token' not in mock_session
        assert mock_session['_user_id'] == '42'
        assert mock_session['_remember'] == 'set'
        assert mock_session['_fresh'] is True
        assert mock_session['_flashes'] == [('info', 'hello')]

    def test_skips_missing_optional_keys(self, mocker):
        mock_session = {'other': 'data'}
        mocker.patch('utils.session_security.session', mock_session)

        from utils.session_security import rotate_session

        rotate_session()
        assert mock_session == {}
