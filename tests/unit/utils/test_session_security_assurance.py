"""Session security — rotate_session preserves auth keys."""

from __future__ import annotations


class TestRotateSession:
    def test_clears_and_restores_flask_login_keys(self, mocker):
        mock_session = {
            "_flashes": [("info", "hello")],
            "_user_id": "42",
            "_remember": "set",
            "_fresh": True,
            "csrf_token": "old-token",
        }

        mocker.patch("utils.session_security.session", mock_session)

        from utils.session_security import rotate_session

        rotate_session()

        assert "csrf_token" not in mock_session
        assert mock_session["_user_id"] == "42"
        assert mock_session["_remember"] == "set"
        assert mock_session["_fresh"] is True
        assert mock_session["_flashes"] == [("info", "hello")]

    def test_skips_missing_optional_keys(self, mocker):
        mock_session = {"other": "data"}
        mocker.patch("utils.session_security.session", mock_session)

        from utils.session_security import rotate_session

        rotate_session()
        assert mock_session == {}
