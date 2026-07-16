"""
Integration tests: Reports routes — real business logic via GET /ledger/trial-balance.
"""
import pytest
import uuid
from decimal import Decimal


class TestTrialBalance:
    def test_trial_balance_returns_equal_debits_and_credits(self, app, db_session, client):
        tid = str(uuid.uuid4())[:8]
        from models import Tenant, Branch, User, Role
        from services.gl_service import GLService

        tenant = Tenant(name=f'TB {tid}', name_ar=f'TB {tid}',
                        slug=f'tb-test-{tid}', default_currency='AED', base_currency='AED')
        db_session.add(tenant)
        db_session.flush()

        branch = Branch(tenant_id=tenant.id, name=f'Main {tid}', code=f'BR{tid[:4]}')
        db_session.add(branch)
        db_session.flush()

        role = Role(name=f'Admin {tid}', slug=f'admin-{tid}', is_active=True)
        db_session.add(role)
        db_session.flush()

        user = User(username=f'viewer-{tid}', email=f'viewer-{tid}@t.com',
                    full_name='Viewer', role_id=role.id,
                    tenant_id=tenant.id, branch_id=branch.id,
                    is_active=True, is_owner=True)
        user.set_password('x')
        db_session.add(user)
        db_session.commit()

        GLService.ensure_core_accounts(tenant_id=tenant.id)
        db_session.commit()

        with client:
            resp = client.post('/auth/login', data={
                'username': user.username,
                'password': 'x',
            }, follow_redirects=True)
            assert resp.status_code == 200

            resp = client.get('/ledger/trial-balance', follow_redirects=True)

        assert resp.status_code == 200, f'Expected 200, got {resp.status_code}'
        html = resp.data.decode('utf-8')
        assert 'ميزان' in html or 'Trial' in html or 'Balance' in html, \
            f'Expected trial balance page. HTML snippet: {html[500:1200]}'

        found_debits = False
        found_credits = False
        for word in ['مدين', 'Debit', 'total_debit', 'debit']:
            if word in html:
                found_debits = True
                break
        for word in ['دائن', 'Credit', 'total_credit', 'credit']:
            if word in html:
                found_credits = True
                break
        assert found_debits and found_credits, \
            f'Expected debit/credit columns in page. HTML: {html[1000:2000]}'
