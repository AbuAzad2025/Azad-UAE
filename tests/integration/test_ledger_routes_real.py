"""
Real route tests: Ledger routes — HTTP client.get() only.
"""
import uuid
from decimal import Decimal


class TestLedgerJournalList:
    def test_journal_list_page_renders(self, app, db_session, client):
        from models import Tenant, Branch, User, Role
        from models.gl import GLJournalEntry

        tid = str(uuid.uuid4())[:8]
        tenant = Tenant(name=f'LG {tid}', name_ar=f'LG {tid}', slug=f'lg-{tid}', default_currency='AED', base_currency='AED')
        db_session.add(tenant); db_session.flush()
        branch = Branch(tenant_id=tenant.id, name=f'Main {tid}', code=f'BR{tid[:4]}')
        db_session.add(branch); db_session.flush()
        role = Role(name=f'Admin {tid}', slug=f'admin-{tid}', is_active=True)
        db_session.add(role); db_session.flush()
        user = User(username=f'lguser-{tid}', email=f'lg-{tid}@t.com',
                    full_name='Accountant', role_id=role.id,
                    tenant_id=tenant.id, branch_id=branch.id,
                    is_active=True, is_owner=True)
        user.set_password('x')
        db_session.add(user); db_session.flush()

        entry = GLJournalEntry(tenant_id=tenant.id, entry_number=f'JE-{tid}',
                               branch_id=branch.id, description='Test entry',
                               total_debit=Decimal('100'), total_credit=Decimal('100'),
                               is_posted=True, currency='AED', exchange_rate=Decimal('1'))
        db_session.add(entry); db_session.commit()

        with client:
            client.post('/auth/login', data={'username': user.username, 'password': 'x'},
                        follow_redirects=True)
            resp = client.get('/ledger/journal-entries')
        assert resp.status_code == 200
        assert entry.entry_number.encode() in resp.data
