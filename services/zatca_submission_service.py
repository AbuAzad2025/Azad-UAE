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
        from utils.tenanting import tenant_query

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

        # The HTTP handler owns the transaction. Lock this tenant's invoice
        # until the result is saved so two requests cannot submit it at once.
        einv = (
            tenant_query(EInvoice)
            .filter_by(tenant_id=tenant.id, sale_id=sale.id, doc_type="invoice")
            .with_for_update()
            .first()
        )
        if einv is None:
            raise ZatcaSubmissionError(
                "No statutory e-invoice artifact exists for this sale — post the sale again "
                "or regenerate the document before submitting."
            )
        if not einv.xml_payload:
            raise ZatcaSubmissionError("The stored e-invoice artifact has no XML payload.")
        payload_xml = einv.xml_payload
        if "Signature" not in payload_xml:
            # FATOORA reporting expects a signed invoice. Sign with the
            # tenant's CSID key when it parses; otherwise warn loudly and
            # fall back to the stored (unsigned) payload so the flow is not
            # silently dead for tenants who have not stored a key yet.
            try:
                from utils.zatca_signing import sign_xml

                payload_xml = sign_xml(payload_xml, private_key, certificate)
                logger.info(
                    "Signed e-invoice XML for tenant %s sale %s before ZATCA submission.",
                    tenant.id,
                    sale.id,
                )
            except ValueError:
                logger.warning(
                    "Submitting unsigned e-invoice XML for tenant %s sale %s to ZATCA; "
                    "FATOORA expects a signed document and may reject it.",
                    tenant.id,
                    sale.id,
                )
        if einv.status == "submitted":
            raise ZatcaSubmissionError(
                "This invoice is marked submitted; verify the authority response before resending."
            )

        base = (
            PRODUCTION_URL
            if (getattr(tenant, "zatca_environment", "sandbox") or "sandbox").lower() == "production"
            else SANDBOX_URL
        )

        try:
            response = requests.post(
                base,
                data=payload_xml.encode("utf-8"),
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
        except ValueError as exc:
            raise ZatcaSubmissionError(
                "ZATCA returned an unrecognized response; submission was not confirmed."
            ) from exc
        if not isinstance(body, dict):
            raise ZatcaSubmissionError("ZATCA returned an unrecognized response; submission was not confirmed.")

        http_ok = 200 <= response.status_code < 300
        reporting_status = body.get("reportingStatus")
        validation = body.get("validationResults")
        malformed_validation = validation is not None and not isinstance(validation, dict)
        validation = validation if isinstance(validation, dict) else {}
        errors = validation.get("errorMessages") or []
        validation_failed = (
            malformed_validation
            or bool(errors)
            or str(validation.get("status") or "").upper()
            in (
                "ERROR",
                "FAILED",
            )
        )
        accepted = http_ok and not validation_failed and str(reporting_status).upper() == "REPORTED"
        if not accepted:
            detail = "; ".join(str(e.get("message") if isinstance(e, dict) else e) for e in errors) or str(body)[:400]
            raise ZatcaSubmissionError(f"ZATCA did not accept the invoice (HTTP {response.status_code}): {detail}")

        einv.status = "submitted"
        db.session.flush()
        return {
            "submitted": True,
            "status": str(reporting_status),
            "response": body,
        }
