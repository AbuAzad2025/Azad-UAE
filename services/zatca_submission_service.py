"""ZATCA FATOORA submission — report a Phase 2 signed simplified invoice.

Mirrors ``ItaAllocationService``: a manual, explicit action (never inside the
sale transaction — FATOORA availability must never block a sale). The
tenant's CSID (certificate + private key + the ZATCA-issued CSID token) is
read from the encrypted tenant secrets.

Endpoints (per ZATCA FATOORA API documentation):
  sandbox:     https://gw-fatoora.zatca.gov.sa/e-invoicing/developer-portal/invoices/reporting/single
  production:  https://gw-fatoora.zatca.gov.sa/e-invoicing/core/invoices/reporting/single
"""

from __future__ import annotations

import logging

import requests

from extensions import db

logger = logging.getLogger(__name__)

SANDBOX_URL = "https://gw-fatoora.zatca.gov.sa/e-invoicing/developer-portal/invoices/reporting/single"
PRODUCTION_URL = "https://gw-fatoora.zatca.gov.sa/e-invoicing/core/invoices/reporting/single"


class ZatcaSubmissionError(ValueError):
    """Raised when FATOORA rejects or cannot be reached — message is user-safe."""


class ZatcaSubmissionService:
    @staticmethod
    def enabled(tenant) -> bool:
        return bool(getattr(tenant, "zatca_phase2_enabled", False))

    @staticmethod
    def submit(sale, *, user_id=None) -> dict:
        from models import EInvoice, Tenant
        from services.tenant_secrets_service import TenantSecretsService

        tenant = db.session.get(Tenant, int(sale.tenant_id)) if sale.tenant_id is not None else None
        if tenant is None:
            raise ZatcaSubmissionError("Tenant not found for this sale.")
        if not ZatcaSubmissionService.enabled(tenant):
            raise ZatcaSubmissionError("ZATCA Phase 2 is disabled for this tenant — enable it in Tax Settings first.")

        csid = TenantSecretsService.get(tenant.id, "zatca_csid")
        private_key = TenantSecretsService.get(tenant.id, "zatca_private_key")
        certificate = TenantSecretsService.get(tenant.id, "zatca_certificate")
        if not (csid and private_key and certificate):
            raise ZatcaSubmissionError(
                "ZATCA Phase 2 is enabled but the CSID (token, private key and "
                "certificate) are not all stored. Complete them in Tax Settings first."
            )

        einv = EInvoice.query.filter_by(tenant_id=tenant.id, sale_id=sale.id, doc_type="invoice").first()
        if einv is None:
            raise ZatcaSubmissionError(
                "No statutory e-invoice artifact exists for this sale — post the sale again "
                "or regenerate the document before submitting."
            )
        if not einv.xml_payload:
            raise ZatcaSubmissionError("The stored e-invoice artifact has no XML payload.")

        base = (
            PRODUCTION_URL
            if (getattr(tenant, "zatca_environment", "sandbox") or "sandbox").lower() == "production"
            else SANDBOX_URL
        )

        try:
            response = requests.post(
                base,
                data=einv.xml_payload.encode("utf-8"),
                headers={
                    "Authorization": f"Bearer {csid}",
                    "Content-Type": "application/xml",
                    "Accept": "application/json",
                },
                timeout=30,
            )
        except requests.RequestException as exc:
            raise ZatcaSubmissionError(f"Could not reach the ZATCA FATOORA platform: {exc}") from exc

        try:
            body = response.json()
        except ValueError:
            body = {"raw": response.text[:500]}

        http_ok = 200 <= response.status_code < 300
        # FATOORA returns reportingStatus / clearanceStatus + validationResults.
        reporting_status = (
            body.get("reportingStatus")
            or body.get("clearanceStatus")
            or body.get("status")
            or ("SUCCESS" if http_ok else None)
        )
        accepted = http_ok and str(reporting_status).upper() in (
            "SUCCESS",
            "REPORTED",
            "CLEARED",
            "200",
            "OK",
            "APPROVED",
        )
        if not accepted:
            errors = body.get("validationResults", {}).get("errorMessages", []) if isinstance(body, dict) else []
            detail = "; ".join(str(e.get("message") if isinstance(e, dict) else e) for e in errors) or str(body)[:400]
            raise ZatcaSubmissionError(f"ZATCA did not accept the invoice (HTTP {response.status_code}): {detail}")

        einv.status = "submitted"
        db.session.flush()
        return {
            "submitted": True,
            "status": str(reporting_status),
            "response": body,
        }
