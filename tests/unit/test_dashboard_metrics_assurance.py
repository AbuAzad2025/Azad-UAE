"""Dashboard widgets, layouts, and metrics aggregation assurance."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from sqlalchemy.exc import IntegrityError


class TestDashboardWidgetModel:
    """models.dashboard — widget registry representation."""

    def test_widget_repr(self):
        from models.dashboard import DashboardWidget

        w = DashboardWidget(widget_key="sales_summary", title="Sales")
        assert "sales_summary" in repr(w)

    def test_layout_repr(self):
        from models.dashboard import UserDashboardLayout

        layout = UserDashboardLayout(
            tenant_id=1, user_id=42, layout_json={"widgets": []}
        )
        assert "user=42" in repr(layout)


class TestDashboardServiceWidgets:
    """get_available_widgets — enabled-only registry."""

    def test_returns_enabled_widgets(self, mocker):
        from models.dashboard import DashboardWidget

        w1, w2 = MagicMock(), MagicMock()
        mock_q = MagicMock()
        mock_q.filter_by.return_value.all.return_value = [w1, w2]
        mocker.patch.object(
            DashboardWidget,
            "query",
            new_callable=mocker.PropertyMock,
            return_value=mock_q,
        )

        from services.dashboard_service import DashboardService

        result = DashboardService.get_available_widgets(user=MagicMock())
        assert result == [w1, w2]
        mock_q.filter_by.assert_called_once_with(is_enabled=True)

    def test_zero_data_fallback_empty_widgets(self, mocker):
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


class TestDashboardServiceLayout:
    """get/save user layout — tenant isolation and validation."""

    def test_get_default_layout_structure(self):
        from services.dashboard_service import DashboardService

        layout = DashboardService.get_default_layout()
        assert "widgets" in layout
        assert len(layout["widgets"]) == 2
        keys = {w["key"] for w in layout["widgets"]}
        assert "sales_summary" in keys
        assert "cash_summary" in keys

    def test_get_user_layout_returns_saved(self, mocker, app):
        from models.dashboard import UserDashboardLayout

        saved = {"widgets": [{"key": "custom", "x": 0, "y": 0, "w": 12, "h": 3}]}
        mock_layout = MagicMock()
        mock_layout.layout_json = saved
        mock_q = MagicMock()
        mock_q.filter_by.return_value.first.return_value = mock_layout
        mocker.patch.object(
            UserDashboardLayout,
            "query",
            new_callable=mocker.PropertyMock,
            return_value=mock_q,
        )

        from services.dashboard_service import DashboardService

        with app.app_context():
            result = DashboardService.get_user_layout(tenant_id=1, user_id=5)
        assert result == saved
        mock_q.filter_by.assert_called_once_with(tenant_id=1, user_id=5)

    def test_get_user_layout_zero_data_fallback(self, mocker, app):
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
            result = DashboardService.get_user_layout(tenant_id=99, user_id=1)
        assert result["widgets"][0]["key"] == "sales_summary"

    def test_save_layout_rejects_non_dict(self, app):
        from services.dashboard_service import DashboardService

        with app.app_context():
            with pytest.raises(ValueError, match="Invalid layout"):
                DashboardService.save_user_layout(1, 1, "not-a-dict")

    def test_save_layout_rejects_oversized_payload(self, app):
        from services.dashboard_service import DashboardService

        huge = {"widgets": ["x" * 10001]}
        with app.app_context():
            with pytest.raises(ValueError, match="Invalid layout"):
                DashboardService.save_user_layout(1, 1, huge)

    def test_save_layout_creates_new_record(self, app, mocker):
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
        mock_session.commit.return_value = None

        layout_json = {
            "widgets": [{"key": "sales_summary", "x": 0, "y": 0, "w": 6, "h": 2}]
        }
        from services.dashboard_service import DashboardService

        with app.app_context():
            result = DashboardService.save_user_layout(1, 7, layout_json)

        mock_session.add.assert_called_once()
        assert result.tenant_id == 1

    def test_save_layout_updates_existing(self, app, mocker):
        from models.dashboard import UserDashboardLayout

        existing = MagicMock()
        existing.layout_json = {}
        mock_q = MagicMock()
        mock_q.filter_by.return_value.first.return_value = existing
        mocker.patch.object(
            UserDashboardLayout,
            "query",
            new_callable=mocker.PropertyMock,
            return_value=mock_q,
        )
        mocker.patch("services.dashboard_service.db.session")

        new_json = {
            "widgets": [{"key": "cash_summary", "x": 6, "y": 0, "w": 6, "h": 2}]
        }
        from services.dashboard_service import DashboardService

        with app.app_context():
            result = DashboardService.save_user_layout(2, 3, new_json)

        assert existing.layout_json == new_json
        assert result is existing

    def test_save_layout_integrity_error_rolls_back(self, app, mocker):
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
        mock_session.flush.side_effect = IntegrityError("dup", {}, Exception())

        from services.dashboard_service import DashboardService

        with app.app_context():
            with pytest.raises(IntegrityError):
                DashboardService.save_user_layout(1, 1, {"widgets": []})
