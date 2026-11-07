"""Synchronize an explicitly selected tenant's existing print settings."""

from extensions import db
from models.invoice_settings import InvoiceSettings
from utils.invoice_profile import sync_invoice_profile
from utils.tenanting import without_tenant_scope


class InvoiceProfileConflict(ValueError):
    """The selected tenant has more than one active print settings row."""


class InvoiceProfileService:
    @staticmethod
    def sync_from_tenant(tenant, fields):
        """Mirror submitted fields; the platform-owner route owns the transaction.

        This operation may target a tenant other than the owner's active tenant.
        Always use an explicit tenant ID and never choose between duplicate rows.
        A missing row is created later by the existing print-settings workflow.
        """
        with without_tenant_scope():
            rows = InvoiceSettings.query.filter_by(tenant_id=int(tenant.id), is_active=True).limit(2).all()
            if len(rows) > 1:
                raise InvoiceProfileConflict("Multiple active invoice settings exist for this tenant")
            if rows:
                sync_invoice_profile(tenant, rows[0], fields)
            # Flush while the explicitly authorized owner operation is scoped
            # to the target tenant, before the caller commits its transaction.
            db.session.flush()
