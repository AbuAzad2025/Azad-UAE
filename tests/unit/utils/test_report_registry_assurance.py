"""Report registry — permission-filtered report catalog for navigation."""

from __future__ import annotations

from unittest.mock import MagicMock

from utils.report_registry import (
    REPORT_CATEGORIES,
    REPORT_REGISTRY,
    get_reports_by_category,
    get_visible_reports,
)


class TestReportRegistryData:
    def test_registry_entries_have_required_keys(self):
        for entry in REPORT_REGISTRY:
            assert entry["id"]
            assert entry["endpoint"]
            assert entry["category"]

    def test_categories_cover_registry(self):
        cat_ids = {c["id"] for c in REPORT_CATEGORIES}
        for entry in REPORT_REGISTRY:
            assert entry["category"] in cat_ids


class TestGetVisibleReports:
    def test_filters_by_permission(self):
        user = MagicMock()
        user.has_permission.side_effect = lambda perm: perm == "view_reports"
        visible = get_visible_reports(user)
        assert all(r["permission"] == "view_reports" for r in visible)
        assert len(visible) > 0

    def test_excludes_reports_without_permission(self):
        user = MagicMock()
        user.has_permission.return_value = False
        assert get_visible_reports(user) == []

    def test_user_without_has_permission_gets_nothing(self):
        assert get_visible_reports(object()) == []


class TestGetReportsByCategory:
    def test_groups_visible_reports(self):
        user = MagicMock()
        user.has_permission.return_value = True
        grouped = get_reports_by_category(user)
        assert isinstance(grouped, dict)
        for cat, reports in grouped.items():
            assert all(r["category"] == cat for r in reports)

    def test_empty_when_no_permissions(self):
        user = MagicMock()
        user.has_permission.return_value = False
        assert get_reports_by_category(user) == {}
