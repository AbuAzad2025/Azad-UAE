"""Gap coverage for models/gl_account_registry.py — pure config validation."""

from __future__ import annotations

import pytest

from models.gl_account_registry import (
    ACCOUNT_TYPE_BY_ROOT,
    BASE_ACCOUNTS,
    GL_MODULE_DEFINITIONS,
    INDUSTRY_EXTENSIONS,
    PROTECTED_ACCOUNT_CODES,
    VALID_INDUSTRY_CODES,
    validate_account_code_type,
)


class TestValidateAccountCodeType:
    def test_none_code(self):
        assert validate_account_code_type(None, "asset") is False

    def test_empty_code(self):
        assert validate_account_code_type("", "asset") is False

    def test_non_digit_root(self):
        assert validate_account_code_type("X100", "asset") is False

    def test_unknown_root(self):
        assert validate_account_code_type("9100", "asset") is False

    def test_asset_match(self):
        assert validate_account_code_type("1130", "asset") is True

    def test_asset_mismatch(self):
        assert validate_account_code_type("1130", "liability") is False

    def test_expense_roots_five_and_six(self):
        assert validate_account_code_type("5100", "expense") is True
        assert validate_account_code_type("6100", "expense") is True

    def test_liability_equity_revenue(self):
        assert validate_account_code_type("2110", "liability") is True
        assert validate_account_code_type("3100", "equity") is True
        assert validate_account_code_type("4100", "revenue") is True


class TestRegistryContents:
    def test_base_accounts_nonempty(self):
        assert len(BASE_ACCOUNTS) > 50

    def test_contra_flags_present(self):
        codes = {a.code: a for a in BASE_ACCOUNTS}
        assert codes["1190"].is_contra is True
        assert codes["3300"].is_contra is True
        assert codes["5201"].is_contra is True
        assert codes["1111"].is_contra is False

    def test_vat_input_is_asset(self):
        codes = {a.code: a for a in BASE_ACCOUNTS}
        assert codes["2122"].type == "asset"

    def test_suspense_account_exists(self):
        assert any(a.code == "2999" for a in BASE_ACCOUNTS)

    def test_protected_codes(self):
        assert "1130" in PROTECTED_ACCOUNT_CODES
        assert "3200" in PROTECTED_ACCOUNT_CODES

    def test_industry_codes_include_general(self):
        assert "general" in VALID_INDUSTRY_CODES
        assert set(INDUSTRY_EXTENSIONS) <= VALID_INDUSTRY_CODES

    def test_module_definitions_core(self):
        assert "core_sales" in GL_MODULE_DEFINITIONS
        assert GL_MODULE_DEFINITIONS["core_sales"].required is True
        assert GL_MODULE_DEFINITIONS["shop_online"].required is False

    def test_root_map(self):
        assert ACCOUNT_TYPE_BY_ROOT["1"] == "asset"
        assert ACCOUNT_TYPE_BY_ROOT["6"] == "expense"

    @pytest.mark.parametrize("code", ["1130", "2110", "4100", "5100"])
    def test_known_codes_validate(self, code):
        from models.gl_account_registry import BASE_ACCOUNTS as _base

        tpl = next(a for a in _base if a.code == code)
        assert validate_account_code_type(code, tpl.type) is True

    def test_vat_input_root_mismatch_is_known_exception(self):
        # 2122 (VAT Input) is deliberately typed "asset" under root 2 —
        # the digit-root check does not cover this intentional exception.
        assert validate_account_code_type("2122", "asset") is False
