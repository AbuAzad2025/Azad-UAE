"""Canonical security enums for RBAC — single source of truth for roles and permissions.

Role slugs map 1:1 to existing DB values (models/roles.slug column).
Permission codes map 1:1 to existing DB values (permissions.code column).
All string comparisons throughout the codebase MUST reference these enum members
instead of bare string literals.
"""

from enum import Enum


class RoleEnum(str, Enum):
    OWNER = "owner"
    DEVELOPER = "developer"
    SUPER_ADMIN = "super_admin"
    MANAGER = "manager"
    BRANCH_MANAGER = "branch_manager"
    ACCOUNTANT = "accountant"
    SELLER = "seller"
    CASHIER = "cashier"

    @classmethod
    def global_scope(cls):
        """Roles that operate across all tenants (platform-level)."""
        return frozenset({cls.OWNER, cls.DEVELOPER, cls.SUPER_ADMIN})

    @classmethod
    def company_admin(cls):
        """Roles that can administer a single tenant."""
        return frozenset({cls.SUPER_ADMIN, cls.MANAGER})

    @classmethod
    def company_admin_values(cls):
        """String values of company-admin roles for DB-slug comparisons."""
        return tuple(r.value for r in cls.company_admin())

    @classmethod
    def financial(cls):
        """Roles with access to financial / accounting surfaces."""
        return frozenset(
            {
                cls.OWNER,
                cls.DEVELOPER,
                cls.SUPER_ADMIN,
                cls.ACCOUNTANT,
                cls.BRANCH_MANAGER,
            }
        )

    @classmethod
    def financial_values(cls):
        """String values of financial roles for DB-slug comparisons."""
        return tuple(r.value for r in cls.financial())

    @classmethod
    def global_scope_values(cls):
        """String values of global-scope roles for DB-slug comparisons."""
        return tuple(r.value for r in cls.global_scope())

    @classmethod
    def restricted_pricing(cls):
        """Roles that CANNOT override prices or apply discounts."""
        return frozenset({cls.SELLER, cls.CASHIER})

    @classmethod
    def restricted_pricing_values(cls):
        """String values of restricted-pricing roles for DB-slug comparisons."""
        return tuple(r.value for r in cls.restricted_pricing())


class PermissionEnum(str, Enum):
    MANAGE_SALES = "manage_sales"
    MANAGE_PURCHASES = "manage_purchases"
    MANAGE_PRODUCTS = "manage_products"
    MANAGE_CUSTOMERS = "manage_customers"
    MANAGE_SUPPLIERS = "manage_suppliers"
    MANAGE_PAYMENTS = "manage_payments"
    MANAGE_EXPENSES = "manage_expenses"
    VIEW_REPORTS = "view_reports"
    MANAGE_WAREHOUSE = "manage_warehouse"
    MANAGE_STORE = "manage_store"
    VIEW_LEDGER = "view_ledger"
    MANAGE_LEDGER = "manage_ledger"
    ADMIN = "admin"
    MANAGE_USERS = "manage_users"
    MANAGE_BACKUPS = "manage_backups"
    MANAGE_PAYROLL = "manage_payroll"
    CRM_VIEW = "crm.view"
    CRM_MANAGE = "crm.manage"
    SUPPORT_VIEW = "support.view"
    SUPPORT_MANAGE = "support.manage"
    PROJECT_VIEW = "project.view"
    PROJECT_MANAGE = "project.manage"
    HR_VIEW = "hr.view"
    HR_MANAGE = "hr.manage"
    MARKETING_MANAGE = "marketing.manage"
    PRINTING_PRINT = "printing.print"
    PRINTING_SETTINGS = "printing.settings"
    VIEW_KDS = "view_kds"
    OVERRIDE_SALE_PRICE = "override_sale_price"

    @classmethod
    def from_code(cls, code: str):
        """Resolve a raw permission-code string to a PermissionEnum member, or None."""
        if not code:
            return None
        try:
            return cls(code)
        except ValueError:
            return None
