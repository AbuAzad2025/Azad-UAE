"""Unit tests for ai_knowledge/specialized/system_guide.py — content integrity."""

from __future__ import annotations

from ai_knowledge.specialized.system_guide import (
    SYSTEM_TERMS,
    USER_GUIDE,
    get_system_guide,
)


class TestSystemTerms:
    def test_categories(self):
        assert set(SYSTEM_TERMS) == {"sales", "customers", "inventory", "accounting"}

    def test_all_terms_are_non_empty_strings(self):
        for category, terms in SYSTEM_TERMS.items():
            assert terms, category
            for key, arabic in terms.items():
                assert isinstance(key, str) and key, category
                assert isinstance(arabic, str) and arabic.strip(), f"{category}.{key}"

    def test_core_sales_terms(self):
        sales = SYSTEM_TERMS["sales"]
        assert sales["invoice"] == "فاتورة"
        assert sales["tax"] == "ضريبة"
        assert sales["payment_method"] == "طريقة الدفع"

    def test_core_accounting_terms(self):
        accounting = SYSTEM_TERMS["accounting"]
        assert accounting["debit"] == "مدين"
        assert accounting["credit"] == "دائن"
        assert accounting["profit"] == "ربح"


class TestUserGuide:
    def test_sections(self):
        assert set(USER_GUIDE) == {
            "getting_started",
            "sales_process",
            "warehouse_management",
            "reports",
        }

    def test_step_counts(self):
        assert len(USER_GUIDE["getting_started"]) == 5
        assert len(USER_GUIDE["sales_process"]) == 8
        assert len(USER_GUIDE["warehouse_management"]) == 7
        assert len(USER_GUIDE["reports"]) == 6

    def test_all_steps_non_empty(self):
        for section, steps in USER_GUIDE.items():
            assert all(isinstance(s, str) and s.strip() for s in steps), section


class TestGetSystemGuide:
    def test_returns_quick_guide_header(self):
        text = get_system_guide()
        assert isinstance(text, str)
        assert "دليل الاستخدام السريع" in text

    def test_includes_all_getting_started_steps(self):
        text = get_system_guide()
        for step in USER_GUIDE["getting_started"]:
            assert step in text

    def test_includes_first_five_sales_steps_only(self):
        # The guide deliberately slices sales_process[:5].
        text = get_system_guide()
        for step in USER_GUIDE["sales_process"][:5]:
            assert step in text
        for step in USER_GUIDE["sales_process"][5:]:
            assert step not in text
