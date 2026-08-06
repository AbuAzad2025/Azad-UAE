from datetime import datetime, timezone
from typing import Any

from extensions import db
import hashlib

Fernet: Any
try:
    from cryptography.fernet import Fernet as _Fernet

    Fernet = _Fernet
    HAS_CRYPTO = True
except ImportError:
    Fernet = Any
    HAS_CRYPTO = False
    Fernet = None


class CardVault(db.Model):
    __tablename__ = "card_vault"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(
        db.Integer,
        db.ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    customer_id = db.Column(db.Integer, db.ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False, index=True)

    card_hash = db.Column(db.String(64), unique=True, nullable=False, index=True)

    card_number_encrypted = db.Column(db.LargeBinary, nullable=False)
    cardholder_name_encrypted = db.Column(db.LargeBinary, nullable=False)
    expiry_month_encrypted = db.Column(db.LargeBinary)
    expiry_year_encrypted = db.Column(db.LargeBinary)
    cvv_encrypted = db.Column(db.LargeBinary)

    card_type = db.Column(db.String(20))

    last_four = db.Column(db.String(4), nullable=False)

    is_default = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=True, index=True)

    usage_count = db.Column(db.Integer, default=0)
    last_used = db.Column(db.DateTime)

    created_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )
    created_by = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="RESTRICT"), nullable=True, index=True)

    tenant = db.relationship("Tenant", backref="card_vaults", foreign_keys=[tenant_id])
    customer = db.relationship("Customer", backref="cards")

    def __repr__(self):
        return f"<CardVault ****{self.last_four}>"

    @staticmethod
    def _hash_card(card_number: str) -> str:
        return hashlib.sha256(str(card_number).encode()).hexdigest()

    @staticmethod
    def _detect_card_type(card_number: str) -> str:
        card_str = str(card_number).replace(" ", "").replace("-", "")
        if card_str.startswith("4"):
            return "visa"
        if card_str.startswith(("51", "52", "53", "54", "55")):
            return "mastercard"
        if card_str.startswith(("34", "37")):
            return "amex"
        if card_str.startswith("6"):
            return "discover"
        return "unknown"

    def set_card_data(
        self,
        card_number: str,
        cardholder_name: str,
        expiry_month: str | None = None,
        expiry_year: str | None = None,
        cvv: str | None = None,
        cipher: Any = None,
    ):
        """Encrypt and store card data. Requires a cipher from CardEncryptionService."""
        if cipher is None:
            raise ValueError("cipher is required to encrypt card data")
        card_clean = str(card_number).replace(" ", "").replace("-", "")

        self.card_number_encrypted = cipher.encrypt(card_clean)
        self.cardholder_name_encrypted = cipher.encrypt(cardholder_name)

        if expiry_month:
            self.expiry_month_encrypted = cipher.encrypt(expiry_month)
        if expiry_year:
            self.expiry_year_encrypted = cipher.encrypt(expiry_year)
        if cvv:
            self.cvv_encrypted = cipher.encrypt(cvv)

        self.card_hash = self._hash_card(card_clean)
        self.last_four = card_clean[-4:]
        self.card_type = self._detect_card_type(card_clean)

    def get_card_number(self, cipher: Any = None) -> str:
        """Return formatted card number if cipher provided, else masked."""
        if cipher is None:
            return f"****-****-****-{self.last_four}"
        decrypted = cipher.decrypt(self.card_number_encrypted)
        return f"{decrypted[:4]}-{decrypted[4:8]}-{decrypted[8:12]}-{decrypted[12:]}"

    def get_cardholder_name(self, cipher: Any = None) -> str | None:
        """Return decrypted cardholder name if cipher provided."""
        if cipher is None:
            return None
        return cipher.decrypt(self.cardholder_name_encrypted)

    def get_expiry(self, cipher: Any = None) -> str | None:
        """Return expiry month/year if cipher provided."""
        if cipher is None or not (self.expiry_month_encrypted and self.expiry_year_encrypted):
            return None
        month = cipher.decrypt(self.expiry_month_encrypted)
        year = cipher.decrypt(self.expiry_year_encrypted)
        return f"{month}/{year}"

    def get_cvv(self, cipher: Any = None) -> str | None:
        """Return CVV if cipher provided, else masked."""
        if cipher is None or not self.cvv_encrypted:
            return None
        return cipher.decrypt(self.cvv_encrypted)

    def mark_used(self):
        self.usage_count += 1
        self.last_used = datetime.now(timezone.utc)

    def to_dict(self, cipher: Any = None) -> dict[str, Any]:
        """Serialize. Only includes decrypted data when cipher is provided."""
        data = {
            "id": self.id,
            "customer_id": self.customer_id,
            "card_type": self.card_type,
            "last_four": self.last_four,
            "is_default": self.is_default,
            "usage_count": self.usage_count,
            "last_used": self.last_used.isoformat() if self.last_used else None,
        }
        if cipher is not None:
            data["cardholder_name"] = self.get_cardholder_name(cipher)
            data["expiry"] = self.get_expiry(cipher)
            data["card_number"] = self.get_card_number(cipher)
            data["cvv"] = self.get_cvv(cipher)
        return data
