"""
Print Service — Professional Printing Engine
محرك الطباعة الاحترافي مع دعم PDF، طباعة جماعية، سجل طباعة
"""
from io import BytesIO
from datetime import datetime, timezone
import logging

from flask import render_template, current_app, url_for
from flask_login import current_user
logger = logging.getLogger(__name__)


class PrintService:
    """Professional print service with PDF generation, bulk print, and audit logging."""

    PRINTABLE_DOCUMENTS = {
        'purchase': {
            'template': 'purchases/print.html',
            'model': 'Purchase',
            'context_key': 'purchase',
            'permission': 'manage_purchases',
            'filename_attr': 'purchase_number',
            'filename_prefix': 'purchase',
        },
        'expense': {
            'template': 'expenses/print.html',
            'model': 'Expense',
            'context_key': 'expense',
            'permission': 'manage_expenses',
            'filename_attr': 'expense_number',
            'filename_prefix': 'expense',
        },
        'payroll_slip': {
            'template': 'payroll/slip.html',
            'model': 'PayrollTransaction',
            'context_key': 'slip',
            'permission': 'manage_payroll',
            'filename_attr': None,
            'filename_prefix': 'salary_slip',
        },
        'cheque': {
            'template': 'printing/cheque.html',
            'model': 'Cheque',
            'context_key': 'cheque',
            'permission': 'manage_payments',
            'filename_attr': None,
            'filename_prefix': 'cheque',
        },
        'packing_slip': {
            'template': 'printing/packing_slip.html',
            'model': 'Sale',
            'context_key': 'sale',
            'permission': 'manage_sales',
            'filename_attr': 'sale_number',
            'filename_prefix': 'packing_slip',
        },
        'sale': {
            'template': 'invoices/modern.html',
            'model': 'Sale',
            'context_key': 'sale',
            'permission': 'manage_sales',
            'filename_attr': 'sale_number',
            'filename_prefix': 'invoice',
        },
    }

    @staticmethod
    def _get_model(model_name):
        """Import and return a model class by name (lazy import to avoid circular deps)."""
        import models
        return getattr(models, model_name)

    @staticmethod
    def _get_tenant_context(tenant_id):
        """Build unified print context for any tenant-scoped document."""
        from extensions import db
        from models.invoice_settings import InvoiceSettings
        from utils.tenant_branding import get_print_header_context
        from utils.tenanting import get_active_tenant_id

        tid = tenant_id or get_active_tenant_id(current_user)
        tenant, settings, company = InvoiceSettings.company_print_context(tid)
        branding = get_print_header_context(tid)
        return {
            'tenant': tenant,
            'settings': settings,
            'company': company,
            'print_branding': branding,
            'print_tenant_id': tid,
        }

    @staticmethod
    def _user_context():
        """Current user info for print metadata."""
        try:
            u = current_user
            return {
                'print_user_name': u.full_name or u.username or '',
                'print_user_id': u.id,
            }
        except Exception:
            return {'print_user_name': '—', 'print_user_id': None}

    @staticmethod
    def render_print(template, extra_context=None, tenant_id=None):
        """Render a standalone print template with full tenant context."""
        ctx = PrintService._get_tenant_context(tenant_id)
        ctx.update(PrintService._user_context())
        if extra_context:
            ctx.update(extra_context)
        return render_template(template, **ctx)

    @staticmethod
    def render_pdf(template, extra_context=None, tenant_id=None, filename='document.pdf'):
        """Render template as PDF bytes using WeasyPrint."""
        from utils.number_to_arabic import number_to_arabic_words
        from utils.helpers import format_currency

        html = PrintService.render_print(template, extra_context, tenant_id)
        try:
            import weasyprint
            pdf_bytes = weasyprint.HTML(string=html).write_pdf()
            logger.info("PDF generated via WeasyPrint: %s (%d bytes)", filename, len(pdf_bytes))
            return pdf_bytes
        except ImportError:
            logger.warning("WeasyPrint not available, falling back to HTML-only PDF wrappers")
            pdf_header = (
                b'<!DOCTYPE html><html><head><meta charset="UTF-8">'
                b'<style>body{font-family:sans-serif}</style></head><body>'
            )
            pdf_footer = b'<p style="text-align:center;color:#999;margin-top:2cm">'
            pdf_footer += b'PDF export requires WeasyPrint to be installed.</p></body></html>'
            return pdf_header + html.encode('utf-8') + pdf_footer
        except Exception as e:
            logger.error("PDF generation failed: %s", e)
            current_app.logger.error("PDF generation error: %s", e)
            return html.encode('utf-8')

    @staticmethod
    def create_snapshot(tenant_id, document_type, document_id, reason='print', document=None):
        """Capture an immutable snapshot of a document at print/finalize/amend time."""
        from utils.tenant_branding import resolve_tenant_branding
        from models.document_snapshot import DocumentSnapshot
        from extensions import db

        try:
            entry = PrintService.PRINTABLE_DOCUMENTS.get(document_type)
            if not entry:
                logger.warning("No registry entry for %s, skipping snapshot", document_type)
                return

            if document is None:
                model_cls = PrintService._get_model(entry['model'])
                query = model_cls.query.filter_by(id=document_id)
                if tenant_id is not None:
                    query = query.filter_by(tenant_id=tenant_id)
                document = query.first()

            if document is None:
                logger.warning("Document %s#%d not found for snapshot", document_type, document_id)
                return

            effective_tenant_id = tenant_id
            if effective_tenant_id is None:
                effective_tenant_id = getattr(document, 'tenant_id', None)

            try:
                snapshot_data = document.to_dict() if hasattr(document, 'to_dict') else {}
                if not snapshot_data:
                    snapshot_data = {c.name: getattr(document, c.name, None)
                                     for c in document.__table__.columns}
            except Exception as e:
                logger.warning("Could not serialize document for snapshot: %s", e)
                snapshot_data = {}

            branding = resolve_tenant_branding(effective_tenant_id)

            snap = DocumentSnapshot(
                tenant_id=effective_tenant_id,
                document_type=document_type,
                document_id=document_id,
                snapshot_data=snapshot_data,
                branding_snapshot=branding,
                snapshot_reason=reason,
                created_by=PrintService._user_context().get('print_user_id'),
            )
            db.session.add(snap)
            logger.info("Snapshot created: %s #%d (%s)", document_type, document_id, reason)
        except Exception as e:
            db.session.rollback()
            logger.warning("Snapshot creation failed (non-blocking): %s", e)

    @staticmethod
    def audit_print(tenant_id, document_type, document_id, user_id=None, action='print', metadata=None):
        """Record print action in audit log (flush-based for transaction safety)."""
        try:
            from models.print_history import PrintHistory
            from extensions import db

            record = PrintHistory(
                tenant_id=tenant_id,
                user_id=user_id or PrintService._user_context().get('print_user_id'),
                document_type=document_type,
                document_id=document_id,
                action=action,
                meta=metadata or {},
                ip_address=None,
            )
            db.session.add(record)
            db.session.flush()
            logger.info("Print audit recorded: %s #%d by user %s", document_type, document_id, user_id)
        except Exception as e:
            db.session.rollback()
            logger.warning("Print audit failed (non-blocking): %s", e)

    @staticmethod
    def bulk_print_documents(documents, template_map, tenant_id=None):
        """Generate HTML for bulk printing multiple documents (all in one print job)."""
        from utils.number_to_arabic import number_to_arabic_words
        from utils.helpers import format_currency

        pages_html = []
        for i, doc in enumerate(documents):
            doc_type = doc.get('type')
            tmpl = template_map.get(doc_type)
            if not tmpl:
                continue
            extra = {
                'bulk_print_index': i + 1,
                'bulk_print_total': len(documents),
            }
            extra.update(doc.get('context', {}))
            html = PrintService.render_print(tmpl, extra, tenant_id)
            pages_html.append(html)

        if not pages_html:
            return '<html><body dir="rtl"><p>لا توجد مستندات للطباعة</p></body></html>'

        combined = (
            '<!DOCTYPE html><html dir="rtl" lang="ar"><head><meta charset="UTF-8">'
            '<style>@page{margin:5mm}body{font-family:Tajawal,Arial,sans-serif}'
            '.page-break{page-break-after:always}</style></head><body>'
        )
        for i, page in enumerate(pages_html):
            if i > 0:
                combined += '<div class="page-break"></div>'
            combined += page
        combined += '</body></html>'
        return combined

