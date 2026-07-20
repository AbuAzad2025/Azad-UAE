"""Unit tests for models/enums.py — RoleEnum and PermissionEnum contracts.

These enums are the canonical RBAC source of truth: role slugs and permission
codes must map 1:1 to DB values, so membership, values, and helper semantics
are pinned here. Pure-python tests — no app context or DB needed.
"""

from models.enums import PermissionEnum, RoleEnum


class TestRoleEnumMembership:
    EXPECTED_VALUES = {
        "owner",
        "developer",
        "super_admin",
        "manager",
        "branch_manager",
        "accountant",
        "seller",
        "cashier",
    }

    def test_member_count_and_values_are_unique(self):
        values = [r.value for r in RoleEnum]
        assert len(RoleEnum) == 8
        assert len(set(values)) == len(values)
        assert set(values) == self.EXPECTED_VALUES

    def test_members_are_str_instances(self):
        for role in RoleEnum:
            assert isinstance(role, str)
            assert role == role.value

    def test_lookup_by_value_round_trips(self):
        for role in RoleEnum:
            assert RoleEnum(role.value) is role

    def test_named_member_values(self):
        assert RoleEnum.OWNER.value == "owner"
        assert RoleEnum.SUPER_ADMIN.value == "super_admin"
        assert RoleEnum.BRANCH_MANAGER.value == "branch_manager"
        assert RoleEnum.CASHIER.value == "cashier"


class TestRoleEnumScopeHelpers:
    def test_global_scope(self):
        scope = RoleEnum.global_scope()
        assert isinstance(scope, frozenset)
        assert scope == {RoleEnum.OWNER, RoleEnum.DEVELOPER, RoleEnum.SUPER_ADMIN}

    def test_company_admin(self):
        admins = RoleEnum.company_admin()
        assert isinstance(admins, frozenset)
        assert admins == {RoleEnum.SUPER_ADMIN, RoleEnum.MANAGER}

    def test_financial(self):
        fin = RoleEnum.financial()
        assert isinstance(fin, frozenset)
        assert fin == {
            RoleEnum.OWNER,
            RoleEnum.DEVELOPER,
            RoleEnum.SUPER_ADMIN,
            RoleEnum.ACCOUNTANT,
            RoleEnum.BRANCH_MANAGER,
        }

    def test_restricted_pricing(self):
        restricted = RoleEnum.restricted_pricing()
        assert isinstance(restricted, frozenset)
        assert restricted == {RoleEnum.SELLER, RoleEnum.CASHIER}

    def test_values_helpers_return_string_tuples(self):
        for helper in (
            RoleEnum.global_scope_values,
            RoleEnum.company_admin_values,
            RoleEnum.financial_values,
            RoleEnum.restricted_pricing_values,
        ):
            values = helper()
            assert isinstance(values, tuple)
            assert all(isinstance(v, str) for v in values)

    def test_values_helpers_match_member_sets(self):
        assert set(RoleEnum.global_scope_values()) == {
            "owner",
            "developer",
            "super_admin",
        }
        assert set(RoleEnum.company_admin_values()) == {"super_admin", "manager"}
        assert set(RoleEnum.financial_values()) == {
            "owner",
            "developer",
            "super_admin",
            "accountant",
            "branch_manager",
        }
        assert set(RoleEnum.restricted_pricing_values()) == {"seller", "cashier"}

    def test_restricted_pricing_never_overlaps_privileged_scopes(self):
        restricted = RoleEnum.restricted_pricing()
        assert restricted.isdisjoint(RoleEnum.global_scope())
        assert restricted.isdisjoint(RoleEnum.company_admin())
        assert restricted.isdisjoint(RoleEnum.financial())


class TestPermissionEnumMembership:
    def test_member_count_and_values_are_unique(self):
        values = [p.value for p in PermissionEnum]
        assert len(PermissionEnum) == 29
        assert len(set(values)) == len(values)

    def test_members_are_str_instances(self):
        for perm in PermissionEnum:
            assert isinstance(perm, str)
            assert perm == perm.value

    def test_named_member_values(self):
        assert PermissionEnum.MANAGE_SALES.value == "manage_sales"
        assert PermissionEnum.ADMIN.value == "admin"
        assert PermissionEnum.CRM_VIEW.value == "crm.view"
        assert PermissionEnum.CRM_MANAGE.value == "crm.manage"
        assert PermissionEnum.OVERRIDE_SALE_PRICE.value == "override_sale_price"

    def test_lookup_by_value_round_trips(self):
        for perm in PermissionEnum:
            assert PermissionEnum(perm.value) is perm


class TestPermissionEnumFromCode:
    def test_from_code_resolves_known_codes(self):
        assert PermissionEnum.from_code("manage_sales") is PermissionEnum.MANAGE_SALES
        assert PermissionEnum.from_code("crm.view") is PermissionEnum.CRM_VIEW
        assert PermissionEnum.from_code("admin") is PermissionEnum.ADMIN

    def test_from_code_round_trips_every_member(self):
        for perm in PermissionEnum:
            assert PermissionEnum.from_code(perm.value) is perm

    def test_from_code_unknown_returns_none(self):
        assert PermissionEnum.from_code("no.such.permission") is None
        assert PermissionEnum.from_code("MANAGE_SALES") is None

    def test_from_code_empty_and_none_return_none(self):
        assert PermissionEnum.from_code("") is None
        assert PermissionEnum.from_code(None) is None
