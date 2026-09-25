"""Feature-gate regression guards (package flags).

Pins the safe scoping decided after the blanket api_bp gate broke 16
integration tests: infrastructure/session APIs are never gated by
``enable_api`` (default False), while genuinely optional modules
(``enable_gl``) are enforced at their blueprint boundary.
"""

from __future__ import annotations


class TestLedgerGate:
    def test_ledger_denied_when_gl_disabled(self, auth_client, db_session, sample_tenant):
        sample_tenant.enable_gl = False
        db_session.flush()
        resp = auth_client.get("/ledger/")
        assert resp.status_code == 403

    def test_ledger_allowed_by_default(self, auth_client, db_session, sample_tenant):
        sample_tenant.enable_gl = True
        db_session.flush()
        resp = auth_client.get("/ledger/")
        assert resp.status_code != 403


class TestApiNeverGated:
    def test_health_open_with_api_disabled(self, client, db_session, sample_tenant):
        sample_tenant.enable_api = False
        db_session.flush()
        resp = client.get("/api/health")
        assert resp.status_code == 200

    def test_internal_api_open_with_flag_off(self, auth_client, db_session, sample_tenant):
        sample_tenant.enable_api = False
        db_session.flush()
        resp = auth_client.get("/api/currencies")
        assert resp.status_code == 200
