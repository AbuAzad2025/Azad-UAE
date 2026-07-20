from unittest.mock import MagicMock, patch

import pytest

from tests.unit.routes.conftest import (
    unauthenticated_client,
)


@pytest.fixture
def graphql_client(app_factory, bypass_admin_auth):
    from routes.graphql import graphql_bp

    app = app_factory(graphql_bp)
    return app.test_client()


def _dev_env(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.delenv("DEBUG", raising=False)


def _prod_env(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("DEBUG", raising=False)


class TestGraphQLValidation:
    def test_empty_query_400(self, graphql_client, monkeypatch):
        _dev_env(monkeypatch)
        resp = graphql_client.post("/graphql", json={"query": ""})
        assert resp.status_code == 400
        assert "required" in resp.get_json()["errors"][0].lower()

    def test_query_too_long_413(self, graphql_client, monkeypatch):
        _dev_env(monkeypatch)
        resp = graphql_client.post("/graphql", json={"query": "x" * 9000})
        assert resp.status_code == 413

    def test_query_depth_exceeded_400(self, graphql_client, monkeypatch):
        _dev_env(monkeypatch)
        deep = "{" * 12 + "id" + "}" * 12
        resp = graphql_client.post("/graphql", json={"query": deep})
        assert resp.status_code == 400
        assert "depth" in resp.get_json()["errors"][0].lower()

    def test_introspection_blocked_in_production(self, graphql_client, monkeypatch):
        _prod_env(monkeypatch)
        resp = graphql_client.post("/graphql", json={"query": "{ __schema { queryType { name } } }"})
        assert resp.status_code == 403

    def test_mutations_disabled_in_production(self, graphql_client, monkeypatch):
        _prod_env(monkeypatch)
        resp = graphql_client.post("/graphql", json={"query": "mutation { noop }"})
        assert resp.status_code == 403

    def test_unauthenticated_401(self, graphql_client, monkeypatch):
        _dev_env(monkeypatch)
        with unauthenticated_client(graphql_client):
            resp = graphql_client.post("/graphql", json={"query": "{ __typename }"})
        assert resp.status_code == 401


class TestGraphQLExecution:
    def test_successful_query_returns_data(self, graphql_client, monkeypatch):
        _dev_env(monkeypatch)
        mock_result = MagicMock()
        mock_result.data = {"__typename": "Query"}
        mock_result.errors = None
        mock_schema = MagicMock()
        mock_schema.execute.return_value = mock_result
        with patch("routes.graphql.build_schema", return_value=mock_schema):
            resp = graphql_client.post("/graphql", json={"query": "{ __typename }"})
        assert resp.status_code == 200
        assert resp.get_json()["data"]["__typename"] == "Query"

    def test_execution_errors_in_response(self, graphql_client, monkeypatch):
        _dev_env(monkeypatch)
        mock_result = MagicMock()
        mock_result.data = None
        mock_result.errors = [Exception("resolver failed")]
        mock_schema = MagicMock()
        mock_schema.execute.return_value = mock_result
        with patch("routes.graphql.build_schema", return_value=mock_schema):
            resp = graphql_client.post("/graphql", json={"query": "{ allSales { id } }"})
        body = resp.get_json()
        assert "errors" in body
        assert "resolver failed" in body["errors"][0]


class TestGraphQLPlayground:
    def test_playground_404_in_production(self, graphql_client, monkeypatch):
        _prod_env(monkeypatch)
        resp = graphql_client.get("/graphql/playground")
        assert resp.status_code == 404

    def test_playground_403_non_owner(self, graphql_client, monkeypatch, bypass_admin_auth):
        _dev_env(monkeypatch)
        bypass_admin_auth.is_owner = False
        resp = graphql_client.get("/graphql/playground")
        assert resp.status_code == 403

    def test_playground_200_for_owner(self, graphql_client, monkeypatch, bypass_admin_auth):
        _dev_env(monkeypatch)
        bypass_admin_auth.is_owner = True
        resp = graphql_client.get("/graphql/playground")
        assert resp.status_code == 200
        assert b"GraphQL Playground" in resp.data
