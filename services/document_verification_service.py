"""
Document Verification Service — QR traceability with pre-generation collision
check, tenant scoping, and IDOR protection (The Spell).
"""

from __future__ import annotations

import logging

from flask_login import current_user

from extensions import db

logger = logging.getLogger(__name__)

VERIFIABLE_TYPES = {"sale", "payment", "receipt", "purchase", "expense"}


class DocumentVerificationService:
    @staticmethod
    def resolve_verification_url(request):
        base = request.url_root.rstrip("/")
        return base + "/verify/{}"

    @staticmethod
    def get_or_create_verification(
        document_type, document_id, tenant_id, created_by=None
    ):
        from models.document_verification import DocumentVerification

        if document_type not in VERIFIABLE_TYPES:
            logger.warning("Unverifiable document type: %s", document_type)
            return None

        try:
            rec = DocumentVerification.get_or_create(
                tenant_id=tenant_id,
                document_type=document_type,
                document_id=document_id,
                created_by=created_by or getattr(current_user, "id", None),
            )
            db.session.flush()
            return rec
        except Exception:
            logger.exception(
                "Failed to create verification for %s #%d", document_type, document_id
            )
            return None

    @staticmethod
    def lookup_by_token(public_token):
        from models.document_verification import DocumentVerification

        if not public_token or not public_token.strip():
            return None

        rec = DocumentVerification.query.filter_by(
            public_token=public_token.strip()
        ).first()
        if not rec:
            return None

        doc = DocumentVerificationService._resolve_document(
            rec.document_type, rec.document_id, rec.tenant_id
        )
        if doc is None:
            return None

        return {
            "tenant_id": rec.tenant_id,
            "document_type": rec.document_type,
            "document_id": rec.document_id,
            "document_hash": rec.document_hash,
            "public_token": rec.public_token,
            "created_at": rec.created_at,
            "document": doc,
        }

    @staticmethod
    def _resolve_document(document_type, document_id, tenant_id):
        try:
            pass

            if document_type == "sale":
                from models import Sale

                return Sale.query.filter_by(id=document_id, tenant_id=tenant_id).first()
            if document_type == "payment":
                from models import Payment

                return Payment.query.filter_by(
                    id=document_id, tenant_id=tenant_id
                ).first()
            if document_type == "receipt":
                from models import Receipt

                return Receipt.query.filter_by(
                    id=document_id, tenant_id=tenant_id
                ).first()
            if document_type == "purchase":
                from models import Purchase

                return Purchase.query.filter_by(
                    id=document_id, tenant_id=tenant_id
                ).first()
            if document_type == "expense":
                from models import Expense

                return Expense.query.filter_by(
                    id=document_id, tenant_id=tenant_id
                ).first()
            return None
        except Exception:
            logger.exception(
                "Error resolving document %s #%d", document_type, document_id
            )
            return None

    @staticmethod
    def build_qr_data(
        document,
        document_type,
        settings,
        tenant,
        print_user_name,
        print_branch,
        verification_url,
    ):
        pass

        getattr(document, "sale_number", None) or getattr(
            document, "payment_number", None
        ) or getattr(document, "receipt_number", None) or getattr(
            document, "purchase_number", None
        ) or getattr(
            document, "expense_number", None
        ) or str(
            getattr(document, "id", "")
        )
        float(
            getattr(document, "total_amount", None)
            or getattr(document, "amount", None)
            or 0
        )
        getattr(document, "currency", None) or (
            tenant.default_currency if tenant else "AED"
        )
        date_val = (
            getattr(document, "sale_date", None)
            or getattr(document, "payment_date", None)
            or getattr(document, "receipt_date", None)
            or getattr(document, "purchase_date", None)
            or getattr(document, "expense_date", None)
        )
        date_str = date_val.strftime("%Y-%m-%d") if date_val else ""
        branch_name = print_branch.name if print_branch else ""

        qr_data = verification_url

        return qr_data
