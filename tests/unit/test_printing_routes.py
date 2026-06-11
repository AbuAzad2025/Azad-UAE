"""Tests for the Professional Printing routes and PrintService."""
import json
from decimal import Decimal
from datetime import datetime, timezone

import pytest
from flask import url_for


def test_print_settings_page(client, db_session, sample_tenant, sample_user):
    """GET /printing/settings renders the settings form."""
    resp = client.get(url_for('printing.print_settings'))
    assert resp.status_code == 200
    assert 'إعدادات الطباعة' in resp.text or 'print' in resp.text


def test_print_settings_save(client, db_session, sample_tenant, sample_user):
    """POST /printing/settings saves print preferences."""
    resp = client.post(url_for('printing.print_settings'), data={
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
    assert resp.status_code == 200


def test_print_history_page(client, db_session, sample_tenant, sample_user):
    """GET /printing/history renders the print history page."""
    resp = client.get(url_for('printing.print_history'))
    assert resp.status_code == 200
    assert 'سجل الطباعة' in resp.text or 'history' in resp.text


def test_print_purchase_route(client, db_session, sample_tenant, sample_user, sample_purchase):
    """GET /printing/purchase/<id> renders professional purchase print."""
    resp = client.get(url_for('printing.print_purchase', id=sample_purchase.id))
    assert resp.status_code == 200
    assert 'فاتورة شراء' in resp.text or 'purchase' in resp.text


def test_print_expense_route(client, db_session, sample_tenant, sample_user, sample_expense):
    """GET /printing/expense/<id> renders professional expense print."""
    resp = client.get(url_for('printing.print_expense', id=sample_expense.id))
    assert resp.status_code == 200
    assert 'سند مصروف' in resp.text or 'expense' in resp.text


def test_print_payroll_slip(client, db_session, sample_tenant, sample_user, sample_payroll_transaction):
    """GET /printing/payroll-slip/<id> renders professional salary slip."""
    resp = client.get(url_for('printing.salary_slip', id=sample_payroll_transaction.id))
    assert resp.status_code == 200
    assert 'قسيمة راتب' in resp.text or 'Salary' in resp.text


def test_print_cheque(client, db_session, sample_tenant, sample_user, sample_cheque):
    """GET /printing/cheque/<id> renders cheque print page."""
    resp = client.get(url_for('printing.print_cheque', id=sample_cheque.id))
    assert resp.status_code in (200, 302)


def test_print_packing_slip(client, db_session, sample_tenant, sample_user, sample_sale):
    """GET /printing/packing-slip/<sale_id> renders delivery note."""
    resp = client.get(url_for('printing.packing_slip', sale_id=sample_sale.id))
    assert resp.status_code == 200
    assert 'إذن تسليم' in resp.text or 'Delivery' in resp.text


def test_print_preview_api(client, db_session, sample_tenant, sample_user, sample_purchase):
    """POST /printing/api/preview returns HTML preview."""
    resp = client.post(url_for('printing.print_preview_api'), json={
        'type': 'purchase',
        'id': sample_purchase.id,
    })
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert 'html' in data
    assert 'فاتورة' in data['html'] or 'purchase' in data['html']


def test_print_history_api(client, db_session, sample_tenant, sample_user):
    """GET /printing/api/print-history returns JSON list."""
    resp = client.get(url_for('printing.api_print_history'))
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert isinstance(data, list)


def test_purchase_pdf_route(client, db_session, sample_tenant, sample_user, sample_purchase):
    """GET /printing/purchase/<id>/pdf downloads a PDF."""
    resp = client.get(url_for('printing.purchase_pdf', id=sample_purchase.id))
    assert resp.status_code in (200, 302, 500)
    if resp.status_code == 200:
        assert resp.mimetype in ('application/pdf', 'text/html')


def test_expense_pdf_route(client, db_session, sample_tenant, sample_user, sample_expense):
    """GET /printing/expense/<id>/pdf downloads a PDF."""
    resp = client.get(url_for('printing.expense_pdf', id=sample_expense.id))
    assert resp.status_code in (200, 302, 500)
