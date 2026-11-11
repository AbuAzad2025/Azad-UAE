"""E-Invoice Service — statutory document generation and persistence.

``generate_for_sale`` runs inside the salle-posting transaction (wired from
``SaleService.fulfill_sale``); ``generate_for_return`` from
``ReturnService.create_return``. Both honor the tenant's master switches:

* ``enable_einvoice`` False → no artifacts are produced (a documented opt-out).
* ``zatca_phase2_enabled`` True (KSA only) → the fully signed Phase 2 document
  (ICV/PIH chain, XML-DSig, TLV QR tags 1–9) is produced instead of the
  classic Phase 1 document; the chain counter continues from the tenant's
  last Phase 2 row.
* ``enable_einvoice_credit_notes`` False → returns produce no artifact.

Artifacts persist on ``e_invoices``. Failures in supported jurisdictions
propagate: the caller runs inside ``atomic_transaction``, so a broken
document rolls the sale/return back instead of booking a statutory document
that does not exist. Government submission (ZATCA FATOORA reporting, Israel
Tax Authority allocation) is credential-gated and never faked; the ITA
allocation number is requested explicitly via the sale page action.
"""

from __future__ import annotations

import base64
import logging
from decimal import Decimal

logger = logging.getLogger(__name__)


class EInvoiceService:
    """خدمة توليد الفواتير الإلكترونية — موثّقة محفوظة ومقروءة"""

    # ------------------------------------------------------------------
    # internal helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _tenant(tenant_id):
        from extensions import db
        from models import Tenant

        return db.session.get(Tenant, int(tenant_id)) if tenant_id is not None else None

    @staticmethod
    def _upsert_row(tenant_id, *, sale_id=None, return_id=None, doc_type="invoice"):
        from models import EInvoice

        query = EInvoice.query.filter_by(tenant_id=int(tenant_id))
        if doc_type == "invoice":
            query = query.filter_by(sale_id=sale_id, doc_type="invoice")
        else:
            query = query.filter_by(return_id=return_id, doc_type="credit_note")
        return query.first()

    @staticmethod
    def _upsert_maintenance_row(tenant_id, maintenance_invoice_id):
        """The artifact of a maintenance invoice, if it has one."""
        from models import EInvoice

        return EInvoice.query.filter_by(
            tenant_id=int(tenant_id),
            maintenance_invoice_id=maintenance_invoice_id,
            doc_type="invoice",
        ).first()

    @staticmethod
    def _last_phase2_row(tenant_id):
        """The tenant's highest-ICV Phase 2 artifact (invoice or credit note)."""
        from models import EInvoice

        return (
            EInvoice.query.filter_by(tenant_id=int(tenant_id))
            .filter(EInvoice.invoice_counter_value.isnot(None))
            .order_by(EInvoice.invoice_counter_value.desc())
            .first()
        )

    @staticmethod
    def _hash_or_fallback(xml_payload: str, document: dict) -> str:
        from utils.einvoice_document import invoice_sha256_hex

        return document.get("invoice_hash") or invoice_sha256_hex(xml_payload)

    @staticmethod
    def _save(tenant_id, tenant, document, *, sale_id=None, return_id=None, doc_type="invoice"):
        from extensions import db
        from models import EInvoice

        xml_payload = document["xml_payload"]
        invoice_hash = EInvoiceService._hash_or_fallback(xml_payload, document)
        phase2 = document.get("format", "").startswith("zatca_phase2")

        row = EInvoiceService._upsert_row(tenant_id, sale_id=sale_id, return_id=return_id, doc_type=doc_type)
        fields = {
            "country": tenant.vat_country if tenant is not None else "XX",
            "format": document["format"],
            "doc_type": doc_type,
            "xml_payload": xml_payload,
            "qr_base64": document.get("qr_base64") or None,
            "invoice_hash": invoice_hash,
            "status": "generated",
        }
        if phase2:
            fields["invoice_counter_value"] = document.get("invoice_counter_value")

        if row is not None:
            for key, value in fields.items():
                setattr(row, key, value)
            result = row
        else:
            result = EInvoice(tenant_id=int(tenant_id), sale_id=sale_id, return_id=return_id, **fields)
            db.session.add(result)
        db.session.flush()
        return result

    @staticmethod
    def _save_maintenance(tenant_id, tenant, document, maintenance_invoice_id):
        """Persist the artifact of a maintenance invoice.

        The row hangs off the maintenance document, so the two ledgers never
        share a key and a maintenance artifact can never be mistaken for
        the artifact of a sale.
        """
        from extensions import db
        from models import EInvoice

        xml_payload = document["xml_payload"]
        invoice_hash = EInvoiceService._hash_or_fallback(xml_payload, document)
        phase2 = document.get("format", "").startswith("zatca_phase2")

        row = EInvoiceService._upsert_maintenance_row(tenant_id, maintenance_invoice_id)
        fields = {
            "country": tenant.vat_country if tenant is not None else "XX",
            "format": document["format"],
            "doc_type": "invoice",
            "xml_payload": xml_payload,
            "qr_base64": document.get("qr_base64") or None,
            "invoice_hash": invoice_hash,
            "status": "generated",
        }
        if phase2:
            fields["invoice_counter_value"] = document.get("invoice_counter_value")

        if row is not None:
            for key, value in fields.items():
                setattr(row, key, value)
            result = row
        else:
            result = EInvoice(
                tenant_id=int(tenant_id),
                maintenance_invoice_id=maintenance_invoice_id,
                **fields,
            )
            db.session.add(result)
        db.session.flush()
        return result

    @staticmethod
    def _build_document(tenant, sale_like, *, doc_type: str, billing_reference: str | None):
        """Phase 2 for KSA tenants with the switch on; classic otherwise."""
        from utils.einvoice_document import build_invoice_xml, invoice_sha256_hex
        from utils.localization import get_strategy
        from utils.tax_settings import vat_country

        country = (
            (getattr(tenant, "vat_country", None) or vat_country(getattr(tenant, "id", None)) or "").strip().upper()
        )
        currency = (
            getattr(sale_like, "currency", None) or getattr(tenant, "default_currency", None) or "SAR"
        ).strip() or "SAR"

        if country == "SA" and getattr(tenant, "zatca_phase2_enabled", False):
            from services.tenant_secrets_service import TenantSecretsService
            from utils.einvoice_phase2_document import build_signed_invoice_xml
            from utils.zatca_crypto import ZATCA_INITIAL_PIH

            private_key = TenantSecretsService.get(tenant.id, "zatca_private_key")
            certificate = TenantSecretsService.get(tenant.id, "zatca_certificate")
            if not private_key or not certificate:
                raise ValueError(
                    "ZATCA Phase 2 is enabled but the CSID private key/certificate "
                    "are not stored for this tenant. Store them under Tax Settings first."
                )
            previous = EInvoiceService._last_phase2_row(tenant.id)
            icv = (previous.invoice_counter_value or 0) + 1 if previous else 1
            previous_pih = (
                base64.b64encode(bytes.fromhex(previous.invoice_hash)).decode("ascii")
                if previous is not None
                else ZATCA_INITIAL_PIH
            )
            return build_signed_invoice_xml(
                sale_like,
                tenant,
                icv=icv,
                previous_pih=previous_pih,
                csid_private_key_pem=private_key,
                csid_certificate_pem=certificate,
                doc_type=doc_type,
                currency=currency,
                billing_reference=billing_reference,
            )

        if country == "SA":
            from utils.einvoice_document import zatca_document

            document = zatca_document(
                sale_like, tenant, currency=currency, doc_type=doc_type, billing_reference=billing_reference
            )
            document["format"] = "zatca_credit_note_xml" if doc_type == "credit_note" else document["format"]
            return document

        strategy = get_strategy(country)
        if doc_type == "invoice":
            try:
                return strategy.generate_einvoice(sale_like)
            except NotImplementedError:
                return None
        xml_payload = build_invoice_xml(
            sale_like,
            tenant,
            country=country,
            currency=currency,
            profile_id="reporting",
            doc_type=doc_type,
            billing_reference=billing_reference,
        )
        return {
            "xml_payload": xml_payload,
            "qr_base64": "",
            "invoice_hash": invoice_sha256_hex(xml_payload),
            "format": f"{country.lower()}_credit_note_ubl_xml",
        }

    # ------------------------------------------------------------------
    # public API
    # ------------------------------------------------------------------
    @staticmethod
    def generate_for_sale(sale, country_code: str | None = None):
        """Generate/regenerate the statutory e-invoice for a posted sale."""
        # A sale without a persisted primary key (e.g. a mocked sale in unit
        # tests) has nothing to attach the artifact to — skip instead of
        # crashing the caller. Real sales always have an integer PK.
        try:
            int(sale.id)
        except (TypeError, ValueError, AttributeError):
            return None
        tenant_id = getattr(sale, "tenant_id", None)
        if tenant_id is None:
            from utils.tenanting import get_active_tenant_id

            tenant_id = get_active_tenant_id()
        tenant = EInvoiceService._tenant(tenant_id)
        if tenant is None or not getattr(tenant, "enable_einvoice", True):
            return None

        document = EInvoiceService._build_document(tenant, sale, doc_type="invoice", billing_reference=None)
        if document is None:
            logger.warning(
                "E-invoice not generated for sale %s: jurisdiction %s has no e-invoice profile",
                getattr(sale, "id", None),
                getattr(tenant, "vat_country", None),
            )
            return None
        return EInvoiceService._save(tenant_id, tenant, document, sale_id=sale.id, doc_type="invoice")

    @staticmethod
    def generate_for_maintenance_invoice(invoice):
        """Generate/regenerate the statutory e-invoice for a maintenance invoice.

        A maintenance job is a sale for the tax authority: the customer
        receives a service, pays a tax, and is entitled to the same
        document. So the same UBL builder and the same ZATCA TLV QR are
        used - only the document it hangs off is different.

        The maintenance invoice is adapted to the shape the document
        builder expects (a sale-like object) rather than the builder
        learning a second shape: one statutory document, one builder.
        """
        from types import SimpleNamespace

        try:
            int(invoice.id)
        except (TypeError, ValueError, AttributeError):
            return None

        tenant_id = getattr(invoice, "tenant_id", None)
        if tenant_id is None:
            from utils.tenanting import get_active_tenant_id

            tenant_id = get_active_tenant_id()
        tenant = EInvoiceService._tenant(tenant_id)
        if tenant is None or not getattr(tenant, "enable_einvoice", True):
            return None

        order = invoice.order
        if order is None:
            return None

        lines = []
        for line in list(order.lines):
            lines.append(
                SimpleNamespace(
                    quantity=line.quantity,
                    unit_price=line.unit_price,
                    line_total=line.line_total,
                    product=line.product,
                    product_id=line.product_id,
                    tax_category=getattr(line.product, "tax_category", "standard") or "standard",
                )
            )
        for service_line in list(order.services_lines):
            lines.append(
                SimpleNamespace(
                    quantity=Decimal("1"),
                    unit_price=service_line.unit_price,
                    line_total=service_line.line_total,
                    product=None,
                    product_id=None,
                    tax_category="standard",
                )
            )

        sale_like = SimpleNamespace(
            id=invoice.id,
            tenant_id=tenant_id,
            customer=order.customer,
            sale_number=invoice.invoice_number,
            sale_date=invoice.invoice_date,
            currency=invoice.currency,
            exchange_rate=invoice.exchange_rate,
            tax_rate=invoice.tax_rate,
            subtotal=invoice.subtotal,
            taxable_amount=invoice.taxable_amount,
            tax_amount=invoice.tax_amount,
            total_amount=invoice.total_amount,
            lines=lines,
        )

        document = EInvoiceService._build_document(tenant, sale_like, doc_type="invoice", billing_reference=None)
        if document is None:
            logger.warning(
                "E-invoice not generated for maintenance invoice %s: jurisdiction %s has no e-invoice profile",
                getattr(invoice, "id", None),
                getattr(tenant, "vat_country", None),
            )
            return None
        return EInvoiceService._save_maintenance(tenant_id, tenant, document, invoice.id)

    @staticmethod
    def generate_for_return(product_return, *, net_return_amount=None, tax_amount=None, refund_amount=None):
        """Generate the statutory credit-note document for an approved return.

        Amounts default to what ``ReturnService`` measured; they are passed in
        explicitly because the return model does not persist them.
        """
        from types import SimpleNamespace

        sale = product_return.sale
        tenant_id = getattr(product_return, "tenant_id", None)
        tenant = EInvoiceService._tenant(tenant_id)
        if tenant is None:
            return None
        if not getattr(tenant, "enable_einvoice", True) or not getattr(tenant, "enable_einvoice_credit_notes", True):
            return None

        from decimal import Decimal as _D

        rate = _D(str(getattr(sale, "tax_rate", 0) or 0))
        net = _D(str(net_return_amount if net_return_amount is not None else 0))
        tax = _D(str(tax_amount if tax_amount is not None else 0))
        total = _D(str(refund_amount if refund_amount is not None else (product_return.refund_amount or net + tax)))
        if total <= 0:
            total = _D(str(product_return.total_amount or 0))

        lines = []
        for source_line in product_return.lines:
            lines.append(
                SimpleNamespace(
                    quantity=source_line.quantity,
                    unit_price=source_line.unit_price,
                    line_total=source_line.line_total,
                    product=source_line.product,
                    product_id=source_line.product_id,
                    tax_category=getattr(source_line.product, "tax_category", "standard") or "standard",
                )
            )

        original_sale_number = getattr(sale, "sale_number", None)
        sale_like = SimpleNamespace(
            id=product_return.id,
            sale_number=product_return.return_number,
            tenant_id=tenant_id,
            customer=getattr(sale, "customer", None),
            sale_date=product_return.created_at,
            currency=product_return.currency,
            exchange_rate=product_return.exchange_rate,
            tax_rate=rate,
            tax_amount=tax,
            taxable_amount=net,
            subtotal=net,
            total_amount=total,
            lines=lines,
        )
        document = EInvoiceService._build_document(
            tenant,
            sale_like,
            doc_type="credit_note",
            billing_reference=original_sale_number,
        )
        if document is None:
            logger.warning(
                "E-invoice credit note not generated for return %s: jurisdiction %s has no e-invoice profile",
                getattr(product_return, "id", None),
                getattr(tenant, "vat_country", None),
            )
            return None
        return EInvoiceService._save(tenant_id, tenant, document, return_id=product_return.id, doc_type="credit_note")

    @staticmethod
    def get_for_sale(sale_id, tenant_id=None):
        from models import EInvoice

        query = EInvoice.query.filter_by(sale_id=sale_id, doc_type="invoice")
        if tenant_id is not None:
            query = query.filter_by(tenant_id=int(tenant_id))
        return query.first()

    @staticmethod
    def get_for_return(return_id, tenant_id=None):
        from models import EInvoice

        query = EInvoice.query.filter_by(return_id=return_id, doc_type="credit_note")
        if tenant_id is not None:
            query = query.filter_by(tenant_id=int(tenant_id))
        return query.first()
