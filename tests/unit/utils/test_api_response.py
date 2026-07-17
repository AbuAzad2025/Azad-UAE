from __future__ import annotations

import pytest
from flask import Flask

from utils.api_response import error_response, paginated_response, success_response


@pytest.fixture
def flask_app():
    return Flask(__name__)


class TestSuccessResponse:
    def test_returns_standard_success_envelope(self, flask_app):
        with flask_app.app_context():
            body, status = success_response(
                data={"id": 1},
                message="ok",
                meta={"trace": "abc"},
                status_code=201,
            )
        payload = body.get_json()
        assert status == 201
        assert payload["success"] is True
        assert payload["data"] == {"id": 1}
        assert payload["message"] == "ok"
        assert payload["errors"] is None
        assert payload["meta"] == {"trace": "abc"}


class TestErrorResponse:
    def test_returns_standard_error_envelope(self, flask_app):
        with flask_app.app_context():
            body, status = error_response(
                message="invalid",
                errors=["field required"],
                status_code=422,
                meta={"field": "name"},
            )
        payload = body.get_json()
        assert status == 422
        assert payload["success"] is False
        assert payload["data"] is None
        assert payload["message"] == "invalid"
        assert payload["errors"] == ["field required"]
        assert payload["meta"] == {"field": "name"}

    def test_defaults_empty_errors_list(self, flask_app):
        with flask_app.app_context():
            body, status = error_response("bad request")
        payload = body.get_json()
        assert status == 400
        assert payload["errors"] == []


class TestPaginatedResponse:
    def test_builds_pagination_metadata(self, flask_app):
        with flask_app.app_context():
            body, status = paginated_response(
                items=[{"id": 1}],
                page=2,
                per_page=10,
                total=25,
                message="listed",
            )
        payload = body.get_json()
        assert status == 200
        assert payload["success"] is True
        assert payload["data"] == [{"id": 1}]
        pagination = payload["meta"]["pagination"]
        assert pagination["page"] == 2
        assert pagination["per_page"] == 10
        assert pagination["total"] == 25
        assert pagination["pages"] == 3
        assert pagination["has_next"] is True
        assert pagination["has_prev"] is True

    def test_first_page_has_no_previous(self, flask_app):
        with flask_app.app_context():
            body, _ = paginated_response([], page=1, per_page=5, total=3)
        pagination = body.get_json()["meta"]["pagination"]
        assert pagination["has_prev"] is False
        assert pagination["has_next"] is False
