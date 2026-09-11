"""Cov4: document_verification_service — url/type/token/resolve/qr arcs."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from services.document_verification_service import DocumentVerificationService


def test_resolve_verification_url():
    req = SimpleNamespace(url_root="https://x.example.com/")
    assert DocumentVerificationService.resolve_verification_url(req) == "https://x.example.com/verify/{}"


def test_get_or_create_unverifiable_type():
    assert DocumentVerificationService.get_or_create_verification("rocket", 1, 1) is None


def test_get_or_create_success(db_session, sample_tenant):
    from models.document_verification import DocumentVerification

    with patch.object(DocumentVerification, "get_or_create", return_value=SimpleNamespace(id=1)) as g:
        out = DocumentVerificationService.get_or_create_verification("sale", 5, sample_tenant.id)
        assert out.id == 1
        g.assert_called_once()


def test_get_or_create_exception_returns_none():
    from models.document_verification import DocumentVerification

    with patch.object(DocumentVerification, "get_or_create", side_effect=RuntimeError("db down")):
        assert DocumentVerificationService.get_or_create_verification("sale", 5, 1) is None


def test_lookup_by_token_blanks():
    assert DocumentVerificationService.lookup_by_token(None) is None
    assert DocumentVerificationService.lookup_by_token("   ") is None


def test_lookup_by_token_missing_record(db_session):
    assert DocumentVerificationService.lookup_by_token("no-such-token") is None


def test_lookup_by_token_doc_gone(monkeypatch):
    from models.document_verification import DocumentVerification

    rec = SimpleNamespace(
        document_type="sale", document_id=123, tenant_id=1,
        document_hash="h", public_token="tok", created_at=None,
    )
    q = MagicMock()
    q.filter_by.return_value.first.return_value = rec
    monkeypatch.setattr(DocumentVerification, "query", q)
    monkeypatch.setattr(DocumentVerificationService, "_resolve_document", staticmethod(lambda *a: None))
    assert DocumentVerificationService.lookup_by_token("tok") is None


def test_lookup_by_token_success(monkeypatch):
    from models.document_verification import DocumentVerification

    rec = SimpleNamespace(
        document_type="sale", document_id=7, tenant_id=2,
        document_hash="h", public_token="tok", created_at="now",
    )
    q = MagicMock()
    q.filter_by.return_value.first.return_value = rec
    monkeypatch.setattr(DocumentVerification, "query", q)
    monkeypatch.setattr(
        DocumentVerificationService, "_resolve_document", staticmethod(lambda *a: {"id": 7})
    )
    out = DocumentVerificationService.lookup_by_token("  tok ")
    assert out["document"] == {"id": 7}
    assert out["tenant_id"] == 2


def test_resolve_document_all_types(db_session, sample_tenant):
    for dtype in ["sale", "payment", "receipt", "purchase", "expense", "unknown"]:
        assert DocumentVerificationService._resolve_document(dtype, 999999999, sample_tenant.id) is None


def test_resolve_document_exception_branch(db_session, sample_tenant):
    # Real DB boundary failure: non-integer id on an integer PK raises
    # (DataError) inside the try -> except arc returns None.
    from unittest.mock import patch
    with patch("services.document_verification_service.logger"):
        assert DocumentVerificationService._resolve_document("sale", "not-an-integer", sample_tenant.id) is None
    db_session.rollback()


def test_build_qr_data_prefers_numbers(sample_tenant):
    tenant = SimpleNamespace(default_currency="AED")
    doc = SimpleNamespace(sale_number="S-1", total_amount=100, currency="USD", id=9)
    assert DocumentVerificationService.build_qr_data(doc, "sale", {}, tenant, "u", "b", "URL") == "URL"
    doc2 = SimpleNamespace(id=9, amount=50)
    assert DocumentVerificationService.build_qr_data(doc2, "x", {}, None, "u", "b", "U2") == "U2"
