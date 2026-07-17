"""Dashboard service — layout retrieval, tenant isolation, empty fallbacks."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from sqlalchemy.exc import IntegrityError


class TestLayoutRetrieval:
    """get_user_layout / get_default_layout — saved vs fallback."""

    def test_default_layout_is_stable_snapshot(self):
        from services.dashboard_service import DashboardService

        first = DashboardService.get_default_layout()
        second = DashboardService.get_default_layout()
        assert first == second
        assert first is not second

    def test_saved_layout_bypasses_default(self, mocker, app):
        from models.dashboard import UserDashboardLayout

        custom = {
            "widgets": [{"key": "inventory_alert", "x": 0, "y": 2, "w": 12, "h": 2}]
        }
        row = MagicMock(layout_json=custom)
        mock_q = MagicMock()
        mock_q.filter_by.return_value.first.return_value = row
        mocker.patch.object(
            UserDashboardLayout,
            "query",
            new_callable=mocker.PropertyMock,
            return_value=mock_q,
        )

        from services.dashboard_service import DashboardService

        with app.app_context():
            result = DashboardService.get_user_layout(tenant_id=5, user_id=10)
        assert result == custom
        mock_q.filter_by.assert_called_once_with(tenant_id=5, user_id=10)

    def test_missing_layout_falls_back_to_default(self, mocker, app):
        from models.dashboard import UserDashboardLayout

        mock_q = MagicMock()
        mock_q.filter_by.return_value.first.return_value = None
        mocker.patch.object(
            UserDashboardLayout,
            "query",
            new_callable=mocker.PropertyMock,
            return_value=mock_q,
        )

        from services.dashboard_service import DashboardService

        with app.app_context():
            fallback = DashboardService.get_user_layout(tenant_id=1, user_id=99)
        assert fallback["widgets"][0]["key"] == "sales_summary"


class TestMultiTenantIsolation:
    """Layouts and widgets scoped per tenant/user — no cross-tenant bleed."""

    def test_layout_queries_are_tenant_scoped(self, mocker, app):
        from models.dashboard import UserDashboardLayout

        mock_q = MagicMock()
        mock_q.filter_by.return_value.first.return_value = None
        mocker.patch.object(
            UserDashboardLayout,
            "query",
            new_callable=mocker.PropertyMock,
            return_value=mock_q,
        )

        from services.dashboard_service import DashboardService

        with app.app_context():
            DashboardService.get_user_layout(tenant_id=7, user_id=1)
            DashboardService.get_user_layout(tenant_id=8, user_id=1)

        calls = [c.kwargs for c in mock_q.filter_by.call_args_list]
        assert {"tenant_id": 7, "user_id": 1} in calls
        assert {"tenant_id": 8, "user_id": 1} in calls

    def test_save_layout_pins_tenant_on_create(self, app, mocker):
        from models.dashboard import UserDashboardLayout

        mock_q = MagicMock()
        mock_q.filter_by.return_value.first.return_value = None
        mocker.patch.object(
            UserDashboardLayout,
            "query",
            new_callable=mocker.PropertyMock,
            return_value=mock_q,
        )
        mock_session = mocker.patch("services.dashboard_service.db.session")

        layout_json = {"widgets": []}
        from services.dashboard_service import DashboardService

        with app.app_context():
            saved = DashboardService.save_user_layout(
                tenant_id=42, user_id=3, layout_json=layout_json
            )

        added = mock_session.add.call_args[0][0]
        assert added.tenant_id == 42
        assert added.user_id == 3
        assert saved.tenant_id == 42

    def test_widget_registry_empty_per_tenant_view(self, mocker):
        from models.dashboard import DashboardWidget

        mock_q = MagicMock()
        mock_q.filter_by.return_value.all.return_value = []
        mocker.patch.object(
            DashboardWidget,
            "query",
            new_callable=mocker.PropertyMock,
            return_value=mock_q,
        )

        from services.dashboard_service import DashboardService

        assert DashboardService.get_available_widgets(MagicMock()) == []


class TestLayoutPersistence:
    """save_user_layout — validation, update path, integrity rollback."""

    def test_rejects_empty_string_layout(self, app):
        from services.dashboard_service import DashboardService

        with app.app_context():
            with pytest.raises(ValueError, match="Invalid layout"):
                DashboardService.save_user_layout(1, 1, "")

    def test_update_existing_without_add(self, app, mocker):
        from models.dashboard import UserDashboardLayout

        existing = MagicMock()
        mock_q = MagicMock()
        mock_q.filter_by.return_value.first.return_value = existing
        mocker.patch.object(
            UserDashboardLayout,
            "query",
            new_callable=mocker.PropertyMock,
            return_value=mock_q,
        )
        mock_session = mocker.patch("services.dashboard_service.db.session")

        payload = {
            "widgets": [{"key": "cash_summary", "x": 0, "y": 0, "w": 12, "h": 1}]
        }
        from services.dashboard_service import DashboardService

        with app.app_context():
            result = DashboardService.save_user_layout(1, 2, payload)

        mock_session.add.assert_not_called()
        assert existing.layout_json == payload
        assert result is existing

    def test_integrity_error_rolls_back(self, app, mocker):
        from models.dashboard import UserDashboardLayout

        mock_q = MagicMock()
        mock_q.filter_by.return_value.first.return_value = MagicMock()
        mocker.patch.object(
            UserDashboardLayout,
            "query",
            new_callable=mocker.PropertyMock,
            return_value=mock_q,
        )
        mock_session = mocker.patch("services.dashboard_service.db.session")
        mock_session.flush.side_effect = IntegrityError("dup", {}, Exception())

        from services.dashboard_service import DashboardService

        with app.app_context():
            with pytest.raises(IntegrityError):
                DashboardService.save_user_layout(1, 1, {"widgets": []})


class TestWidgetCatalog:
    """get_available_widgets — enabled registry (permission filter TODO)."""

    def test_returns_only_enabled_widgets(self, mocker):
        from models.dashboard import DashboardWidget

        widgets = [MagicMock(widget_key="a"), MagicMock(widget_key="b")]
        mock_q = MagicMock()
        mock_q.filter_by.return_value.all.return_value = widgets
        mocker.patch.object(
            DashboardWidget,
            "query",
            new_callable=mocker.PropertyMock,
            return_value=mock_q,
        )

        from services.dashboard_service import DashboardService

        result = DashboardService.get_available_widgets(MagicMock())
        assert len(result) == 2
        mock_q.filter_by.assert_called_once_with(is_enabled=True)
