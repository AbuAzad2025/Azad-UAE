"""WhatsApp messaging via UltraMsg API."""
from __future__ import annotations

import os
from typing import Dict

import requests


class WhatsAppService:
    @staticmethod
    def is_enabled() -> bool:
        return bool(os.environ.get('WHATSAPP_API_KEY'))

    @staticmethod
    def _normalize_phone(phone: str) -> str:
        phone_clean = phone.replace('+', '').replace(' ', '').replace('-', '')
        if not phone_clean.startswith('971'):
            phone_clean = '971' + phone_clean.lstrip('0')
        return phone_clean

    @staticmethod
    def _api_config() -> tuple[str | None, str, str | None]:
        return (
            os.environ.get('WHATSAPP_API_KEY'),
            os.environ.get('WHATSAPP_API_URL', 'https://api.ultramsg.com'),
            os.environ.get('WHATSAPP_INSTANCE_ID'),
        )

    @staticmethod
    def send_invoice(phone: str, invoice_number: str, pdf_url: str = None) -> Dict:
        if not WhatsAppService.is_enabled():
            return {'success': False, 'error': 'WhatsApp not configured'}

        api_key, api_url, instance_id = WhatsAppService._api_config()
        if not all([api_key, instance_id]):
            return {'success': False, 'error': 'Missing configuration'}

        phone_clean = WhatsAppService._normalize_phone(phone)
        message = (
            f'السلام عليكم ورحمة الله وبركاته\n\n'
            f'فاتورتك رقم {invoice_number} جاهزة!\n\n'
            f'يمكنك مراجعتها والدفع.\n\n'
            f'شكراً لتعاملكم معنا'
        )

        try:
            if pdf_url:
                endpoint = f'{api_url}/{instance_id}/messages/document'
                payload = {
                    'token': api_key,
                    'to': phone_clean,
                    'document': pdf_url,
                    'caption': message,
                }
            else:
                endpoint = f'{api_url}/{instance_id}/messages/chat'
                payload = {
                    'token': api_key,
                    'to': phone_clean,
                    'body': message,
                }

            response = requests.post(endpoint, data=payload, timeout=10)
            result = response.json()
            return {
                'success': True,
                'message_id': result.get('id'),
                'phone': phone_clean,
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}

    @staticmethod
    def send_payment_reminder(phone: str, customer_name: str, amount_due: float) -> Dict:
        if not WhatsAppService.is_enabled():
            return {'success': False, 'error': 'WhatsApp not configured'}

        api_key, api_url, instance_id = WhatsAppService._api_config()
        phone_clean = WhatsAppService._normalize_phone(phone)
        message = (
            f'السلام عليكم {customer_name}\n\n'
            f'تذكير ودي بالرصيد المستحق: {amount_due:,.2f} درهم\n\n'
            f'نرجو منكم التكرم بالسداد في أقرب وقت ممكن.\n\n'
            f'شكراً لكم'
        )

        try:
            endpoint = f'{api_url}/{instance_id}/messages/chat'
            response = requests.post(endpoint, data={
                'token': api_key,
                'to': phone_clean,
                'body': message,
            }, timeout=10)
            result = response.json()
            return {
                'success': True,
                'message_id': result.get('id'),
                'phone': phone_clean,
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}

    @staticmethod
    def send_custom_message(phone: str, message: str) -> Dict:
        if not WhatsAppService.is_enabled():
            return {'success': False, 'error': 'WhatsApp not configured'}

        api_key, api_url, instance_id = WhatsAppService._api_config()
        phone_clean = WhatsAppService._normalize_phone(phone)

        try:
            endpoint = f'{api_url}/{instance_id}/messages/chat'
            response = requests.post(endpoint, data={
                'token': api_key,
                'to': phone_clean,
                'body': message,
            }, timeout=10)
            result = response.json()
            return {
                'success': True,
                'message_id': result.get('id'),
                'phone': phone_clean,
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}
