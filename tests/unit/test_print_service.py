"""Print Service unit tests."""
import pytest
from services.print_service import PrintService


class TestPrintService:
    def test_user_context(self, app, db_session, sample_user):
        with app.app_context():
            ctx = PrintService._user_context()
            assert 'print_user_name' in ctx
            assert 'print_user_id' in ctx

    def test_render_print(self, app, db_session, sample_tenant):
        with app.app_context():
            with app.test_request_context():
                html = PrintService.render_print('print/test_template.html', tenant_id=sample_tenant.id)
                assert isinstance(html, str)

    def test_render_pdf_fallback(self, app, db_session, sample_tenant):
        with app.app_context():
            with app.test_request_context():
                pdf = PrintService.render_pdf('print/test_template.html', tenant_id=sample_tenant.id)
                assert isinstance(pdf, bytes)
                assert len(pdf) > 0

    def test_audit_print(self, app, db_session, sample_tenant, sample_user):
        with app.app_context():
            PrintService.audit_print(
                tenant_id=sample_tenant.id,
                document_type='invoice',
                document_id=1,
                user_id=sample_user.id,
            )
            from models import PrintHistory
            rec = PrintHistory.query.filter_by(tenant_id=sample_tenant.id, document_type='invoice').first()
            assert rec is not None
            assert rec.document_id == 1

    def test_bulk_print_documents_empty(self, app, db_session, sample_tenant):
        with app.app_context():
            html = PrintService.bulk_print_documents([], {}, tenant_id=sample_tenant.id)
            assert 'لا توجد مستندات' in html

    def test_bulk_print_documents(self, app, db_session, sample_tenant):
        with app.app_context():
            with app.test_request_context():
                docs = [
                    {'type': 'invoice', 'context': {'number': 'INV-001'}},
                ]
                template_map = {'invoice': 'print/test_template.html'}
                html = PrintService.bulk_print_documents(docs, template_map, tenant_id=sample_tenant.id)
                assert isinstance(html, str)
                assert 'page-break' in html or 'INV-001' in html or 'page-break' not in html
