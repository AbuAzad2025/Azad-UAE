"""Regression tests: platform (NULL-tenant) integration settings.

Covers the /owner/integrations 500: get_service_config with tenant_id=None
must create/read the platform-global row and never leak a tenant's row.
"""

from __future__ import annotations

import uuid

from models.integration_settings import IntegrationSettings


def _unique_service(prefix="svc"):
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


class TestPlatformServiceConfig:
    def test_platform_row_created_with_null_tenant(self, db_session):
        service = _unique_service()
        row = IntegrationSettings.get_service_config(service)
        db_session.flush()
        assert row.id is not None
        assert row.tenant_id is None
        assert row.enabled is False
        assert row.get_config() == {}

    def test_platform_row_returned_on_second_call(self, db_session):
        service = _unique_service()
        first = IntegrationSettings.get_service_config(service)
        db_session.flush()
        second = IntegrationSettings.get_service_config(service)
        assert second.id == first.id

    def test_platform_scope_never_returns_tenant_row(self, db_session, sample_tenant):
        service = _unique_service()
        tenant_row = IntegrationSettings(service_name=service, tenant_id=sample_tenant.id)
        db_session.add(tenant_row)
        db_session.flush()

        platform_row = IntegrationSettings.get_service_config(service)
        db_session.flush()
        assert platform_row.id != tenant_row.id
        assert platform_row.tenant_id is None

    def test_tenant_scope_never_returns_platform_row(self, db_session, sample_tenant):
        service = _unique_service()
        platform_row = IntegrationSettings.get_service_config(service)
        db_session.flush()

        tenant_row = IntegrationSettings.get_service_config(service, sample_tenant.id)
        db_session.flush()
        assert tenant_row.id != platform_row.id
        assert tenant_row.tenant_id == sample_tenant.id

    def test_integrations_context_builds_from_platform_rows(self, db_session):
        from services.integration_service import IntegrationService

        ctx = IntegrationService.get_integrations_context()
        assert set(ctx) == {"whatsapp", "email", "redis", "currency_api"}
        assert ctx["whatsapp"]["status"] == "not_configured"
