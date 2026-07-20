"""Unit tests for models/document_verification.py — hash + public-token traceability."""

from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError


class TestHashAndTokenGeneration:
    def test_generate_hash_is_sha256_hex(self):
        from models.document_verification import DocumentVerification

        h = DocumentVerification._generate_hash(1, "sale", 10)
        assert isinstance(h, str)
        assert len(h) == 64
        int(h, 16)  # valid hex

    def test_generate_hash_unique_per_call(self):
        from models.document_verification import DocumentVerification

        # A uuid4 component makes every candidate hash distinct.
        assert DocumentVerification._generate_hash(
            1, "sale", 10
        ) != DocumentVerification._generate_hash(1, "sale", 10)

    def test_generate_token_is_uuid4_hex(self):
        from models.document_verification import DocumentVerification

        token = DocumentVerification._generate_token()
        assert isinstance(token, str)
        assert len(token) == 32
        int(token, 16)


class TestGetOrCreate:
    def test_creates_record_with_hash_and_token(self, db_session, sample_tenant):
        from models.document_verification import DocumentVerification

        rec = DocumentVerification.get_or_create(sample_tenant.id, "sale", 100)
        db_session.commit()

        assert rec.id is not None
        assert len(rec.document_hash) == 64
        assert len(rec.public_token) == 32
        assert rec.created_at is not None
        assert rec.created_by is None

    def test_idempotent_returns_existing(self, db_session, sample_tenant):
        from models.document_verification import DocumentVerification

        first = DocumentVerification.get_or_create(sample_tenant.id, "sale", 100)
        db_session.commit()
        second = DocumentVerification.get_or_create(sample_tenant.id, "sale", 100)
        db_session.commit()

        assert second.id == first.id
        assert second.document_hash == first.document_hash
        assert second.public_token == first.public_token
        assert (
            DocumentVerification.query.filter_by(
                tenant_id=sample_tenant.id, document_type="sale", document_id=100
            ).count()
            == 1
        )

    def test_distinct_documents_get_distinct_records(self, db_session, sample_tenant):
        from models.document_verification import DocumentVerification

        a = DocumentVerification.get_or_create(sample_tenant.id, "sale", 1)
        b = DocumentVerification.get_or_create(sample_tenant.id, "sale", 2)
        c = DocumentVerification.get_or_create(sample_tenant.id, "purchase", 1)
        db_session.commit()

        hashes = {a.document_hash, b.document_hash, c.document_hash}
        tokens = {a.public_token, b.public_token, c.public_token}
        assert len(hashes) == 3
        assert len(tokens) == 3

    def test_created_by_recorded(self, db_session, sample_tenant, sample_user):
        from models.document_verification import DocumentVerification

        rec = DocumentVerification.get_or_create(
            sample_tenant.id, "sale", 5, created_by=sample_user.id
        )
        db_session.commit()
        assert rec.created_by == sample_user.id


class TestUniquenessConstraints:
    def test_document_hash_unique(self, db_session, sample_tenant):
        from models.document_verification import DocumentVerification

        rec = DocumentVerification.get_or_create(sample_tenant.id, "sale", 1)
        db_session.commit()

        db_session.add(
            DocumentVerification(
                tenant_id=sample_tenant.id,
                document_type="sale",
                document_id=999,
                document_hash=rec.document_hash,
                public_token=DocumentVerification._generate_token(),
            )
        )
        with pytest.raises(IntegrityError):
            db_session.flush()
        db_session.rollback()

    def test_tenant_document_triple_unique(self, db_session, sample_tenant):
        from models.document_verification import DocumentVerification

        DocumentVerification.get_or_create(sample_tenant.id, "sale", 1)
        db_session.commit()

        db_session.add(
            DocumentVerification(
                tenant_id=sample_tenant.id,
                document_type="sale",
                document_id=1,
                document_hash=DocumentVerification._generate_hash(
                    sample_tenant.id, "sale", 1
                ),
                public_token=DocumentVerification._generate_token(),
            )
        )
        with pytest.raises(IntegrityError):
            db_session.flush()
        db_session.rollback()


class TestToDict:
    def test_to_dict_shape(self, db_session, sample_tenant):
        from models.document_verification import DocumentVerification

        rec = DocumentVerification.get_or_create(sample_tenant.id, "sale", 7)
        db_session.commit()

        d = rec.to_dict()
        assert d["tenant_id"] == sample_tenant.id
        assert d["document_type"] == "sale"
        assert d["document_id"] == 7
        assert d["document_hash"] == rec.document_hash
        assert d["public_token"] == rec.public_token
        assert d["created_at"] is not None
        assert set(d) == {
            "id",
            "tenant_id",
            "document_type",
            "document_id",
            "document_hash",
            "public_token",
            "created_at",
        }
