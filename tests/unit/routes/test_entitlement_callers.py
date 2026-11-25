"""Entitlement callers: provisioning must follow a package purchase."""

from __future__ import annotations

from decimal import Decimal


class TestPackagePortalContract:
    def test_tenant_form_only_offers_real_slugs(self, owner_client, sample_tenant):
        html = owner_client.get(f"/owner/tenants/{sample_tenant.id}/edit").get_data(as_text=True)
        assert 'value="pro"' in html
        assert 'value="professional"' not in html
        assert 'value="standard"' not in html


class TestPackagePurchaseProvisioning:
    def test_activate_purchase_provisions_bound_tenant(self, owner_client, db_session, sample_tenant, mocker):
        from models.package import Package, PackagePurchase

        package = Package(
            name_ar="باقة اختبار",
            name_en="Entitlement Test",
            slug="entitlement-test",
            price=Decimal("99"),
            is_active=True,
        )
        db_session.add(package)
        db_session.flush()

        purchase = PackagePurchase(
            package_id=package.id,
            tenant_id=sample_tenant.id,
            customer_name="Test Buyer",
            customer_email="buyer@example.com",
            payment_method="bank",
            payment_status="pending",
            amount_paid=Decimal("99"),
        )
        db_session.add(purchase)
        db_session.commit()
        assert purchase.tenant_id == sample_tenant.id
        assert purchase.package_id == package.id

        provision = mocker.patch(
            "services.saas_provisioning_service.SaaSProvisioningService.activate_purchased_package"
        )

        response = owner_client.post(
            f"/payment-vault/purchase/{purchase.id}/activate",
            follow_redirects=False,
        )
        assert response.status_code == 302
        provision.assert_called_once_with(
            tenant_id=sample_tenant.id,
            package_id=package.id,
            duration_type="monthly",
        )
