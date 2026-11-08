"""E-Invoice Service — statutory document generation for posted sales.

``generate_for_sale(sale)`` produces the country-specific statutory document
(UBL 2.1-shaped XML; KSA additionally the ZATCA TLV QR) and persists it on an
``e_invoices`` row — one row per sale, regenerated in place on re-issue.

Unsupported jurisdictions (``NullStrategy``) are a no-op with a warning log,
not a failure: the sale proceeds and no artifact row is created. Any error
while building a statutory artifact for a *supported* country propagates —
the caller runs inside ``atomic_transaction``, so a broken document rolls the
sale back instead of selling with no statutory record.

Government-gateway submission (ZATCA Phase 2 CSID signing, Israel Tax
Authority allocation number, PMA/FTA access points) requires tenant
credentials and is a separate, credential-gated phase. Nothing here claims
a government accepted anything.
"""


class EInvoiceService:
    """خدمة توليد الفواتير الإلكترونية وحفظها"""

    @staticmethod
    def generate_for_sale(sale, country_code: str | None = None):
        """Generate (or regenerate) the statutory e-invoice row for ``sale``.

        Returns the ``models.EInvoice`` row, or ``None`` in an unsupported
        jurisdiction. Raises in supported jurisdictions on any failure.
        """
        from extensions import db
        from models import EInvoice
        from utils.localization import get_strategy
        from utils.tax_settings import vat_country

        tenant_id = getattr(sale, "tenant_id", None)
        if country_code is None:
            tenant_id_ctx = tenant_id
            if tenant_id_ctx is None:
                from utils.tenanting import get_active_tenant_id

                tenant_id_ctx = get_active_tenant_id()
            country_code = vat_country(tenant_id_ctx) if tenant_id_ctx else "PS"
        country = (country_code or "").strip().upper()

        strategy = get_strategy(country)
        try:
            document = strategy.generate_einvoice(sale)
        except NotImplementedError:
            from flask import current_app

            current_app.logger.warning(
                "E-invoice not generated for sale %s: jurisdiction %s has no e-invoice profile",
                getattr(sale, "id", None),
                country,
            )
            return None

        xml_payload = document["xml_payload"]
        from utils.einvoice_document import invoice_sha256_hex

        invoice_hash = document.get("invoice_hash") or invoice_sha256_hex(xml_payload)

        existing = EInvoice.query.filter_by(tenant_id=tenant_id, sale_id=sale.id).first()
        if existing is not None:
            existing.country = country
            existing.format = document["format"]
            existing.xml_payload = xml_payload
            existing.qr_base64 = document.get("qr_base64") or None
            existing.invoice_hash = invoice_hash
            existing.status = "generated"
            row = existing
        else:
            row = EInvoice(
                tenant_id=tenant_id,
                sale_id=sale.id,
                country=country,
                format=document["format"],
                xml_payload=xml_payload,
                qr_base64=document.get("qr_base64") or None,
                invoice_hash=invoice_hash,
                status="generated",
            )
            db.session.add(row)
        db.session.flush()
        return row

    @staticmethod
    def get_for_sale(sale_id, tenant_id=None):
        from models import EInvoice

        query = EInvoice.query.filter_by(sale_id=sale_id)
        if tenant_id is not None:
            query = query.filter_by(tenant_id=int(tenant_id))
        return query.first()
