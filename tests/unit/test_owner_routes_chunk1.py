"""
Chunk 1 — routes/owner.py first 3 endpoints:
  1. GET /owner/master-login-info
  2. GET /owner/                     (redirects to dashboard)
  3. GET /owner/dashboard            (stats aggregation page)
"""


class TestMasterLoginInfo:
    """GET /owner/master-login-info — template + master password info."""

    def test_returns_200_and_renders_template(self, owner_client, mocker):
        mock_status = {"enabled": True, "expires_at": "2026-06-23T23:59:59"}
        mock_password = "BREAK-GLASS-123"

        mocker.patch("utils.master_login.master_login_status", return_value=mock_status)
        mocker.patch(
            "utils.master_login.build_today_master_cleartext", return_value=mock_password
        )
        mock_render = mocker.patch(
            "routes.owner.render_template", return_value="<html>rendered</html>"
        )

        resp = owner_client.get("/owner/master-login-info")

        assert resp.status_code == 200
        mock_render.assert_called_once_with(
            "owner/master_login_info.html",
            status=mock_status,
            today_password=mock_password,
        )


class TestOwnerRoot:
    """GET /owner/ — redirects to /owner/dashboard."""

    def test_root_redirects_to_dashboard(self, owner_client):
        resp = owner_client.get("/owner/")
        assert resp.status_code == 302
        assert resp.headers["Location"].endswith("/owner/dashboard")


class TestOwnerDashboard:
    """GET /owner/dashboard — many aggregated stats."""

    def _patch_all(self, model_patch, counts):
        """Patch every model referenced by the route."""
        for name in ("User", "Customer", "Product", "Sale",
                     "Purchase", "SaleLine", "AuditLog", "Tenant"):
            model_patch(f"routes.owner.{name}", count=counts.get(name, 0))
        # Locally imported inside the function body
        model_patch("models.Branch", count=counts.get("Branch", 0))
        model_patch("models.Warehouse", count=counts.get("Warehouse", 0))

    def test_returns_200_empty_stats(self, owner_client, mocker, model_patch, mock_db_query):
        mocker.patch("routes.owner.get_active_tenant_id", return_value=None)
        mocker.patch("routes.owner._owner_branch_scope", return_value=None)

        self._patch_all(model_patch, {m: 0 for m in (
            "User", "Customer", "Product", "Sale", "Purchase",
            "SaleLine", "AuditLog", "Tenant", "Branch", "Warehouse",
        )})
        mocker.patch("routes.owner.db.session.query", mock_db_query)

        mocker.patch("utils.owner_panel.build_platform_overview", return_value={})
        mocker.patch("utils.owner_panel.build_tenant_management_rows", return_value=[])
        mocker.patch("utils.owner_panel.build_branding_overview_rows", return_value=[])
        mocker.patch("utils.owner_panel.build_system_health_summary", return_value={})
        mocker.patch("services.backup_service.BackupService.list_backups", return_value=[])
        mocker.patch("routes.owner.render_template", return_value="ok")

        resp = owner_client.get("/owner/dashboard")
        assert resp.status_code == 200

    def test_returns_200_with_data(self, owner_client, mocker, model_patch, mock_db_query):
        from itertools import cycle

        mocker.patch("routes.owner.get_active_tenant_id", return_value=None)
        mocker.patch("routes.owner._owner_branch_scope", return_value=None)

        self._patch_all(model_patch, {
            "User": 5, "Customer": 42, "Product": 100, "Sale": 8,
            "Purchase": 20, "AuditLog": 10, "Tenant": 3,
            "Branch": 0, "Warehouse": 0,
        })

        mock_db_query.filter.return_value.first.side_effect = cycle([
            (10, 5000.0, 500.0),     # today sales
            (120, 60000.0),            # month sales
            (80000.0, 40000.0),        # inventory
            (15000.0, 25),             # receivables
        ])
        mock_db_query.filter.return_value.scalar.side_effect = cycle([
            250000.0,         # year sales
            30000.0,          # month purchases
            15000.0,          # profit
        ])
        mocker.patch("routes.owner.db.session.query", mock_db_query)

        mocker.patch("utils.owner_panel.build_platform_overview", return_value={})
        mocker.patch("utils.owner_panel.build_tenant_management_rows", return_value=[])
        mocker.patch("utils.owner_panel.build_branding_overview_rows", return_value=[])
        mocker.patch("utils.owner_panel.build_system_health_summary", return_value={})
        mocker.patch("services.backup_service.BackupService.list_backups", return_value=[])
        mocker.patch("routes.owner.render_template", return_value="ok")

        resp = owner_client.get("/owner/dashboard")
        assert resp.status_code == 200
