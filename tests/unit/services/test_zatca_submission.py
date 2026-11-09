"""Unit tests for ZATCA FATOORA submission (manual action: HTTP failures never block a sale)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from services.zatca_submission_service import ZatcaSubmissionError, ZatcaSubmissionService

SALE = MagicMock(tenant_id=11, id=3)


def _tenant(**kwargs):
    tenant = MagicMock(zatca_phase2_enabled=True, zatca_environment="sandbox", id=11)
    for key, value in kwargs.items():
        setattr(tenant, key, value)
    return tenant


class TestEnabled:
    def test_enabled(self):
        assert ZatcaSubmissionService.enabled(_tenant()) is True

    def test_disabled(self):
        assert ZatcaSubmissionService.enabled(_tenant(zatca_phase2_enabled=False)) is False


class TestSubmitGuards:
    def test_missing_tenant(self, mocker):
        mock_db = mocker.patch("services.zatca_submission_service.db")
        mock_db.session.get.return_value = None
        with pytest.raises(ZatcaSubmissionError, match="Tenant not found"):
            ZatcaSubmissionService.submit(SALE)

    def test_disabled_tenant(self, mocker):
        mock_db = mocker.patch("services.zatca_submission_service.db")
        mock_db.session.get.return_value = _tenant(zatca_phase2_enabled=False)
        with pytest.raises(ZatcaSubmissionError, match="disabled"):
            ZatcaSubmissionService.submit(SALE)

    def test_missing_secrets(self, mocker):
        mock_db = mocker.patch("services.zatca_submission_service.db")
        mock_db.session.get.return_value = _tenant()
        mocker.patch("services.tenant_secrets_service.TenantSecretsService.get", return_value=None)
        with pytest.raises(ZatcaSubmissionError, match="CSID"):
            ZatcaSubmissionService.submit(SALE)

    def _secrets(self, mocker):
        mocker.patch(
            "services.tenant_secrets_service.TenantSecretsService.get",
            side_effect=lambda tid, name: "x",
        )

    def test_missing_einvoice(self, mocker):
        mock_db = mocker.patch("services.zatca_submission_service.db")
        mock_db.session.get.return_value = _tenant()
        self._secrets(mocker)
        einvoice_model = mocker.patch("models.EInvoice")
        einvoice_model.query.filter_by.return_value.first.return_value = None
        with pytest.raises(ZatcaSubmissionError, match="artifact"):
            ZatcaSubmissionService.submit(SALE)

    def test_empty_payload(self, mocker):
        mock_db = mocker.patch("services.zatca_submission_service.db")
        mock_db.session.get.return_value = _tenant()
        self._secrets(mocker)
        einvoice_model = mocker.patch("models.EInvoice")
        einvoice_model.query.filter_by.return_value.first.return_value = MagicMock(xml_payload="")
        with pytest.raises(ZatcaSubmissionError, match="payload"):
            ZatcaSubmissionService.submit(SALE)


class TestSubmitHttp:
    def _post_setup(self, mocker, body, status_code=200, environment="sandbox"):
        mock_db = mocker.patch("services.zatca_submission_service.db")
        mock_db.session.get.return_value = _tenant(zatca_environment=environment)
        mocker.patch(
            "services.tenant_secrets_service.TenantSecretsService.get",
            side_effect=lambda tid, name: "x",
        )
        einvoice_model = mocker.patch("models.EInvoice")
        einvoice_row = MagicMock(xml_payload="<x/>", status="draft")
        einvoice_model.query.filter_by.return_value.first.return_value = einvoice_row
        response = MagicMock(status_code=status_code, text=str(body))
        response.json.return_value = body
        post = mocker.patch("services.zatca_submission_service.requests.post", return_value=response)
        return einvoice_row, post

    def test_network_error(self, mocker):
        import requests

        mock_db = mocker.patch("services.zatca_submission_service.db")
        mock_db.session.get.return_value = _tenant()
        mocker.patch(
            "services.tenant_secrets_service.TenantSecretsService.get",
            side_effect=lambda tid, name: "x",
        )
        einvoice_model = mocker.patch("models.EInvoice")
        einvoice_model.query.filter_by.return_value.first.return_value = MagicMock(xml_payload="<x/>")
        mocker.patch(
            "services.zatca_submission_service.requests.post",
            side_effect=requests.RequestException("down"),
        )
        with pytest.raises(ZatcaSubmissionError, match="Could not reach"):
            ZatcaSubmissionService.submit(SALE)

    def test_rejected_with_validation_errors(self, mocker):
        body = {"validationResults": {"errorMessages": [{"message": "bad"}]}}
        self._post_setup(mocker, body, status_code=400)
        with pytest.raises(ZatcaSubmissionError, match="did not accept"):
            ZatcaSubmissionService.submit(SALE)

    def test_success_marks_submitted(self, mocker):
        einvoice_row, post = self._post_setup(mocker, {"reportingStatus": "REPORTED"})
        result = ZatcaSubmissionService.submit(SALE)
        assert result["submitted"] is True
        assert result["status"] == "REPORTED"
        assert einvoice_row.status == "submitted"
        post.assert_called_once()
        headers = post.call_args.kwargs["headers"]
        assert headers["Authorization"] == "Bearer x"

    def test_production_environment_url(self, mocker):
        einvoice_row, post = self._post_setup(mocker, {"clearanceStatus": "CLEARED"}, environment="production")
        result = ZatcaSubmissionService.submit(SALE)
        assert result["status"] == "CLEARED"
        assert "core/invoices" in post.call_args.args[0]

    def test_http_ok_without_status_word(self, mocker):
        einvoice_row, post = self._post_setup(mocker, {})
        assert ZatcaSubmissionService.submit(SALE)["status"] == "SUCCESS"

    def test_non_json_body_falls_back_to_raw(self, mocker):
        import requests  # noqa: F401

        mock_db = mocker.patch("services.zatca_submission_service.db")
        mock_db.session.get.return_value = _tenant()
        mocker.patch(
            "services.tenant_secrets_service.TenantSecretsService.get",
            side_effect=lambda tid, name: "x",
        )
        einvoice_model = mocker.patch("models.EInvoice")
        einvoice_model.query.filter_by.return_value.first.return_value = MagicMock(xml_payload="<x/>")
        response = MagicMock(status_code=200, text="plain ok")
        response.json.side_effect = ValueError("not json")
        mocker.patch("services.zatca_submission_service.requests.post", return_value=response)
        result = ZatcaSubmissionService.submit(SALE)
        assert result["status"] == "SUCCESS"
        assert result["response"] == {"raw": "plain ok"}
