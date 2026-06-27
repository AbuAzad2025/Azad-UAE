from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from models.donation import Donation


class TestDonationInstance:
    def test_repr(self, sample_tenant):
        d = Donation(
            tenant_id=sample_tenant.id,
            amount_usd=Decimal('25.00'),
            payment_method='card',
            status='pending',
        )
        assert '25' in repr(d)
        assert 'card' in repr(d)

    def test_is_completed_and_pending(self, sample_tenant):
        done = Donation(
            tenant_id=sample_tenant.id,
            amount_usd=Decimal('10'),
            payment_method='paypal',
            status='completed',
        )
        pending = Donation(
            tenant_id=sample_tenant.id,
            amount_usd=Decimal('10'),
            payment_method='paypal',
            status='pending',
        )
        assert done.is_completed is True
        assert done.is_pending is False
        assert pending.is_pending is True
        assert pending.is_completed is False

    def test_to_dict_with_dates(self, sample_tenant):
        now = datetime(2025, 6, 1, 12, 0, tzinfo=timezone.utc)
        d = Donation(
            tenant_id=sample_tenant.id,
            amount_usd=Decimal('50.00'),
            amount_crypto=Decimal('0.001'),
            payment_method='crypto',
            crypto_type='btc',
            status='completed',
            donor_name='Ali',
            created_at=now,
            confirmed_at=now,
            completed_at=now,
        )
        data = d.to_dict()
        assert data['amount_usd'] == 50.0
        assert data['amount_crypto'] == 0.001
        assert data['donor_name'] == 'Ali'
        assert data['created_at'] == now.isoformat()

    def test_to_dict_null_amounts(self, sample_tenant):
        d = Donation(
            tenant_id=sample_tenant.id,
            amount_usd=None,
            payment_method='bank',
            status='failed',
        )
        data = d.to_dict()
        assert data['amount_usd'] == 0
        assert data['amount_crypto'] is None
        assert data['confirmed_at'] is None


class TestDonationAggregates:
    def _seed(self, db_session, tenant_id, other_tenant_id=None):
        rows = [
            Donation(
                tenant_id=tenant_id,
                amount_usd=Decimal('100'),
                payment_method='card',
                status='completed',
                completed_at=datetime(2025, 6, 2, tzinfo=timezone.utc),
            ),
            Donation(
                tenant_id=tenant_id,
                amount_usd=Decimal('50'),
                payment_method='crypto',
                status='completed',
                completed_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
            ),
            Donation(
                tenant_id=tenant_id,
                amount_usd=Decimal('20'),
                payment_method='paypal',
                status='pending',
            ),
        ]
        if other_tenant_id is not None:
            rows.append(
                Donation(
                    tenant_id=other_tenant_id,
                    amount_usd=Decimal('999'),
                    payment_method='card',
                    status='completed',
                    completed_at=datetime(2025, 6, 3, tzinfo=timezone.utc),
                )
            )
        db_session.add_all(rows)
        db_session.commit()

    def test_get_total_donations_all_tenants(self, db_session, sample_tenant):
        import uuid
        from models import Tenant

        suffix = uuid.uuid4().hex[:8]
        other = Tenant(
            name=f'Other Donor Tenant {suffix}',
            name_ar='آخر',
            name_en=f'Other {suffix}',
            slug=f'other-don-{suffix}',
            default_currency='AED',
        )
        db_session.add(other)
        db_session.commit()
        self._seed(db_session, sample_tenant.id, other_tenant_id=other.id)
        total = Donation.get_total_donations()
        assert total >= 1149.0

    def test_get_total_donations_filtered(self, db_session, sample_tenant):
        self._seed(db_session, sample_tenant.id)
        assert Donation.get_total_donations(tenant_id=sample_tenant.id) == 150.0

    def test_get_total_donations_empty(self, db_session, sample_tenant):
        assert Donation.get_total_donations(tenant_id=sample_tenant.id) == 0

    def test_get_donations_count(self, db_session, sample_tenant):
        self._seed(db_session, sample_tenant.id)
        assert Donation.get_donations_count(tenant_id=sample_tenant.id) == 2
        assert Donation.get_donations_count() >= 2

    def test_get_pending_count(self, db_session, sample_tenant):
        self._seed(db_session, sample_tenant.id)
        assert Donation.get_pending_count(tenant_id=sample_tenant.id) == 1

    def test_get_recent_donations(self, db_session, sample_tenant):
        self._seed(db_session, sample_tenant.id)
        recent = Donation.get_recent_donations(limit=1, tenant_id=sample_tenant.id)
        assert len(recent) == 1
        assert recent[0].amount_usd == Decimal('100')

    def test_get_donations_by_method(self, db_session, sample_tenant):
        self._seed(db_session, sample_tenant.id)
        by_method = Donation.get_donations_by_method(tenant_id=sample_tenant.id)
        methods = {row['method']: row for row in by_method}
        assert methods['card']['count'] == 1
        assert methods['card']['total'] == 100.0
        assert methods['crypto']['total'] == 50.0
