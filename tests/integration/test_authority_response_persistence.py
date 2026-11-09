"""Database-backed response handling; the authority HTTP calls are mocked.

These tests do not establish compliance with either government API.
"""

from decimal import Decimal
from unittest.mock import MagicMock

from models import EInvoice


def _artifact(db_session, sale, country):
    row = EInvoice(
        tenant_id=sale.tenant_id,
        sale_id=sale.id,
        country=country,
        doc_type="invoice",
        format="test",
        xml_payload="<test/>",
        invoice_hash="a" * 64,
        status="generated",
    )
    db_session.add(row)
    db_session.flush()
    return row


def test_zatca_result_persists_and_does_not_send_a_second_time(
    auth_client, db_session, sample_tenant, sample_sale, mocker
):
    sample_tenant.vat_country = "SA"
    sample_tenant.zatca_phase2_enabled = True
    row = _artifact(db_session, sample_sale, "SA")
    row_id = row.id
    db_session.commit()
    mocker.patch("services.tenant_secrets_service.TenantSecretsService.get", return_value="credential")
    response = MagicMock(status_code=200)
    response.json.return_value = {"reportingStatus": "REPORTED"}
    post = mocker.patch("services.zatca_submission_service.requests.post", return_value=response)

    assert auth_client.post(f"/sales/{sample_sale.id}/submit-to-zatca").status_code == 302
    db_session.expire_all()
    assert db_session.get(EInvoice, row_id).status == "submitted"
    assert auth_client.post(f"/sales/{sample_sale.id}/submit-to-zatca").status_code == 302
    assert post.call_count == 1


def test_ita_number_persists_and_does_not_send_a_second_time(
    auth_client, db_session, sample_tenant, sample_sale, mocker
):
    sample_tenant.vat_country = "IL"
    sample_tenant.enable_ita_allocation = True
    sample_tenant.ita_allocation_threshold = Decimal("0")
    sample_tenant.tax_number = "123456789"
    sample_sale.customer.tax_number = "987654321"
    row = _artifact(db_session, sample_sale, "IL")
    row_id = row.id
    db_session.commit()
    mocker.patch("services.tenant_secrets_service.TenantSecretsService.get", return_value="credential")
    response = MagicMock(status_code=200)
    response.json.return_value = {"status": 200, "approved": True, "confirmation_number": "20240704061109183186068226"}
    post = mocker.patch("services.ita_allocation_service.requests.post", return_value=response)

    assert auth_client.post(f"/sales/{sample_sale.id}/request-ita-allocation").status_code == 302
    db_session.expire_all()
    assert db_session.get(EInvoice, row_id).ita_allocation_number == "20240704061109183186068226"
    assert auth_client.post(f"/sales/{sample_sale.id}/request-ita-allocation").status_code == 302
    assert post.call_count == 1
