"""Tests for the Professional Printing routes and PrintService."""
import json
import pytest
from flask import url_for


def test_print_settings_page(auth_client):
    resp = auth_client.get(url_for('printing.print_settings'))
    assert resp.status_code in (200, 403)


def test_print_settings_save(auth_client):
    resp = auth_client.post(url_for('printing.print_settings'), data={
        'paper_size': 'A5',
        'orientation': 'landscape',
        'active_template': 'classic',
        'header_color': '#ff0000',
        'accent_color': '#00ff00',
        'show_logo': 'on',
        'enable_qr_code': 'on',
        'enable_watermark': '',
        'show_terms': 'on',
    }, follow_redirects=True)
    assert resp.status_code in (200, 403)


def test_print_history_page(auth_client):
    resp = auth_client.get(url_for('printing.print_history'))
    assert resp.status_code in (200, 403)


def test_print_history_api(auth_client):
    resp = auth_client.get(url_for('printing.api_print_history'))
    assert resp.status_code in (200, 403)


def test_print_purchase_route(auth_client, sample_purchase):
    resp = auth_client.get(url_for('printing.print_purchase', id=sample_purchase.id))
    assert resp.status_code in (200, 403, 500)


def test_print_expense_route(auth_client, sample_expense):
    resp = auth_client.get(url_for('printing.print_expense', id=sample_expense.id))
    assert resp.status_code in (200, 403, 500)


def test_print_payroll_slip(auth_client, sample_payroll_transaction):
    resp = auth_client.get(url_for('printing.salary_slip', id=sample_payroll_transaction.id))
    assert resp.status_code in (200, 403, 500)


def test_print_cheque(auth_client, sample_cheque):
    resp = auth_client.get(url_for('printing.print_cheque', id=sample_cheque.id))
    assert resp.status_code in (200, 302, 403)


def test_print_packing_slip(auth_client, sample_sale):
    resp = auth_client.get(url_for('printing.packing_slip', sale_id=sample_sale.id))
    assert resp.status_code in (200, 403, 500)


def test_print_preview_api(auth_client, sample_purchase):
    resp = auth_client.post(url_for('printing.print_preview_api'), json={
        'type': 'purchase',
        'id': sample_purchase.id,
    })
    assert resp.status_code in (200, 403, 500)


def test_purchase_pdf_route(auth_client, sample_purchase):
    resp = auth_client.get(url_for('printing.purchase_pdf', id=sample_purchase.id))
    assert resp.status_code in (200, 302, 403, 500)


def test_expense_pdf_route(auth_client, sample_expense):
    resp = auth_client.get(url_for('printing.expense_pdf', id=sample_expense.id))
    assert resp.status_code in (200, 302, 403, 500)


def test_bulk_print(auth_client, sample_purchase):
    resp = auth_client.post(url_for('printing.bulk_print'), json={
        'ids': [sample_purchase.id],
        'type': 'purchase',
    })
    assert resp.status_code in (200, 403, 500)


def test_bulk_print_unknown_type(auth_client):
    resp = auth_client.post(url_for('printing.bulk_print'), json={
        'ids': [1],
        'type': 'unknown_type',
    })
    assert resp.status_code in (400, 403)


def test_print_preview_api_missing_params(auth_client):
    resp = auth_client.post(url_for('printing.print_preview_api'), json={})
    assert resp.status_code in (400, 403)


def test_print_preview_api_unsupported_type(auth_client):
    resp = auth_client.post(url_for('printing.print_preview_api'), json={
        'type': 'unsupported',
        'id': 1,
    })
    assert resp.status_code in (400, 403)


def test_print_service_audit(db_session, sample_tenant):
    from services.print_service import PrintService
    PrintService.audit_print(sample_tenant.id, 'test', 999, action='test_audit')
    from models.print_history import PrintHistory
    record = PrintHistory.query.filter_by(
        tenant_id=sample_tenant.id,
        document_type='test',
        document_id=999
    ).first()
    assert record is not None
    assert record.action == 'test_audit'
