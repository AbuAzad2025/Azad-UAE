"""Unit tests for services/document_verification_service.py — QR traceability service.

Covers type gating, idempotent get-or-create, token lookup with document
resolution, and the QR payload builder. DB-backed via standard fixtures.
"""

from __future__ import annotations

from types import SimpleNamespace

from services.document_verification_service import (
    VERIFIABLE_TYPES,
    DocumentVerificationService,
)


class TestVerifiableTypes:
    def test_expected_types(self):
        assert VERIFIABLE_TYPES == {"sale", "payment", "receipt", "purchase", "expense"}


class TestResolveVerificationUrl:
    def test_builds_verify_url_from_request_root(self):
        fake_request = SimpleNamespace(url_root="http://localhost:5000/")
        url = DocumentVerificationService.resolve_verification_url(fake_request)
        assert url == "http://localhost:5000/verify/{}"


class TestGetOrCreateVerification:
    def test_rejects_unverifiable_type(self, db_session, sample_tenant):
        rec = DocumentVerificationService.get_or_create_verification(
            "invoice", 1, sample_tenant.id
        )
        assert rec is None

    def test_creates_record_for_sale(
        self, db_session, sample_tenant, sample_sale, sample_user
    ):
        rec = DocumentVerificationService.get_or_create_verification(
            "sale", sample_sale.id, sample_tenant.id, created_by=sample_user.id
        )
        assert rec is not None
        assert rec.tenant_id == sample_tenant.id
        assert rec.document_type == "sale"
        assert rec.document_id == sample_sale.id
        assert rec.created_by == sample_user.id
        assert rec.public_token
        assert rec.document_hash

    def test_second_call_returns_same_record(
        self, db_session, sample_tenant, sample_sale
    ):
        first = DocumentVerificationService.get_or_create_verification(
            "sale", sample_sale.id, sample_tenant.id
        )
        second = DocumentVerificationService.get_or_create_verification(
            "sale", sample_sale.id, sample_tenant.id
        )
        assert first is not None and second is not None
        assert second.id == first.id
        assert second.public_token == first.public_token


class TestLookupByToken:
    def test_blank_tokens_return_none(self, db_session):
        assert DocumentVerificationService.lookup_by_token(None) is None
        assert DocumentVerificationService.lookup_by_token("") is None
        assert DocumentVerificationService.lookup_by_token("   ") is None

    def test_unknown_token_returns_none(self, db_session):
        assert DocumentVerificationService.lookup_by_token("no-such-token") is None

    def test_valid_token_resolves_document(
        self, db_session, sample_tenant, sample_sale
    ):
        rec = DocumentVerificationService.get_or_create_verification(
            "sale", sample_sale.id, sample_tenant.id
        )
        result = DocumentVerificationService.lookup_by_token(f"  {rec.public_token}  ")
        assert result is not None
        assert result["tenant_id"] == sample_tenant.id
        assert result["document_type"] == "sale"
        assert result["document_id"] == sample_sale.id
        assert result["public_token"] == rec.public_token
        assert result["document"] is not None
        assert result["document"].id == sample_sale.id

    def test_missing_document_returns_none(self, db_session, sample_tenant):
        from models.document_verification import DocumentVerification

        rec = DocumentVerification.get_or_create(
            tenant_id=sample_tenant.id,
            document_type="sale",
            document_id=999999999,
            created_by=None,
        )
        db_session.flush()
        assert DocumentVerificationService.lookup_by_token(rec.public_token) is None


class TestResolveDocument:
    def test_unknown_type_returns_none(self, db_session, sample_tenant):
        assert (
            DocumentVerificationService._resolve_document(
                "invoice", 1, sample_tenant.id
            )
            is None
        )

    def test_missing_rows_return_none_for_all_types(self, db_session, sample_tenant):
        for doc_type in sorted(VERIFIABLE_TYPES):
            assert (
                DocumentVerificationService._resolve_document(
                    doc_type, 999999999, sample_tenant.id
                )
                is None
            )

    def test_resolves_sale_with_tenant_scope(
        self, db_session, sample_tenant, sample_sale
    ):
        doc = DocumentVerificationService._resolve_document(
            "sale", sample_sale.id, sample_tenant.id
        )
        assert doc is not None and doc.id == sample_sale.id
        # Cross-tenant resolution must not leak the document (IDOR guard).
        assert (
            DocumentVerificationService._resolve_document(
                "sale", sample_sale.id, sample_tenant.id + 9999
            )
            is None
        )


class TestBuildQrData:
    def test_returns_verification_url(self):
        doc = SimpleNamespace(id=7)
        qr = DocumentVerificationService.build_qr_data(
            document=doc,
            document_type="sale",
            settings=None,
            tenant=None,
            print_user_name="user",
            print_branch=None,
            verification_url="http://localhost/verify/abc",
        )
        assert qr == "http://localhost/verify/abc"
