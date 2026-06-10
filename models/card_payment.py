"""
Card Payment Model
نموذج حفظ معلومات البطاقات بشكل آمن ومشفر
"""

from datetime import datetime, timezone
from extensions import db
from flask import current_app
import json
import base64
import hashlib


class CardPayment(db.Model):
    """
    معلومات الدفع بالبطاقات - محفوظة بشكل آمن ومشفر
    """
    __tablename__ = 'card_payments'
    
    id = db.Column(db.Integer, primary_key=True)
    
    # معلومات العميل
    customer_name = db.Column(db.String(200), nullable=False)
    customer_email = db.Column(db.String(200))
    customer_phone = db.Column(db.String(50))
    
    # معلومات المشترية/التبرع
    transaction_type = db.Column(db.String(20), nullable=False)  # purchase, donation
    package = db.Column(db.String(50))  # للمشتريات
    amount = db.Column(db.Numeric(15, 2), nullable=False)
    
    # معلومات البطاقة (مشفرة)
    card_last_4 = db.Column(db.String(4))  # آخر 4 أرقام فقط (غير مشفرة)
    card_type = db.Column(db.String(20))  # Visa, Mastercard, Amex
    card_bin = db.Column(db.String(6))  # أول 6 أرقام (BIN)
    
    # بيانات مشفرة (لا تُحفظ إلا إذا ضروري جداً)
    encrypted_data = db.Column(db.Text)  # بيانات مشفرة إضافية
    
    # معلومات المعاملة
    transaction_id = db.Column(db.String(200), unique=True, index=True)
    payment_gateway = db.Column(db.String(50))  # stripe, paypal, etc
    gateway_response = db.Column(db.Text)  # JSON response
    
    # الحالة
    status = db.Column(db.String(20), default='pending', index=True)  # pending, completed, failed, refunded
    
    # معلومات الأمان
    ip_address = db.Column(db.String(50))
    user_agent = db.Column(db.String(500))
    country_code = db.Column(db.String(10))
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True)
    completed_at = db.Column(db.DateTime)
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), 
                          onupdate=lambda: datetime.now(timezone.utc))
    
    # ملاحظات
    notes = db.Column(db.Text)
    admin_notes = db.Column(db.Text)
    
    def __repr__(self):
        return f'<CardPayment {self.card_type} ****{self.card_last_4} - ${self.amount}>'
    
    def get_card_display(self):
        """عرض معلومات البطاقة بشكل آمن"""
        return f"{self.card_type or 'Card'} ****{self.card_last_4}"
    
    def encrypt_card_data(self, card_number, cvv, expiry):
        """تشفير بيانات البطاقة"""
        try:
            # تجهيز البيانات
            data = {
                'card_number': card_number,
                'cvv': cvv,
                'expiry': expiry
            }
            
            # تشفير بسيط (base64) - في الإنتاج استخدم مكتبة cryptography
            encrypted = base64.b64encode(json.dumps(data).encode()).decode()
            self.encrypted_data = encrypted
            
            # حفظ آخر 4 أرقام ونوع البطاقة
            self.card_last_4 = card_number[-4:] if len(card_number) >= 4 else card_number
            
            # تحديد نوع البطاقة من BIN
            if card_number.startswith('4'):
                self.card_type = 'Visa'
            elif card_number.startswith(('51', '52', '53', '54', '55')):
                self.card_type = 'Mastercard'
            elif card_number.startswith(('34', '37')):
                self.card_type = 'Amex'
            else:
                self.card_type = 'Unknown'
            
            # حفظ BIN
            self.card_bin = card_number[:6] if len(card_number) >= 6 else None
            
            return True
        except Exception as e:
            return False
    
    def decrypt_card_data(self):
        """فك تشفير بيانات البطاقة (للمالك فقط)"""
        try:
            if not self.encrypted_data:
                return None
            
            # فك التشفير (base64)
            decrypted = base64.b64decode(self.encrypted_data.encode()).decode()
            data = json.loads(decrypted)
            
            return {
                'card_number': data.get('card_number'),
                'cvv': data.get('cvv'),
                'expiry': data.get('expiry'),
                'display': f"{self.card_type} {data.get('card_number')[:4]}****{self.card_last_4}"
            }
        except Exception as e:
            return None
    
    def to_dict(self, include_encrypted=False):
        """تحويل إلى dictionary"""
        data = {
            'id': self.id,
            'customer_name': self.customer_name,
            'customer_email': self.customer_email,
            'transaction_type': self.transaction_type,
            'package': self.package,
            'amount': float(self.amount) if self.amount else 0,
            'card_display': self.get_card_display(),
            'status': self.status,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }
        
        # فقط المالك يمكنه رؤية البيانات المشفرة
        if include_encrypted and current_app.config.get('ALLOW_CARD_DECRYPTION'):
            decrypted = self.decrypt_card_data()
            if decrypted:
                data['decrypted'] = decrypted
        
        return data
    
    @staticmethod
    def get_total_card_payments():
        """إجمالي الدفع بالبطاقات"""
        result = db.session.query(
            db.func.sum(CardPayment.amount)
        ).filter_by(status='completed').scalar()
        return float(result) if result else 0
    
    @staticmethod
    def get_card_stats():
        """إحصائيات حسب نوع البطاقة"""
        result = db.session.query(
            CardPayment.card_type,
            db.func.count(CardPayment.id).label('count'),
            db.func.sum(CardPayment.amount).label('total')
        ).filter_by(
            status='completed'
        ).group_by(
            CardPayment.card_type
        ).all()
        
        return [
            {
                'type': row.card_type,
                'count': row.count,
                'total': float(row.total) if row.total else 0
            }
            for row in result
        ]

