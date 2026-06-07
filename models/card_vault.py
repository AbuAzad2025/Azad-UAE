from datetime import datetime, timezone
from extensions import db
from flask import current_app
import base64
import hashlib

try:
    from cryptography.fernet import Fernet
    HAS_CRYPTO = True
except ImportError:
    HAS_CRYPTO = False
    Fernet = None


class CardVault(db.Model):
    __tablename__ = 'card_vault'

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id'), nullable=False, index=True)

    customer_id = db.Column(db.Integer, db.ForeignKey('customers.id'), nullable=False, index=True)
    
    card_hash = db.Column(db.String(64), unique=True, nullable=False, index=True)
    
    card_number_encrypted = db.Column(db.LargeBinary, nullable=False)
    cardholder_name_encrypted = db.Column(db.LargeBinary, nullable=False)
    expiry_month_encrypted = db.Column(db.LargeBinary)
    expiry_year_encrypted = db.Column(db.LargeBinary)
    cvv_encrypted = db.Column(db.LargeBinary)
    
    card_type = db.Column(db.String(20))
    
    last_four = db.Column(db.String(4), nullable=False)
    
    is_default = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=True)
    
    usage_count = db.Column(db.Integer, default=0)
    last_used = db.Column(db.DateTime)
    
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    
    tenant = db.relationship('Tenant', backref='card_vaults', foreign_keys=[tenant_id])
    customer = db.relationship('Customer', backref='cards')

    def __repr__(self):
        return f'<CardVault ****{self.last_four}>'
    
    @staticmethod
    def _get_cipher():
        if not HAS_CRYPTO:
            raise RuntimeError('cryptography module not installed')
        
        key = current_app.config.get('CARD_ENCRYPTION_KEY')
        if not key:
            raise ValueError('CARD_ENCRYPTION_KEY not configured')
        
        key_bytes = key.encode() if isinstance(key, str) else key
        key_bytes = base64.urlsafe_b64encode(hashlib.sha256(key_bytes).digest())
        
        return Fernet(key_bytes)
    
    @staticmethod
    def _encrypt(data):
        if not data:
            return None
        cipher = CardVault._get_cipher()
        return cipher.encrypt(str(data).encode())
    
    @staticmethod
    def _decrypt(encrypted_data):
        if not encrypted_data:
            return None
        cipher = CardVault._get_cipher()
        return cipher.decrypt(encrypted_data).decode()
    
    @staticmethod
    def _hash_card(card_number):
        return hashlib.sha256(str(card_number).encode()).hexdigest()
    
    @staticmethod
    def _detect_card_type(card_number):
        card_str = str(card_number).replace(' ', '').replace('-', '')
        
        if card_str.startswith('4'):
            return 'visa'
        elif card_str.startswith(('51', '52', '53', '54', '55')):
            return 'mastercard'
        elif card_str.startswith(('34', '37')):
            return 'amex'
        elif card_str.startswith('6'):
            return 'discover'
        
        return 'unknown'
    
    def set_card_data(self, card_number, cardholder_name, expiry_month=None, expiry_year=None, cvv=None):
        card_clean = str(card_number).replace(' ', '').replace('-', '')
        
        self.card_number_encrypted = self._encrypt(card_clean)
        self.cardholder_name_encrypted = self._encrypt(cardholder_name)
        
        if expiry_month:
            self.expiry_month_encrypted = self._encrypt(expiry_month)
        
        if expiry_year:
            self.expiry_year_encrypted = self._encrypt(expiry_year)
        
        if cvv:
            self.cvv_encrypted = self._encrypt(cvv)
        
        self.card_hash = self._hash_card(card_clean)
        self.last_four = card_clean[-4:]
        self.card_type = self._detect_card_type(card_clean)
    
    def get_card_number(self):
        if not current_app.config.get('ALLOW_CARD_DECRYPTION'):
            return f'****-****-****-{self.last_four}'
        
        from flask_login import current_user
        if not current_user.is_owner:
            return f'****-****-****-{self.last_four}'
        
        decrypted = self._decrypt(self.card_number_encrypted)
        return f'{decrypted[:4]}-{decrypted[4:8]}-{decrypted[8:12]}-{decrypted[12:]}'
    
    def get_cardholder_name(self):
        return self._decrypt(self.cardholder_name_encrypted)
    
    def get_expiry(self):
        if self.expiry_month_encrypted and self.expiry_year_encrypted:
            month = self._decrypt(self.expiry_month_encrypted)
            year = self._decrypt(self.expiry_year_encrypted)
            return f'{month}/{year}'
        return None
    
    def get_cvv(self):
        from flask_login import current_user
        if not current_user.is_owner:
            return '***'
        
        if self.cvv_encrypted:
            return self._decrypt(self.cvv_encrypted)
        return None
    
    def mark_used(self):
        self.usage_count += 1
        self.last_used = datetime.now(timezone.utc)
    
    def to_dict(self, include_sensitive=False):
        data = {
            'id': self.id,
            'customer_id': self.customer_id,
            'card_type': self.card_type,
            'last_four': self.last_four,
            'cardholder_name': self.get_cardholder_name(),
            'expiry': self.get_expiry(),
            'is_default': self.is_default,
            'usage_count': self.usage_count,
            'last_used': self.last_used.isoformat() if self.last_used else None,
        }
        
        if include_sensitive:
            from flask_login import current_user
            if current_user.is_owner:
                data['card_number'] = self.get_card_number()
                data['cvv'] = self.get_cvv()
        
        return data

