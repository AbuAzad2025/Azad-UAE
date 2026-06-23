import pytest
from decimal import Decimal
from datetime import datetime, timezone


class TestPaymentsReceipts:
    def test_receipts_list_returns_200(self, auth_client, db_session, sample_tenant, sample_customer):
        import uuid
        from models import Receipt

        receipt = Receipt(
            tenant_id=sample_tenant.id,
            receipt_number=f'REC-{uuid.uuid4().hex[:8].upper()}',
            customer_id=sample_customer.id,
            amount=Decimal('100.000'),
            currency='AED',
            amount_aed=Decimal('100.000'),
            payment_method='cash',
            receipt_date=datetime.now(timezone.utc),
        )
        db_session.add(receipt)
        db_session.commit()

        resp = auth_client.get('/payments/receipts')
        assert resp.status_code == 200

    def test_search_entities_returns_customers_json(self, auth_client, db_session, sample_tenant, sample_customer, sample_branch):
        import uuid
        from models import Receipt
        from decimal import Decimal
        from datetime import datetime, timezone

        receipt = Receipt(
            tenant_id=sample_tenant.id,
            receipt_number=f'REC-{uuid.uuid4().hex[:8].upper()}',
            customer_id=sample_customer.id,
            amount=Decimal('100.000'),
            currency='AED',
            amount_aed=Decimal('100.000'),
            payment_method='cash',
            branch_id=sample_branch.id,
            receipt_date=datetime.now(timezone.utc),
        )
        db_session.add(receipt)
        db_session.commit()

        resp = auth_client.get('/payments/search-entities?type=customer&q=Test')
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data) >= 1
        assert data[0]['name'] == 'Test Customer'
        assert data[0]['phone'] == '0555000001'
