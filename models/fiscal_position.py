"""
المواقف الضريبية - Fiscal Positions
Inspired by Odoo's account.fiscal.position
Maps taxes and accounts based on customer type/location.
"""

from datetime import datetime, timezone
from extensions import db


class FiscalPosition(db.Model):
    """
    Defines a fiscal position that changes how taxes and income accounts
    are applied for a customer (e.g. local VAT 5%, export VAT 0%, GCC).
    """
    __tablename__ = 'fiscal_positions'
    __table_args__ = (
        db.UniqueConstraint('tenant_id', 'code', name='uq_fiscal_pos_tenant_code'),
    )

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False, index=True)

    code = db.Column(db.String(50), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    name_ar = db.Column(db.String(100))

    # Matching criteria (auto-assign to customers)
    country_code = db.Column(db.String(2))  # e.g. 'AE', 'SA', 'US'
    vat_required = db.Column(db.Boolean, default=False)  # customer must have VAT number
    auto_apply = db.Column(db.Boolean, default=False)  # auto-assign to matching customers

    is_active = db.Column(db.Boolean, nullable=False, default=True)
    notes = db.Column(db.Text)

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc),
                            onupdate=lambda: datetime.now(timezone.utc))

    tenant = db.relationship('Tenant', backref='fiscal_positions', foreign_keys=[tenant_id])
    tax_rules = db.relationship('FiscalPositionTaxRule', back_populates='fiscal_position',
                                cascade='all, delete-orphan')

    def __repr__(self):
        return f'<FiscalPosition {self.code}>'

    def map_tax(self, source_tax_id):
        """Map a source tax to the destination tax for this fiscal position."""
        rule = FiscalPositionTaxRule.query.filter_by(
            fiscal_position_id=self.id,
            source_tax_id=source_tax_id
        ).first()
        return rule.destination_tax_id if rule else source_tax_id

    def map_account(self, source_account_id):
        """Map a source income/expense account to destination account."""
        rule = FiscalPositionTaxRule.query.filter_by(
            fiscal_position_id=self.id,
            source_account_id=source_account_id
        ).first()
        return rule.destination_account_id if rule else source_account_id


class FiscalPositionTaxRule(db.Model):
    """
    Individual mapping rule: source tax/account -> destination tax/account.
    """
    __tablename__ = 'fiscal_position_tax_rules'

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False, index=True)
    fiscal_position_id = db.Column(db.Integer, db.ForeignKey('fiscal_positions.id'), nullable=False, index=True)

    # Source (what the product has by default)
    source_tax_id = db.Column(db.Integer, db.ForeignKey('tax_calculation_rules.id'))
    source_account_id = db.Column(db.Integer, db.ForeignKey('gl_accounts.id'))

    # Destination (what to use under this fiscal position)
    destination_tax_id = db.Column(db.Integer, db.ForeignKey('tax_calculation_rules.id'))
    destination_account_id = db.Column(db.Integer, db.ForeignKey('gl_accounts.id'))

    # Rule type
    rule_type = db.Column(db.String(20), nullable=False, default='tax')  # 'tax' or 'account'

    tenant = db.relationship('Tenant', backref='fiscal_position_tax_rules', foreign_keys=[tenant_id])
    fiscal_position = db.relationship('FiscalPosition', back_populates='tax_rules')
    source_tax = db.relationship('TaxCalculationRule', foreign_keys=[source_tax_id])
    destination_tax = db.relationship('TaxCalculationRule', foreign_keys=[destination_tax_id])
    source_account = db.relationship('GLAccount', foreign_keys=[source_account_id])
    destination_account = db.relationship('GLAccount', foreign_keys=[destination_account_id])

    def __repr__(self):
        return f'<FiscalPositionTaxRule {self.rule_type}>'
