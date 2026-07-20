"""Unit tests for ai_knowledge/knowledge/tax_customs_knowledge.py — content integrity."""

from __future__ import annotations

from ai_knowledge.knowledge.tax_customs_knowledge import (
    CUSTOMS_UAE,
    EXPORT_PROCEDURES,
    IMPORT_PROCEDURES,
    PALESTINE_TAX,
    SAUDI_TAX,
    TAX_CUSTOMS_GUIDE,
    UAE_TAX_SYSTEM,
    get_customs_info,
    get_tax_info,
)


class TestKnowledgeContent:
    def test_guide_keys(self):
        assert set(TAX_CUSTOMS_GUIDE) == {
            "uae_vat",
            "uae_tax",  # alias of uae_vat — see TestGetTaxInfoUaeAlias
            "uae_customs",
            "saudi_tax",
            "palestine_tax",
            "import",
            "export",
        }

    def test_all_entries_non_empty_strings(self):
        for key, value in TAX_CUSTOMS_GUIDE.items():
            assert isinstance(value, str) and value.strip(), key

    def test_uae_vat_facts(self):
        assert "5%" in UAE_TAX_SYSTEM
        assert "375,000" in UAE_TAX_SYSTEM
        assert "2018" in UAE_TAX_SYSTEM
        assert "ضريبة القيمة المضافة" in UAE_TAX_SYSTEM

    def test_uae_customs_facts(self):
        assert "الجمارك" in CUSTOMS_UAE
        assert "5%" in CUSTOMS_UAE
        assert "الفاتورة التجارية" in CUSTOMS_UAE

    def test_saudi_vat_rate(self):
        assert "15%" in SAUDI_TAX

    def test_palestine_vat_rate(self):
        assert "16%" in PALESTINE_TAX

    def test_import_export_procedures_present(self):
        assert "قطع الغيار" in IMPORT_PROCEDURES
        assert "التصدير" in EXPORT_PROCEDURES


class TestGetTaxInfo:
    def test_saudi_lookup(self):
        assert get_tax_info("saudi") is TAX_CUSTOMS_GUIDE["saudi_tax"]

    def test_palestine_lookup(self):
        assert get_tax_info("palestine") is TAX_CUSTOMS_GUIDE["palestine_tax"]

    def test_lookup_is_case_insensitive(self):
        assert get_tax_info("SAUDI") == get_tax_info("saudi")

    def test_unknown_country_returns_fallback(self):
        assert get_tax_info("japan") == "معلومات غير متوفرة لهذه الدولة"

    def test_returns_string_for_any_input(self):
        assert isinstance(get_tax_info(""), str)


class TestGetCustomsInfo:
    def test_uae_lookup(self):
        assert get_customs_info("uae") is TAX_CUSTOMS_GUIDE["uae_customs"]

    def test_lookup_is_case_insensitive(self):
        assert get_customs_info("UAE") == get_customs_info("uae")

    def test_unknown_country_returns_fallback(self):
        assert get_customs_info("japan") == "معلومات غير متوفرة"


class TestGetTaxInfoUaeAlias:
    """Pin the uae_tax → uae_vat alias (regression: UAE tax showed 'unavailable')."""

    def test_uae_lookup_returns_vat_content(self):
        assert get_tax_info("uae") is TAX_CUSTOMS_GUIDE["uae_vat"]

    def test_uae_lookup_is_case_insensitive(self):
        assert get_tax_info("UAE") is TAX_CUSTOMS_GUIDE["uae_vat"]

    def test_uae_does_not_return_fallback(self):
        assert get_tax_info("uae") != "معلومات غير متوفرة لهذه الدولة"
