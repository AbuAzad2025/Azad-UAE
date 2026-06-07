from flask import session
from utils.session_security import rotate_session

class TestRotateSession:
    def test_clears_old_keys(self, app):
        with app.test_request_context():
            session["old_key"] = "old_value"
            rotate_session()
            assert "old_key" not in session
    def test_preserves_user_id(self, app):
        with app.test_request_context():
            session["_user_id"] = "42"
            session["junk"] = "data"
            rotate_session()
            assert session.get("_user_id") == "42"
            assert "junk" not in session
    def test_preserves_remember(self, app):
        with app.test_request_context():
            session["_remember"] = "set"
            rotate_session()
            assert session.get("_remember") == "set"
    def test_preserves_fresh(self, app):
        with app.test_request_context():
            session["_fresh"] = True
            rotate_session()
            assert session.get("_fresh") is True
    def test_preserves_flashes(self, app):
        with app.test_request_context():
            session["_flashes"] = [("info", "msg")]
            rotate_session()
            assert session.get("_flashes") == [("info", "msg")]
    def test_handles_empty_session(self, app):
        with app.test_request_context():
            rotate_session()
            assert session == {}
    def test_preserves_multiple_keys(self, app):
        with app.test_request_context():
            session["_user_id"] = "7"
            session["_remember"] = "yes"
            session["_fresh"] = False
            session["_flashes"] = []
            rotate_session()
            assert session.get("_user_id") == "7"
            assert session.get("_remember") == "yes"
            assert session.get("_fresh") is False
            assert session.get("_flashes") == []
