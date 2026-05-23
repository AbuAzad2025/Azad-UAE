import os
import requests
from typing import Optional, Dict


class WhatsAppService:
    
    @staticmethod
    def is_enabled() -> bool:
        return bool(os.environ.get('WHATSAPP_API_KEY'))
    
    @staticmethod
    def send_invoice(phone: str, invoice_number: str, pdf_url: str = None) -> Dict:
        if not WhatsAppService.is_enabled():
            return {'success': False, 'error': 'WhatsApp not configured'}
        
        api_key = os.environ.get('WHATSAPP_API_KEY')
        api_url = os.environ.get('WHATSAPP_API_URL', 'https://api.ultramsg.com')
        instance_id = os.environ.get('WHATSAPP_INSTANCE_ID')
        
        if not all([api_key, instance_id]):
            return {'success': False, 'error': 'Missing configuration'}
        
        phone_clean = phone.replace('+', '').replace(' ', '').replace('-', '')
        if not phone_clean.startswith('971'):
            phone_clean = '971' + phone_clean.lstrip('0')
        
        message = f"""
السلام عليكم ورحمة الله وبركاته

فاتورتك رقم {invoice_number} جاهزة!

يمكنك مراجعتها والدفع.

شكراً لتعاملكم معنا
        """.strip()
        
        try:
            if pdf_url:
                endpoint = f'{api_url}/{instance_id}/messages/document'
                payload = {
                    'token': api_key,
                    'to': phone_clean,
                    'document': pdf_url,
                    'caption': message
                }
            else:
                endpoint = f'{api_url}/{instance_id}/messages/chat'
                payload = {
                    'token': api_key,
                    'to': phone_clean,
                    'body': message
                }
            
            response = requests.post(endpoint, data=payload, timeout=10)
            result = response.json()
            
            return {
                'success': True,
                'message_id': result.get('id'),
                'phone': phone_clean
            }
        
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }
    
    @staticmethod
    def send_payment_reminder(phone: str, customer_name: str, amount_due: float) -> Dict:
        if not WhatsAppService.is_enabled():
            return {'success': False, 'error': 'WhatsApp not configured'}
        
        api_key = os.environ.get('WHATSAPP_API_KEY')
        api_url = os.environ.get('WHATSAPP_API_URL', 'https://api.ultramsg.com')
        instance_id = os.environ.get('WHATSAPP_INSTANCE_ID')
        
        phone_clean = phone.replace('+', '').replace(' ', '').replace('-', '')
        if not phone_clean.startswith('971'):
            phone_clean = '971' + phone_clean.lstrip('0')
        
        message = f"""
السلام عليكم {customer_name}

تذكير ودي بالرصيد المستحق: {amount_due:,.2f} درهم

نرجو منكم التكرم بالسداد في أقرب وقت ممكن.

شكراً لكم
        """.strip()
        
        try:
            endpoint = f'{api_url}/{instance_id}/messages/chat'
            response = requests.post(endpoint, data={
                'token': api_key,
                'to': phone_clean,
                'body': message
            }, timeout=10)
            
            result = response.json()
            
            return {
                'success': True,
                'message_id': result.get('id'),
                'phone': phone_clean
            }
        
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }
    
    @staticmethod
    def send_custom_message(phone: str, message: str) -> Dict:
        if not WhatsAppService.is_enabled():
            return {'success': False, 'error': 'WhatsApp not configured'}
        
        api_key = os.environ.get('WHATSAPP_API_KEY')
        api_url = os.environ.get('WHATSAPP_API_URL', 'https://api.ultramsg.com')
        instance_id = os.environ.get('WHATSAPP_INSTANCE_ID')
        
        phone_clean = phone.replace('+', '').replace(' ', '').replace('-', '')
        if not phone_clean.startswith('971'):
            phone_clean = '971' + phone_clean.lstrip('0')
        
        try:
            endpoint = f'{api_url}/{instance_id}/messages/chat'
            response = requests.post(endpoint, data={
                'token': api_key,
                'to': phone_clean,
                'body': message
            }, timeout=10)
            
            result = response.json()
            
            return {
                'success': True,
                'message_id': result.get('id'),
                'phone': phone_clean
            }
        
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }

