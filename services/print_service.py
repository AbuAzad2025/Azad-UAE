"""
Print Service — Professional Printing Engine
محرك الطباعة الاحترافي مع دعم PDF، طباعة جماعية، سجل طباعة
"""

import logging
from typing import Any

from flask import current_app
from flask_login import current_user

logger = logging.getLogger(__name__)


class PrintService:
    """Professional print service with PDF generation, bulk print, and audit logging."""

    # Valid template names for invoices and receipts
    INVOICE_TEMPLATES = {"modern", "classic", "gulf", "minimal", "simple"}
    RECEIPT_TEMPLATES = {"modern", "classic", "gulf", "minimal", "simple", "payment_voucher"}

    PRINTABLE_DOCUMENTS: dict[str, dict[str, Any]] = {
        "purchase": {
            "template": "purchases/print.html",
            "model": "Purchase",
            "context_key": "purchase",
            "permission": "manage_purchases",
            "filename_attr": "purchase_number",
            "filename_prefix": "purchase",
        },
        "expense": {
            "template": "expenses/print.html",
            "model": "Expense",
            "context_key": "expense",
            "permission": "manage_expenses",
            "filename_attr": "expense_number",
            "filename_prefix": "expense",
        },
        "payroll_slip": {
            "template": "payroll/slip.html",
            "model": "PayrollTransaction",
            "context_key": "slip",
            "permission": "manage_payroll",
            "filename_attr": None,
            "filename_prefix": "salary_slip",
        },
        "cheque": {
            "template": "printing/cheque.html",
            "model": "Cheque",
            "context_key": "cheque",
            "permission": "manage_payments",
            "filename_attr": None,
            "filename_prefix": "cheque",
        },
        "packing_slip": {
            "template": "printing/packing_slip.html",
            "model": "Sale",
            "context_key": "sale",
            "permission": "manage_sales",
            "filename_attr": "sale_number",
            "filename_prefix": "packing_slip",
        },
        "sale": {
            "template": None,  # resolved dynamically via resolve_template()
            "model": "Sale",
            "context_key": "sale",
            "permission": "manage_sales",
            "filename_attr": "sale_number",
            "filename_prefix": "invoice",
        },
        "receipt": {
            "template": None,  # resolved dynamically via resolve_template()
            "model": "Receipt",
            "context_key": "receipt",
            "permission": "manage_payments",
            "filename_attr": "receipt_number",
            "filename_prefix": "receipt",
        },
        "payment": {
            "template": "receipts/payment_voucher.html",
            "model": "Payment",
            "context_key": "payment",
            "permission": "manage_payments",
            "filename_attr": "payment_number",
            "filename_prefix": "payment",
        },
        "customer_statement": {
            "template": "customers/statement_print.html",
            "model": "Customer",
            "context_key": "customer",
            "permission": "manage_customers",
            "filename_attr": None,
            "filename_prefix": "statement",
        },
        "supplier_statement": {
            "template": "suppliers/statement_print.html",
            "model": "Supplier",
            "context_key": "supplier",
            "permission": "manage_suppliers",
            "filename_attr": None,
            "filename_prefix": "statement",
        },
        "advanced_ledger": {
            "template": "ledger/professional_printing.html",
            "model": None,  # no model, custom query
            "context_key": "trial_balance_data",
            "permission": "view_ledger",
            "filename_attr": None,
            "filename_prefix": "trial_balance",
        },
    }

    @staticmethod
    def resolve_template(doc_type, tenant_id=None, requested_template=None):
        """Resolve the print template path for a document type.

        Args:
            doc_type: Document type key (sale, receipt, payment).
            tenant_id: Optional tenant ID to read active_template from InvoiceSettings.
            requested_template: Optional explicit template name from user query param.

        Returns:
            Template path string.
        """
        from models.invoice_settings import InvoiceSettings

        settings = InvoiceSettings.get_active(tenant_id) if tenant_id else None
        active = settings.active_template if settings and settings.active_template else "modern"

        if doc_type == "sale":
            chosen = requested_template if requested_template in PrintService.INVOICE_TEMPLATES else active
            return f"invoices/{chosen}.html"

        if doc_type in ("receipt", "payment"):
            chosen = requested_template if requested_template in PrintService.RECEIPT_TEMPLATES else active
            return f"receipts/{chosen}.html"

        entry = PrintService.PRINTABLE_DOCUMENTS.get(doc_type)
        if entry and entry.get("template"):
            return entry["template"]

        logger.warning("No template resolved for doc_type=%s, falling back to invoices/modern.html", doc_type)
        return "invoices/modern.html"

    @staticmethod
    def _get_model(model_name):
        """Import and return a model class by name (lazy import to avoid circular deps)."""
        import models

        return getattr(models, model_name)

    @staticmethod
    def _get_tenant_context(tenant_id):
        """Build unified print context for any tenant-scoped document."""
        from models.invoice_settings import InvoiceSettings
        from utils.tenant_branding import get_print_header_context
        from utils.tenanting import get_active_tenant_id

        tid = tenant_id or get_active_tenant_id(current_user)
        tenant, settings, company = InvoiceSettings.company_print_context(tid)
        branding = get_print_header_context(tid)
        return {
            "tenant": tenant,
            "settings": settings,
            "company": company,
            "print_branding": branding,
            "print_tenant_id": tid,
        }

    @staticmethod
    def _user_context():
        """Current user info for print metadata."""
        try:
            u = current_user
            return {
                "print_user_name": u.full_name or u.username or "",
                "print_user_id": u.id,
            }
        except Exception:
            return {"print_user_name": "—", "print_user_id": None}

    @staticmethod
    def render_print(template, extra_context=None, tenant_id=None):
        """Render a standalone print template with full tenant context."""
        from flask import render_template

        ctx = PrintService._get_tenant_context(tenant_id)
        ctx.update(PrintService._user_context())
        if extra_context:
            ctx.update(extra_context)
        return render_template(template, **ctx)

    @staticmethod
    def render_pdf(template, extra_context=None, tenant_id=None, filename="document.pdf"):
        """Render template as PDF bytes using WeasyPrint."""

        html = PrintService.render_print(template, extra_context, tenant_id)
        try:
            import os
            import re
            from pathlib import Path

            import weasyprint

            html_ready = html
            try:
                static_folder = current_app.static_folder
                if not static_folder:
                    raise ValueError("static folder is not configured")
                root = os.path.abspath(os.path.join(static_folder, os.pardir))
                root_uri = Path(root).as_uri()
                html_ready = re.sub(
                    r'((?:src|href)=")/static/',
                    rf"\1{root_uri}/static/",
                    html,
                )
            except Exception:
                html_ready = html

            pdf_bytes = weasyprint.HTML(string=html_ready).write_pdf()
            logger.info("PDF generated via WeasyPrint: %s (%d bytes)", filename, len(pdf_bytes))
            return pdf_bytes
        except ImportError:
            logger.warning("WeasyPrint not available, falling back to HTML-only response")
            raise RuntimeError(
                "PDF export requires WeasyPrint to be installed. Please install WeasyPrint for PDF generation."
            )
        except Exception as e:
            logger.error("PDF generation failed: %s", e)
            current_app.logger.error("PDF generation error: %s", e)
            return html.encode("utf-8")

    @staticmethod
    def _json_safe(value):
        """Recursively convert Decimal/datetime values to JSON-serializable primitives."""
        from datetime import date, datetime
        from decimal import Decimal

        if isinstance(value, Decimal):
            return float(value)
        if isinstance(value, datetime | date):
            return value.isoformat()
        if isinstance(value, dict):
            return {k: PrintService._json_safe(v) for k, v in value.items()}
        if isinstance(value, list | tuple):
            return [PrintService._json_safe(v) for v in value]
        return value

    @staticmethod
    def create_snapshot(tenant_id, document_type, document_id, reason="print", document=None):
        """Capture an immutable snapshot of a document at print/finalize/amend time."""
        from extensions import db
        from models.document_snapshot import DocumentSnapshot
        from utils.tenant_branding import resolve_tenant_branding

        try:
            entry = PrintService.PRINTABLE_DOCUMENTS.get(document_type)
            if not entry:
                logger.warning("No registry entry for %s, skipping snapshot", document_type)
                return

            if document is None:
                model_cls = PrintService._get_model(entry["model"])
                query = model_cls.query.filter_by(id=document_id)
                if tenant_id is not None:
                    query = query.filter_by(tenant_id=tenant_id)
                document = query.first()

            if document is None:
                logger.warning("Document %s#%d not found for snapshot", document_type, document_id)
                return

            effective_tenant_id = tenant_id
            if effective_tenant_id is None:
                effective_tenant_id = getattr(document, "tenant_id", None)

            try:
                snapshot_data = document.to_dict() if hasattr(document, "to_dict") else {}
                if not snapshot_data:
                    snapshot_data = {c.name: getattr(document, c.name, None) for c in document.__table__.columns}
            except Exception as e:
                logger.warning("Could not serialize document for snapshot: %s", e)
                snapshot_data = {}

            branding = resolve_tenant_branding(effective_tenant_id)

            snap = DocumentSnapshot(
                tenant_id=effective_tenant_id,
                document_type=document_type,
                document_id=document_id,
                snapshot_data=PrintService._json_safe(snapshot_data),
                branding_snapshot=PrintService._json_safe(branding),
                snapshot_reason=reason,
                created_by=PrintService._user_context().get("print_user_id"),
            )
            db.session.add(snap)
            logger.info("Snapshot created: %s #%d (%s)", document_type, document_id, reason)
        except Exception as e:
            logger.warning("Snapshot creation failed (non-blocking): %s", e)

    @staticmethod
    def audit_print(
        tenant_id,
        document_type,
        document_id,
        user_id=None,
        action="print",
        metadata=None,
    ):
        """Record print action in audit log (flush-based for transaction safety)."""
        try:
            from extensions import db
            from models.print_history import PrintHistory

            record = PrintHistory(
                tenant_id=tenant_id,
                user_id=user_id or PrintService._user_context().get("print_user_id"),
                document_type=document_type,
                document_id=document_id,
                action=action,
                meta=metadata or {},
                ip_address=None,
            )
            db.session.add(record)
            db.session.flush()
            logger.info(
                "Print audit recorded: %s #%d by user %s",
                document_type,
                document_id,
                user_id,
            )
        except Exception as e:
            logger.warning("Print audit failed (non-blocking): %s", e)

    @staticmethod
    def bulk_print_documents(documents, template_map, tenant_id=None):
        """Generate HTML for bulk printing multiple documents (all in one print job)."""

        pages_html = []
        for i, doc in enumerate(documents):
            doc_type = doc.get("type")
            tmpl = template_map.get(doc_type)
            if not tmpl:
                continue
            extra = {
                "bulk_print_index": i + 1,
                "bulk_print_total": len(documents),
            }
            extra.update(doc.get("context", {}))
            html = PrintService.render_print(tmpl, extra, tenant_id)
            pages_html.append(html)

        if not pages_html:
            return '<html><body dir="rtl"><p>لا توجد مستندات للطباعة</p></body></html>'

        combined = (
            '<!DOCTYPE html><html dir="rtl" lang="ar"><head><meta charset="UTF-8">'
            "<style>@page{margin:5mm}body{font-family:Tajawal,Arial,sans-serif}"
            ".page-break{page-break-after:always}</style></head><body>"
        )
        for i, page in enumerate(pages_html):
            if i > 0:
                combined += '<div class="page-break"></div>'
            combined += page
        combined += "</body></html>"
        return combined

    # ─── Route-facing scoped fetches ───

    @staticmethod
    def get_document(model_cls, record_id, tenant_id):
        """Fetch a printable document by id with strict tenant scoping.

        tenant_id is REQUIRED. Passing None raises ValueError so callers cannot
        accidentally skip the security boundary. This complements the SQLAlchemy
        ORM listener (utils/tenant_orm.py) with explicit, defense-in-depth filtering.
        """
        if tenant_id is None:
            raise ValueError("tenant_id is required for security")
        return model_cls.query.filter_by(id=record_id, tenant_id=tenant_id).first()

    @staticmethod
    def get_tenant_document(model_cls, doc_id, tenant_id):
        """Strictly tenant-scoped document fetch (bulk print / preview)."""
        return model_cls.query.filter_by(id=doc_id, tenant_id=tenant_id).first()

    @staticmethod
    def get_shipment_for_sale(sale_id, tenant_id):
        """Shipment linked to a sale (tenant-scoped) or None."""
        from models import Shipment

        return Shipment.query.filter_by(sale_id=sale_id, tenant_id=tenant_id).first()

    @staticmethod
    def history_query(tenant_id):
        """Print-history query for a tenant, newest first."""
        from models.print_history import PrintHistory

        return PrintHistory.query.filter_by(tenant_id=tenant_id).order_by(PrintHistory.created_at.desc())

    @staticmethod
    def list_recent_history(tenant_id, limit=20):
        """Most recent print-history records for a tenant."""
        from models.print_history import PrintHistory

        return (
            PrintHistory.query.filter_by(tenant_id=tenant_id)
            .order_by(PrintHistory.created_at.desc())
            .limit(limit)
            .all()
        )
