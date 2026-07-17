"""Coverage Wave Agent-3 — route edge-branch tests.

Targets: routes/treasury.py lines 62-63 (export: unscoped user lacking
branch access → 403).
"""

from unittest.mock import patch

import pytest


@pytest.fixture
def treasury_client(app_factory, bypass_permission_auth):
    from routes.treasury import treasury_bp

    app = app_factory(treasury_bp)
    return app.test_client()


class TestTreasuryExportBranchAccess:
    def test_export_unscoped_branch_not_accessible_403(self, treasury_client):
        with (
            patch(
                "services.treasury_service.TreasuryService.build_dashboard",
                return_value={"liquidity": {"accounts": []}},
            ),
            patch("routes.treasury.report_branch_scope_id", return_value=None),
            patch("routes.treasury.user_can_access_branch", return_value=False),
            patch(
                "routes.treasury.render_template", return_value="forbidden"
            ) as render,
        ):
            resp = treasury_client.get("/reports/treasury/export?branch_id=9")
        assert resp.status_code == 403
        render.assert_called_once_with("errors/403.html")
