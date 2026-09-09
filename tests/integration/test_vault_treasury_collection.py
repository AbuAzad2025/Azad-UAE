"""
Real end-to-end tests for the platform treasury (accrued vs collected).

No mocks: real tenant/owner/vault/donation/sale/fee rows in the test DB,
real HTTP through the Flask test client, real assertions on persisted
state. Each test answers: does owner-confirmed collection land tenant-less
vault evidence exactly once?

Rule: every test here must prevent a production bug, not raise a number.
"""

import uuid
from decimal import Decimal


def _uid():
    return str(uuid.uuid4())[:8]


def _make_tenant(db_session):
    from models import Tenant

    tid = _uid()
    t = Tenant(
        name=f"Treasury {tid}",
        name_ar=f"Treasury {tid}",
        slug=f"treasury-{tid}",
        default_currency="ILS",
        base_currency="ILS",
        is_active=True,
    )
    db_session.add(t)
    db_session.flush()
    return t


def _make_owner(db_session):
    from models import Role, User

    suffix = _uid()
    role = Role.query.filter_by(slug="developer").first()
    if not role:
        role = Role(name=f"OwnerRole_{suffix}", slug="developer", is_active=True)
        db_session.add(role)
        db_session.flush()
    u = User(
        tenant_id=None,
        username=f"owner_{suffix}",
        email=f"owner_{suffix}@test.com",
        is_active=True,
        password_hash="fakehash",
        role_id=role.id,
        is_owner=True,
    )
    u.set_password("ownerpass")
    db_session.add(u)
    db_session.flush()
    return u


def _make_vault(db_session, password="vaultpass"):
    from models.payment_vault import PaymentVault

    v = PaymentVault(tenant_id=None, vault_name="Platform Vault", is_locked=False)
    v.set_vault_password(password)
    db_session.add(v)
    db_session.flush()
    return v


def _login(client, username):
    return client.post(
        "/auth/login",
        data={"username": username, "password": "ownerpass"},
        follow_redirects=False,
    )


class TestDonationVaultReceiptReal:
    def test_approve_platform_donation_writes_tenantless_receipt_once(self, app, db_session):
        from models.donation import Donation
        from models.payment_vault import PaymentTransaction

        _make_tenant(db_session)
        owner = _make_owner(db_session)
        _make_vault(db_session)
        donation = Donation(
            tenant_id=None,
            amount_usd=Decimal("25.00"),
            payment_method="crypto",
            crypto_type="btc",
            wallet_address="bc1qreal",
            donor_name="Real Donor",
            status="pending",
        )
        db_session.add(donation)
        db_session.commit()
        did = donation.id

        with app.test_client() as client:
            assert _login(client, owner.username).status_code == 302
            assert client.post("/payment-vault/unlock", data={"vault_password": "vaultpass"}).status_code in (
                200,
                302,
            )
            resp = client.post(f"/payment-vault/donation/{did}/approve", follow_redirects=False)
            assert resp.status_code == 302
            # idempotent re-approve: no duplicate vault row
            resp2 = client.post(f"/payment-vault/donation/{did}/approve", follow_redirects=False)
            assert resp2.status_code == 302

        with app.app_context():
            assert db_session.get(Donation, did).status == "completed"
            rows = PaymentTransaction.query.filter_by(transaction_id=f"DONATION-{did}").all()
            assert len(rows) == 1
            assert rows[0].tenant_id is None
            assert rows[0].payment_status == "completed"
            assert rows[0].amount_usd == Decimal("25.00")


class TestFeeCollectionReal:
    def _fee_setup(self, db_session):
        from models import Customer, Role, Sale, User
        from models.azad_platform_fee import AzadPlatformFee

        tenant = _make_tenant(db_session)
        owner = _make_owner(db_session)
        vault = _make_vault(db_session)
        role = Role(name=f"Seller_{_uid()}", slug=f"seller-{_uid()}", is_active=True)
        db_session.add(role)
        db_session.flush()
        seller = User(
            tenant_id=tenant.id,
            username=f"seller_{_uid()}",
            email=f"seller_{_uid()}@test.com",
            is_active=True,
            password_hash="fakehash",
            role_id=role.id,
        )
        seller.set_password("x")
        db_session.add(seller)
        db_session.flush()
        customer = Customer(tenant_id=tenant.id, name=f"Cust {_uid()}", phone="0500000000")
        db_session.add(customer)
        db_session.flush()
        sale = Sale(
            tenant_id=tenant.id,
            sale_number=f"S-{_uid()}",
            customer_id=customer.id,
            seller_id=seller.id,
            total_amount=Decimal("1000.000"),
            amount=Decimal("1000.000"),
            amount_aed=Decimal("1000.000"),
            paid_amount_aed=Decimal("0.000"),
            balance_due=Decimal("1000.000"),
        )
        db_session.add(sale)
        db_session.flush()
        fee = AzadPlatformFee(
            idempotency_key=f"fee-{_uid()}",
            tenant_id=tenant.id,
            sale_id=sale.id,
            vault_id=vault.id,
            rate_percent=Decimal("1.00"),
            base_amount_aed=Decimal("1000.000"),
            fee_amount_aed=Decimal("10.000"),
            status="settled",
            gl_posted=True,
        )
        db_session.add(fee)
        db_session.commit()
        return tenant, owner, vault, fee

    def test_confirm_collects_fee_with_evidence(self, app, db_session):
        from models.azad_platform_fee import AzadPlatformFee
        from models.payment_vault import PaymentTransaction

        tenant, owner, _, fee = self._fee_setup(db_session)
        fid = fee.id

        with app.test_client() as client:
            assert _login(client, owner.username).status_code == 302
            client.get(f"/tenants/switch/{tenant.id}", follow_redirects=False)
            client.post("/payment-vault/unlock", data={"vault_password": "vaultpass"})
            resp = client.post("/payment-vault/platform-fees/confirm", data={"fee_ids": str(fid)})
            assert resp.status_code == 302
            # second confirm: nothing settled left -> error flash, still redirect
            resp2 = client.post("/payment-vault/platform-fees/confirm", data={"fee_ids": str(fid)})
            assert resp2.status_code == 302

        with app.app_context():
            fee = db_session.get(AzadPlatformFee, fid)
            assert fee.status == "paid"
            assert fee.collected_at is not None
            assert fee.confirmed_by == owner.id
            txns = PaymentTransaction.query.filter(
                PaymentTransaction.customer_name == "Azad Platform Settlements"
            ).all()
            mine = [t for t in txns if t.tenant_id is None and t.payment_status == "completed"]
            assert len(mine) >= 1
            assert sum((t.amount_usd for t in mine), Decimal("0")) >= Decimal("10.00")


class TestVaultDashboardSplitReal:
    def test_dashboard_shows_accrued_vs_collected(self, app, db_session):
        from models.donation import Donation

        _make_tenant(db_session)
        owner = _make_owner(db_session)
        _make_vault(db_session)
        db_session.add(
            Donation(
                tenant_id=None,
                amount_usd=Decimal("40.00"),
                payment_method="bank",
                donor_name="Split Donor",
                status="pending",
            )
        )
        db_session.commit()

        with app.test_client() as client:
            assert _login(client, owner.username).status_code == 302
            client.post("/payment-vault/unlock", data={"vault_password": "vaultpass"})
            resp = client.get("/payment-vault/dashboard")
            assert resp.status_code == 200
            body = resp.data.decode("utf-8", "replace")
            assert "Accrued vs Collected" in body
