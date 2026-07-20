"""Route tests for POST /owner/integrations/test/<service>.

The owner_required guard runs for real (anonymous and tenant admins get 404,
the real platform owner gets in). The model boundary
(IntegrationSettings.get_service_config) is mocked with an in-memory row;
mail.send and requests.get are mocked at the service module boundary so the
service's success/failure recording runs for real.
"""

from __future__ import annotations

import uuid

import pytest


@pytest.fixture
def platform_owner_client(client, db_session):
    """Real platform owner (is_owner + tenant_id=None) via real login."""
    from models import Role, User

    unique = str(uuid.uuid4())[:8]
    role = db_session.query(Role).filter_by(slug="owner").first()
    created_role = None
    if not role:
        role = Role(name="Owner", slug="owner", is_active=True)
        db_session.add(role)
        db_session.flush()
        created_role = role
    user = User(
        username=f"powner-{unique}",
        email=f"powner-{unique}@example.com",
        full_name="Platform Owner",
        tenant_id=None,
        role_id=role.id,
        is_owner=True,
    )
    user.set_password("password123")
    db_session.add(user)
    db_session.commit()
    client.post(
        "/auth/login",
        data={"username": user.username, "password": "password123"},
        follow_redirects=False,
    )
    yield client
    db_session.delete(user)
    if created_role is not None:
        db_session.delete(created_role)
    db_session.commit()


def _integration_row(service, config):
    """In-memory IntegrationSettings row (never added to the session)."""
    from models.integration_settings import IntegrationSettings

    row = IntegrationSettings(service_name=service, enabled=True)
    row.set_config(config)
    return row


def _mock_config_lookup(mocker, row):
    return mocker.patch(
        "models.integration_settings.IntegrationSettings.get_service_config",
        return_value=row,
    )


class TestOwnerGuardContract:
    def test_anonymous_gets_404(self, client):
        assert client.post("/owner/integrations/test/email").status_code == 404

    def test_tenant_admin_gets_404(self, auth_client):
        assert auth_client.post("/owner/integrations/test/email").status_code == 404


class TestInvalidService:
    def test_unknown_service_gets_404(self, platform_owner_client, mocker):
        send = mocker.patch("services.integration_service.mail.send")
        resp = platform_owner_client.post("/owner/integrations/test/whatsapp")
        assert resp.status_code == 404
        send.assert_not_called()


class TestEmailConnection:
    _URL = "/owner/integrations/test/email"

    def test_success_returns_ok_and_records(self, platform_owner_client, mocker):
        row = _integration_row("email", {"smtp_user": "owner@example.com", "sender_name": "Azad"})
        _mock_config_lookup(mocker, row)
        send = mocker.patch("services.integration_service.mail.send")

        resp = platform_owner_client.post(self._URL)

        assert resp.status_code == 200
        payload = resp.get_json()
        assert payload["success"] is True
        assert payload["message"]
        send.assert_called_once()
        msg = send.call_args.args[0]
        assert msg.recipients == ["owner@example.com"]
        assert row.last_test_status == "success"
        assert row.last_tested_at is not None
        assert row.last_test_message == payload["message"]

    def test_mail_failure_records_failed(self, platform_owner_client, mocker):
        row = _integration_row("email", {"smtp_user": "owner@example.com"})
        _mock_config_lookup(mocker, row)
        mocker.patch("services.integration_service.mail.send", side_effect=RuntimeError("smtp down"))

        resp = platform_owner_client.post(self._URL)

        assert resp.status_code == 200
        payload = resp.get_json()
        assert payload["success"] is False
        assert "smtp down" in payload["message"]
        assert row.last_test_status == "failed"
        assert row.last_tested_at is not None

    def test_unconfigured_sender_records_failed(self, platform_owner_client, mocker):
        row = _integration_row("email", {})
        _mock_config_lookup(mocker, row)
        send = mocker.patch("services.integration_service.mail.send")

        resp = platform_owner_client.post(self._URL)

        assert resp.status_code == 200
        assert resp.get_json()["success"] is False
        send.assert_not_called()
        assert row.last_test_status == "failed"


class TestCurrencyApiConnection:
    _URL = "/owner/integrations/test/currency_api"

    def test_success_returns_ok_and_records(self, platform_owner_client, mocker):
        row = _integration_row(
            "currency_api",
            {"api_key": "secret-key", "api_provider": "exchangerate", "base_currency": "AED"},
        )
        _mock_config_lookup(mocker, row)
        response = mocker.Mock(status_code=200)
        response.json.return_value = {"result": "success", "base_code": "AED"}
        get = mocker.patch("services.integration_service.requests.get", return_value=response)

        resp = platform_owner_client.post(self._URL)

        assert resp.status_code == 200
        payload = resp.get_json()
        assert payload["success"] is True
        get.assert_called_once()
        args, kwargs = get.call_args
        assert "secret-key" in args[0]
        assert args[0].endswith("/latest/AED")
        assert kwargs["timeout"] == 8
        assert row.last_test_status == "success"
        assert row.last_tested_at is not None

    def test_connection_error_records_failed(self, platform_owner_client, mocker):
        import requests

        row = _integration_row("currency_api", {"api_key": "secret-key"})
        _mock_config_lookup(mocker, row)
        mocker.patch(
            "services.integration_service.requests.get",
            side_effect=requests.exceptions.ConnectionError("no route"),
        )

        resp = platform_owner_client.post(self._URL)

        assert resp.status_code == 200
        payload = resp.get_json()
        assert payload["success"] is False
        assert row.last_test_status == "failed"
        assert row.last_tested_at is not None

    def test_non_200_records_failed(self, platform_owner_client, mocker):
        row = _integration_row("currency_api", {"api_key": "secret-key"})
        _mock_config_lookup(mocker, row)
        response = mocker.Mock(status_code=429)
        mocker.patch("services.integration_service.requests.get", return_value=response)

        resp = platform_owner_client.post(self._URL)

        assert resp.status_code == 200
        payload = resp.get_json()
        assert payload["success"] is False
        assert "429" in payload["message"]
        assert row.last_test_status == "failed"

    def test_unconfigured_api_records_failed(self, platform_owner_client, mocker):
        row = _integration_row("currency_api", {})
        _mock_config_lookup(mocker, row)
        get = mocker.patch("services.integration_service.requests.get")

        resp = platform_owner_client.post(self._URL)

        assert resp.status_code == 200
        assert resp.get_json()["success"] is False
        get.assert_not_called()
        assert row.last_test_status == "failed"
