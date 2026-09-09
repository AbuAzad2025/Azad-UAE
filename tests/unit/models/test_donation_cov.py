"""Coverage for Donation tenant-unfiltered query arcs (140->142, 148->150, 160->162)."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from models.donation import Donation


def _seed(db_session, tenant_id):
    rows = [
        Donation(
            tenant_id=tenant_id,
            amount_usd=Decimal("100"),
            payment_method="card",
            status="completed",
            completed_at=datetime(2025, 6, 2, tzinfo=UTC),
        ),
        Donation(
            tenant_id=tenant_id,
            amount_usd=Decimal("50"),
            payment_method="crypto",
            status="completed",
            completed_at=datetime(2025, 6, 1, tzinfo=UTC),
        ),
        Donation(
            tenant_id=tenant_id,
            amount_usd=Decimal("20"),
            payment_method="paypal",
            status="pending",
        ),
    ]
    db_session.add_all(rows)
    db_session.commit()
    return rows


class TestDonationPendingCountUnfiltered:
    def test_get_pending_count_without_tenant(self, db_session, sample_tenant):
        """Arc 140->142: tenant_id is None skips the tenant filter."""
        _seed(db_session, sample_tenant.id)
        assert Donation.get_pending_count() >= 1

    def test_get_pending_count_filtered_and_unfiltered_agree(self, db_session, sample_tenant):
        _seed(db_session, sample_tenant.id)
        assert Donation.get_pending_count(tenant_id=sample_tenant.id) == 1
        assert Donation.get_pending_count() >= Donation.get_pending_count(tenant_id=sample_tenant.id)


class TestDonationRecentUnfiltered:
    def test_get_recent_donations_without_tenant(self, db_session, sample_tenant):
        """Arc 148->150: tenant_id is None skips the tenant filter."""
        _seed(db_session, sample_tenant.id)
        # Unfiltered window may include other tests' rows (shared CI DB),
        # so scope the assertion to this test's own tenant rows.
        recent = Donation.get_recent_donations(limit=1000)
        mine = {r.payment_method for r in recent if r.tenant_id == sample_tenant.id}
        assert mine >= {"card", "crypto"}

    def test_get_recent_donations_filtered_orders_by_completed_at(self, db_session, sample_tenant):
        _seed(db_session, sample_tenant.id)
        recent = Donation.get_recent_donations(limit=1, tenant_id=sample_tenant.id)
        assert len(recent) == 1
        assert recent[0].amount_usd == Decimal("100")


class TestDonationByMethodUnfiltered:
    def test_get_donations_by_method_without_tenant(self, db_session, sample_tenant):
        """Arc 160->162: tenant_id is None skips the tenant filter."""
        _seed(db_session, sample_tenant.id)
        by_method = Donation.get_donations_by_method()
        methods = {row["method"]: row for row in by_method}
        assert methods["card"]["count"] >= 1
        assert methods["card"]["total"] >= 100.0
        assert methods["crypto"]["total"] >= 50.0

    def test_get_donations_by_method_filtered(self, db_session, sample_tenant):
        _seed(db_session, sample_tenant.id)
        by_method = Donation.get_donations_by_method(tenant_id=sample_tenant.id)
        methods = {row["method"]: row for row in by_method}
        assert methods["card"]["count"] == 1
        assert methods["crypto"]["total"] == 50.0
