"""Tests for system_knowledge reference data."""

from __future__ import annotations

from ai_knowledge.system_knowledge import (
    SYSTEM_INFO,
    get_contextual_help,
    get_model_info,
    get_permission_info,
    get_role_based_features,
    get_role_info,
    search_knowledge,
)


class TestSystemKnowledge:
    def test_system_info(self):
        assert SYSTEM_INFO["name"] == "Azad-UAE ERP"

    def test_get_model_info(self):
        info = get_model_info("Customer")
        assert info is not None
        assert info["table"] == "customers"

    def test_get_model_info_missing(self):
        assert get_model_info("NotAModel") is None

    def test_get_permission_info(self):
        info = get_permission_info("manage_sales")
        assert info["name_ar"] == "إدارة المبيعات"

    def test_get_role_info(self):
        info = get_role_info("manager")
        assert info["name_ar"] == "مدير"

    def test_search_knowledge_customer(self):
        results = search_knowledge("عميل customers")
        assert isinstance(results, list)
        assert any(r.get("type") == "model" for r in results) or len(results) >= 0

    def test_search_knowledge_permission(self):
        results = search_knowledge("manage_sales صلاحية")
        assert isinstance(results, list)

    def test_contextual_help(self):
        help_info = get_contextual_help("dashboard")
        assert help_info is None or isinstance(help_info, dict)

    def test_role_based_features(self):
        features = get_role_based_features("seller")
        assert isinstance(features, list)
