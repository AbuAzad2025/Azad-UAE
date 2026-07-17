from __future__ import annotations

from types import SimpleNamespace

import pytest

from utils.username_policy import (
    PLATFORM_RESERVED,
    build_company_username,
    branch_key,
    is_platform_reserved,
    is_platform_user,
    normalize_username,
    parse_company_username,
    tenant_username_prefix,
    validate_username_for_user,
)


class TestNormalizeAndReserved:
    def test_normalize_username_strips_and_lowers(self):
        assert normalize_username("  Owner  ") == "owner"

    def test_normalize_empty(self):
        assert normalize_username(None) == ""

    def test_platform_reserved_membership(self):
        assert "owner" in PLATFORM_RESERVED
        assert is_platform_reserved("AZAD") is True
        assert is_platform_reserved("user1") is False


class TestTenantUsernamePrefix:
    def test_none_tenant_returns_empty(self):
        assert tenant_username_prefix(None) == ""

    def test_mapped_slug(self):
        tenant = SimpleNamespace(slug="alhazem")
        assert tenant_username_prefix(tenant) == "HZM"

    def test_legacy_alias_slug(self):
        tenant = SimpleNamespace(slug="alhazem-batteries")
        assert tenant_username_prefix(tenant) == "HZM"

    def test_t_prefix_slug(self):
        tenant = SimpleNamespace(slug="t-aed")
        assert tenant_username_prefix(tenant) == "AED"

    def test_t_prefix_derived(self):
        tenant = SimpleNamespace(slug="t-eur-west")
        assert tenant_username_prefix(tenant) == "EUR"

    def test_cleaned_slug_fallback(self):
        tenant = SimpleNamespace(slug="ab")
        assert tenant_username_prefix(tenant) == "TN"

    def test_three_char_cleaned(self):
        tenant = SimpleNamespace(slug="my-co")
        assert tenant_username_prefix(tenant) == "MYC"


class TestBranchKey:
    @pytest.mark.parametrize(
        "code,expected",
        [
            (None, "main"),
            ("", "main"),
            ("MAIN", "main"),
            ("HQ", "main"),
            ("BR-01", "01"),
            ("WAREHOUSE-NORTH", "warehouse_no"),
        ],
    )
    def test_branch_key(self, code, expected):
        assert branch_key(code) == expected


class TestBuildAndParseCompanyUsername:
    def test_build_company_username_success(self):
        tenant = SimpleNamespace(slug="default")
        assert build_company_username(tenant, "ahmad") == "DEF_ahmad"

    def test_build_without_prefix_raises(self):
        with pytest.raises(ValueError, match="تينانت"):
            build_company_username(None, "ahmad")

    def test_build_invalid_local_raises(self):
        tenant = SimpleNamespace(slug="default")
        with pytest.raises(ValueError, match="غير صالح"):
            build_company_username(tenant, "1bad")

    @pytest.mark.parametrize(
        "username,expected",
        [
            ("DEF_ahmad", ("DEF", "ahmad")),
            ("_bad", None),
            ("bad_", None),
            ("1X_user", None),
        ],
    )
    def test_parse_company_username(self, username, expected):
        assert parse_company_username(username) == expected


class TestValidateUsernameForUser:
    def test_empty_username(self):
        assert validate_username_for_user("") == "اسم المستخدم مطلوب."

    def test_invalid_pattern(self):
        assert "حروف وأرقام" in validate_username_for_user("ab")

    def test_owner_must_be_owner(self):
        assert validate_username_for_user("admin", is_owner=True) is not None
        assert validate_username_for_user("owner", is_owner=True) is None

    def test_platform_reserved_rejected(self):
        assert "محجوز" in validate_username_for_user("azad")

    def test_requires_tenant(self):
        assert "تينانت" in validate_username_for_user("DEF_ahmad", tenant=None)

    def test_wrong_prefix(self):
        tenant = SimpleNamespace(slug="default")
        msg = validate_username_for_user("ABC_ahmad", tenant=tenant)
        assert "DEF_" in msg

    def test_unprefixed_format_hint(self):
        tenant = SimpleNamespace(slug="default")
        msg = validate_username_for_user("plainuser", tenant=tenant)
        assert "DEF_" in msg

    def test_invalid_local_part(self):
        tenant = SimpleNamespace(slug="default")
        msg = validate_username_for_user("DEF_1bad", tenant=tenant)
        assert "جزء الاسم" in msg

    def test_valid_company_username(self):
        tenant = SimpleNamespace(slug="default")
        assert validate_username_for_user("DEF_ahmad", tenant=tenant) is None


class TestIsPlatformUser:
    def test_none_user(self):
        assert is_platform_user(None) is False

    def test_owner_flag(self):
        assert is_platform_user(SimpleNamespace(is_owner=True, username="x")) is True

    def test_reserved_username(self):
        assert (
            is_platform_user(SimpleNamespace(is_owner=False, username="azad")) is True
        )

    def test_regular_user(self):
        assert (
            is_platform_user(SimpleNamespace(is_owner=False, username="def_ahmad"))
            is False
        )
