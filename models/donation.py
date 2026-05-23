"""
Donation Model
نموذج التبرعات والدعم المالي
"""

from datetime import datetime, timezone
from extensions import db
from decimal import Decimal


class Donation(db.Model):
    """
    سجل التبرعات - يحفظ كل عمليات الدعم المالي
    """
    __tablename__ = 'donations'
    
    id = db.Column(db.Integer, primary_key=True)
    
    # Amount Info - معلومات المبلغ
    amount_usd = db.Column(db.Numeric(15, 2), nullable=False)  # المبلغ بالدولار
    amount_crypto = db.Column(db.Numeric(20, 8))  # المبلغ بالعملة الرقمية
    
    # Payment Method - طريقة الدفع
    payment_method = db.Column(db.String(50), nullable=False)  # crypto, card, paypal, bank
    
    # Crypto Info - معلومات العملة الرقمية
    crypto_type = db.Column(db.String(20))  # btc, eth, usdt, usdc, bnb
    wallet_address = db.Column(db.String(200))  # عنوان المحفظة المستخدم
    transaction_hash = db.Column(db.String(200))  # Transaction ID/Hash
    
    # Status - الحالة
    status = db.Column(db.String(20), default='pending')  # pending, confirmed, completed, failed
    
    # Donor Info - معلومات المتبرع (اختياري)
    donor_name = db.Column(db.String(200))
    donor_email = db.Column(db.String(200))
    donor_message = db.Column(db.Text)  # رسالة من المتبرع
    
    # Purchase Info - معلومات الشراء (للمنتجات)
    transaction_type = db.Column(db.String(20), default='donation')  # donation, purchase
    package = db.Column(db.String(50))  # basic, professional, enterprise
    customer_name = db.Column(db.String(200))  # اسم العميل (للمشتريات)
    customer_email = db.Column(db.String(200))  # إيميل العميل (للمشتريات)
    customer_phone = db.Column(db.String(50))  # رقم الجوال
    
    # Conversion Info - معلومات التحويل
    converted_to_crypto = db.Column(db.Boolean, default=False)
    conversion_rate = db.Column(db.Numeric(15, 6))  # سعر التحويل
    final_wallet_address = db.Column(db.String(200))  # المحفظة النهائية المستلمة
    
    # Payment Gateway Info - معلومات بوابة الدفع
    gateway_name = db.Column(db.String(50))  # coingate, nowpayments, btcpay, stripe
    gateway_transaction_id = db.Column(db.String(200))
    gateway_status = db.Column(db.String(50))
    
    # Security & Tracking - الأمان والتتبع
    ip_address = db.Column(db.String(50))
    user_agent = db.Column(db.String(500))
    country_code = db.Column(db.String(10))
    
    # Notifications - الإشعارات
    thank_you_sent = db.Column(db.Boolean, default=False)
    notification_sent = db.Column(db.Boolean, default=False)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True)
    confirmed_at = db.Column(db.DateTime)  # وقت التأكيد
    completed_at = db.Column(db.DateTime)  # وقت الاكتمال
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), 
                          onupdate=lambda: datetime.now(timezone.utc))
    
    # Notes - ملاحظات
    notes = db.Column(db.Text)
    admin_notes = db.Column(db.Text)  # ملاحظات إدارية
    
    def __repr__(self):
        return f'<Donation ${self.amount_usd} via {self.payment_method} - {self.status}>'
    
    @property
    def is_completed(self):
        """تحقق إذا كانت العملية مكتملة"""
        return self.status == 'completed'
    
    @property
    def is_pending(self):
        """تحقق إذا كانت العملية معلقة"""
        return self.status == 'pending'
    
    def to_dict(self):
        """تحويل إلى dictionary"""
        return {
            'id': self.id,
            'amount_usd': float(self.amount_usd) if self.amount_usd else 0,
            'amount_crypto': float(self.amount_crypto) if self.amount_crypto else None,
            'payment_method': self.payment_method,
            'crypto_type': self.crypto_type,
            'status': self.status,
            'donor_name': self.donor_name,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'confirmed_at': self.confirmed_at.isoformat() if self.confirmed_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
        }
    
    @staticmethod
    def get_total_donations():
        """إجمالي التبرعات المكتملة"""
        result = db.session.query(
            db.func.sum(Donation.amount_usd)
        ).filter_by(status='completed').scalar()
        return float(result) if result else 0
    
    @staticmethod
    def get_donations_count():
        """عدد التبرعات المكتملة"""
        return Donation.query.filter_by(status='completed').count()
    
    @staticmethod
    def get_pending_count():
        """عدد التبرعات المعلقة"""
        return Donation.query.filter_by(status='pending').count()
    
    @staticmethod
    def get_recent_donations(limit=10):
        """أحدث التبرعات"""
        return Donation.query.filter_by(
            status='completed'
        ).order_by(
            Donation.completed_at.desc()
        ).limit(limit).all()
    
    @staticmethod
    def get_donations_by_method():
        """التبرعات حسب طريقة الدفع"""
        result = db.session.query(
            Donation.payment_method,
            db.func.count(Donation.id).label('count'),
            db.func.sum(Donation.amount_usd).label('total')
        ).filter_by(
            status='completed'
        ).group_by(
            Donation.payment_method
        ).all()
        
        return [
            {
                'method': row.payment_method,
                'count': row.count,
                'total': float(row.total) if row.total else 0
            }
            for row in result
        ]

