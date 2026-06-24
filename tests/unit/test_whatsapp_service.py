"""Unit tests for WhatsAppService."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest
import requests

from services.whatsapp_service import WhatsAppService


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch):
    for key in ('WHATSAPP_API_KEY', 'WHATSAPP_API_URL', 'WHATSAPP_INSTANCE_ID'):
        monkeypatch.delenv(key, raising=False)
    yield


@pytest.fixture
def whatsapp_env(monkeypatch):
    monkeypatch.setenv('WHATSAPP_API_KEY', 'test-token')
    monkeypatch.setenv('WHATSAPP_INSTANCE_ID', 'inst-1')
    monkeypatch.setenv('WHATSAPP_API_URL', 'https://wa.test')


class TestIsEnabled:
    def test_disabled_without_key(self):
        assert WhatsAppService.is_enabled() is False

    def test_enabled_with_key(self, monkeypatch):
        monkeypatch.setenv('WHATSAPP_API_KEY', 'x')
        assert WhatsAppService.is_enabled() is True


class TestSendInvoice:
    def test_not_configured(self):
        assert WhatsAppService.send_invoice('0501234567', 'INV-1') == {
            'success': False,
            'error': 'WhatsApp not configured',
        }

    def test_missing_instance(self, monkeypatch):
        monkeypatch.setenv('WHATSAPP_API_KEY', 'only-key')
        result = WhatsAppService.send_invoice('0501234567', 'INV-1')
        assert result['success'] is False
        assert result['error'] == 'Missing configuration'

    def test_chat_message_success(self, whatsapp_env, mocker):
        resp = MagicMock()
        resp.json.return_value = {'id': 'msg-1'}
        mocker.patch('services.whatsapp_service.requests.post', return_value=resp)

        result = WhatsAppService.send_invoice('050-123-4567', 'INV-99')
        assert result['success'] is True
        assert result['message_id'] == 'msg-1'
        assert result['phone'] == '971501234567'

    def test_document_message_success(self, whatsapp_env, mocker):
        captured = {}
        resp = MagicMock()
        resp.json.return_value = {'id': 'doc-1'}

        def fake_post(url, data=None, timeout=None):
            captured['url'] = url
            captured['data'] = data
            return resp

        mocker.patch('services.whatsapp_service.requests.post', side_effect=fake_post)
        result = WhatsAppService.send_invoice('971501234567', 'INV-2', pdf_url='https://pdf.example/a.pdf')
        assert result['success'] is True
        assert captured['url'].endswith('/messages/document')
        assert captured['data']['document'] == 'https://pdf.example/a.pdf'

    def test_request_failure(self, whatsapp_env, mocker):
        mocker.patch(
            'services.whatsapp_service.requests.post',
            side_effect=requests.exceptions.Timeout('timeout'),
        )
        result = WhatsAppService.send_invoice('0501234567', 'INV-3')
        assert result['success'] is False
        assert 'timeout' in result['error']


class TestSendPaymentReminder:
    def test_not_configured(self):
        result = WhatsAppService.send_payment_reminder('0501234567', 'Ali', 100.5)
        assert result['success'] is False

    def test_success(self, whatsapp_env, mocker):
        resp = MagicMock()
        resp.json.return_value = {'id': 'rem-1'}
        mocker.patch('services.whatsapp_service.requests.post', return_value=resp)

        result = WhatsAppService.send_payment_reminder('+971 50 111 2222', 'Sara', 250)
        assert result['success'] is True
        assert result['phone'] == '971501112222'

    def test_failure(self, whatsapp_env, mocker):
        mocker.patch('services.whatsapp_service.requests.post', side_effect=RuntimeError('net'))
        result = WhatsAppService.send_payment_reminder('0501234567', 'Ali', 10)
        assert result['success'] is False


class TestSendCustomMessage:
    def test_not_configured(self):
        assert WhatsAppService.send_custom_message('050', 'hi')['success'] is False

    def test_success(self, whatsapp_env, mocker):
        resp = MagicMock()
        resp.json.return_value = {'id': 'c-1'}
        post = mocker.patch('services.whatsapp_service.requests.post', return_value=resp)

        result = WhatsAppService.send_custom_message('0501234567', 'Hello')
        assert result['success'] is True
        assert post.call_args.kwargs['data']['body'] == 'Hello'

    def test_failure(self, whatsapp_env, mocker):
        mocker.patch('services.whatsapp_service.requests.post', side_effect=ValueError('bad'))
        assert WhatsAppService.send_custom_message('0501234567', 'x')['success'] is False
