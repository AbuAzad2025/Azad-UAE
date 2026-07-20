"""Unit tests for models/document_snapshot.py — immutable DocumentSnapshot records."""

from __future__ import annotations


class TestDocumentSnapshotCreate:
    def test_create_with_defaults(self, db_session, sample_tenant):
        from models.document_snapshot import DocumentSnapshot

        snap = DocumentSnapshot(
            tenant_id=sample_tenant.id,
            document_type="sale",
            document_id=42,
            snapshot_data={"total": "100.00", "lines": [1, 2]},
        )
        db_session.add(snap)
        db_session.commit()

        assert snap.id is not None
        assert snap.snapshot_reason == "print"
        assert snap.branding_snapshot is None
        assert snap.created_at is not None
        assert snap.created_by is None

    def test_json_payload_round_trip(self, db_session, sample_tenant):
        from models.document_snapshot import DocumentSnapshot

        payload = {"customer": "عميل", "amounts": [1.5, 2.5], "meta": {"a": 1}}
        snap = DocumentSnapshot(
            tenant_id=sample_tenant.id,
            document_type="invoice",
            document_id=7,
            snapshot_data=payload,
            branding_snapshot={"logo": "default.png"},
            snapshot_reason="finalize",
        )
        db_session.add(snap)
        db_session.commit()
        db_session.expire_all()

        refreshed = DocumentSnapshot.query.get(snap.id)
        assert refreshed.snapshot_data == payload
        assert refreshed.branding_snapshot == {"logo": "default.png"}
        assert refreshed.snapshot_reason == "finalize"

    def test_created_by_user_relationship(self, db_session, sample_tenant, sample_user):
        from models.document_snapshot import DocumentSnapshot

        snap = DocumentSnapshot(
            tenant_id=sample_tenant.id,
            document_type="sale",
            document_id=1,
            snapshot_data={},
            created_by=sample_user.id,
        )
        db_session.add(snap)
        db_session.commit()

        assert snap.user is not None
        assert snap.user.id == sample_user.id


class TestDocumentSnapshotRepresentation:
    def test_repr(self, db_session, sample_tenant):
        from models.document_snapshot import DocumentSnapshot

        snap = DocumentSnapshot(
            tenant_id=sample_tenant.id,
            document_type="sale",
            document_id=9,
            snapshot_data={},
            snapshot_reason="amend",
        )
        assert repr(snap) == "<DocumentSnapshot sale#9 amend>"

    def test_to_dict(self, db_session, sample_tenant, sample_user):
        from models.document_snapshot import DocumentSnapshot

        snap = DocumentSnapshot(
            tenant_id=sample_tenant.id,
            document_type="purchase",
            document_id=3,
            snapshot_data={"x": 1},
            created_by=sample_user.id,
        )
        db_session.add(snap)
        db_session.commit()

        d = snap.to_dict()
        assert d["tenant_id"] == sample_tenant.id
        assert d["document_type"] == "purchase"
        assert d["document_id"] == 3
        assert d["snapshot_reason"] == "print"
        assert d["created_by"] == sample_user.id
        assert d["created_at"] is not None
        assert set(d) == {
            "id",
            "tenant_id",
            "document_type",
            "document_id",
            "snapshot_reason",
            "created_at",
            "created_by",
        }
