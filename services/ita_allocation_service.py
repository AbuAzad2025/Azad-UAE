"""Israel Tax Authority — invoice allocation number (מספר הקצאה) client.

Production : https://ita-api.taxes.gov.il/shaam/production/Invoices/v2/Approval
Sandbox    : https://ita-api.taxes.gov.il/shaam/tsandbox/Invoices/v2/Approval
(OAuth2 user-restricted; the tenant stores its access token + environment in
Tax Settings — see ``routes/owner/settings.py`` and ``tenant_secrets``.)

Deliberately a *manual, explicit* action — never a synchronous call inside
sale posting. A POS sale in a dead zone must never fail because the ITA
endpoint is down. The tenant triggers it from the sale page once the sale is
complete; the allocation number is stored on the e-invoice row and printed
on the document.

Failure modes map to the ITA's documented behavior: HTTP errors and a
``confirmation_number`` of "0" / ``approved`` = false mean the request was
rejected; a message explaining why (validation, duplicate, reversed charge)
is surfaced to the user.
"""

from __future__ import annotations

import logging
from decimal import Decimal

import requests

from extensions import db

logger = logging.getLogger(__name__)

PRODUCTION_URL = "https://ita-api.taxes.gov.il/shaam/production/Invoices/v2/Approval"
SANDBOX_URL = "https://ita-api.taxes.gov.il/shaam/tsandbox/Invoices/v2/Approval"

INVOICE_TYPE_TAX_INVOICE = "305"


class ItaAllocationError(ValueError):
    """Raised when the ITA rejects or cannot be reached — message is safe to show."""


class ItaAllocationService:
    @staticmethod
    def enabled(tenant) -> bool:
        return bool(getattr(tenant, "enable_ita_allocation", False))

    @staticmethod
    def eligible(tenant, sale) -> bool:
        threshold = Decimal(str(getattr(tenant, "ita_allocation_threshold", 0) or 0))
        total = Decimal(str(getattr(sale, "total_amount", 0) or 0))
        return ItaAllocationService.enabled(tenant) and total >= threshold

    @staticmethod
    def _digits(value) -> str:
        return "".join(ch for ch in str(value or "") if ch.isdigit())

    @staticmethod
    def request_allocation_number(sale, *, user_id=None) -> dict:
        from models import EInvoice, Tenant
        from services.tenant_secrets_service import TenantSecretsService

        tenant = db.session.get(Tenant, int(sale.tenant_id)) if sale.tenant_id is not None else None
        if tenant is None:
            raise ItaAllocationError("Tenant not found for this sale.")
        if not ItaAllocationService.enabled(tenant):
            raise ItaAllocationError("ITA allocation is disabled for this tenant (Tax Settings → מספר הקצאה).")

        threshold = Decimal(str(getattr(tenant, "ita_allocation_threshold", 0) or 0))
        total = Decimal(str(getattr(sale, "total_amount", 0) or 0))
        if total < threshold:
            raise ItaAllocationError(
                f"The sale total ({total}) is below the allocation threshold ({threshold}). "
                "The allocation number is required only above it."
            )

        token = TenantSecretsService.get(tenant.id, "ita_oauth_token")
        if not token:
            raise ItaAllocationError(
                "No ITA OAuth token stored for this tenant. Store one in Tax Settings "
                "(the token comes from the ITA developer portal / your software-house registration)."
            )

        seller = ItaAllocationService._digits(getattr(tenant, "tax_number", None))
        if len(seller) != 9:
            raise ItaAllocationError("The tenant's VAT number must be exactly 9 digits for the ITA allocation service.")

        customer = getattr(sale, "customer", None)
        buyer = ItaAllocationService._digits(getattr(customer, "tax_number", None)) if customer else ""
        if buyer and len(buyer) != 9:
            raise ItaAllocationError(
                "The customer's VAT number must be exactly 9 digits (or empty for a private customer)."
            )

        base = (
            PRODUCTION_URL
            if (getattr(tenant, "ita_environment", "sandbox") or "sandbox").lower() == "production"
            else SANDBOX_URL
        )
        net = Decimal(str(getattr(sale, "taxable_amount", 0) or 0))
        tax = Decimal(str(getattr(sale, "tax_amount", 0) or 0))
        total_amount = Decimal(str(getattr(sale, "total_amount", 0) or 0))
        issue = getattr(sale, "sale_date", None)
        payload = {
            "Invoice_ID": f"{tenant.id}-{sale.sale_number}"[:50],
            "Invoice_Type": INVOICE_TYPE_TAX_INVOICE,
            "Vat_Number": seller,
            "Invoice_Reference_Number": str(sale.sale_number)[:20],
            "Customer_VAT_Number": buyer,
            "Invoice_Date": issue.strftime("%Y-%m-%d") if issue else "",
            "Payment_Amount": f"{net:.2f}",
            "VAT_Amount": f"{tax:.2f}",
            "Payment_Amount_Including_VAT": f"{total_amount:.2f}",
        }
        payload = {key: value for key, value in payload.items() if value != ""}

        try:
            response = requests.post(
                base,
                json=payload,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                timeout=30,
            )
        except requests.RequestException as exc:
            raise ItaAllocationError(f"Could not reach the ITA service: {exc}") from exc

        try:
            body = response.json()
        except ValueError:
            body = {}

        # The ITA returns the same fields with different casing depending on
        # environment/version — accept both.
        def pick(*names):
            for name in names:
                if body.get(name) not in (None, ""):
                    return body[name]
                if isinstance(body.get("data"), dict):
                    nested = body["data"].get(name)
                    if nested not in (None, ""):
                        return nested
            return None

        status = pick("Status", "status")
        approved = pick("approved", "Approved")
        message = pick("Message", "message") or ""
        confirmation = pick("Confirmation_Number", "confirmation_number", "ConfirmationNumber")
        http_ok = 200 <= response.status_code < 300
        approved_flag = (
            str(approved).lower() in ("true", "1", "yes")
            or (status is not None and int(status) == 200 and str(confirmation) not in (None, "", "0"))
            or (approved is None and status is None and http_ok and confirmation not in (None, "", "0"))
        )
        if not approved_flag:
            error_bits = [
                bit
                for bit in (
                    str(message),
                    f"status={status}" if status is not None else None,
                    f"http={response.status_code}",
                )
                if bit
            ]
            raise ItaAllocationError(
                "The Israel Tax Authority did not approve the invoice allocation: " + "; ".join(error_bits)
            )

        number = str(confirmation)
        if not number.strip():
            raise ItaAllocationError("The ITA approved the request but returned no allocation number.")

        einv = EInvoice.query.filter_by(tenant_id=tenant.id, sale_id=sale.id, doc_type="invoice").first()
        if einv is not None:
            einv.ita_allocation_number = number
            db.session.flush()
        return {
            "allocation_number": number,
            "approved": True,
        }
