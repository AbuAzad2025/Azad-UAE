"""
Comprehensive Model Tests
Tests model imports, creation, string representation, fields, and relationships
using existing conftest fixtures.
"""
import pytest
from decimal import Decimal
from datetime import datetime, timezone, date


class TestModelImports:
    """Verify all key model classes can be imported from models/__init__.py."""

    def test_import_tenant(self):
        from models import Tenant
        assert Tenant is not None

    def test_import_user_role_permission(self):
        from models import User, Role, Permission
        assert User is not None
        assert Role is not None
        assert Permission is not None

    def test_import_branch(self):
        from models import Branch
        assert Branch is not None

    def test_import_customer(self):
        from models import Customer
        assert Customer is not None

    def test_import_supplier(self):
        from models import Supplier
        assert Supplier is not None

    def test_import_product_category(self):
        from models import Product, ProductCategory, ProductPartner
        assert Product is not None
        assert ProductCategory is not None
        assert ProductPartner is not None

    def test_import_warehouse_stock(self):
        from models import Warehouse, StockMovement, ProductWarehouseStock
        assert Warehouse is not None
        assert StockMovement is not None
        assert ProductWarehouseStock is not None

    def test_import_sale(self):
        from models import Sale, SaleLine
        assert Sale is not None
        assert SaleLine is not None

    def test_import_purchase(self):
        from models import Purchase, PurchaseLine
        assert Purchase is not None
        assert PurchaseLine is not None

    def test_import_expense(self):
        from models import Expense, ExpenseCategory
        assert Expense is not None
        assert ExpenseCategory is not None

    def test_import_cheque(self):
        from models import Cheque
        assert Cheque is not None

    def test_import_payroll(self):
        from models import Employee, PayrollTransaction, SalaryAdvance
        assert Employee is not None
        assert PayrollTransaction is not None
        assert SalaryAdvance is not None

    def test_import_invoice_settings(self):
        from models import InvoiceSettings
        assert InvoiceSettings is not None

    def test_import_print_history(self):
        from models import PrintHistory
        assert PrintHistory is not None

    def test_import_gl_models(self):
        from models import GLAccount, GLJournalEntry, GLJournalLine
        assert GLAccount is not None
        assert GLJournalEntry is not None
        assert GLJournalLine is not None

    def test_import_audit_log(self):
        from models import AuditLog
        assert AuditLog is not None


class TestTenantModel:
    """Tenant creation, __repr__, fields."""

    def test_tenant_created(self, sample_tenant):
        assert sample_tenant.id is not None
        assert sample_tenant.name.startswith("Test Company")

    def test_tenant_repr(self, sample_tenant):
        rep = repr(sample_tenant)
        assert rep.startswith("<Tenant ")
        assert sample_tenant.name in rep

    def test_tenant_fields(self, sample_tenant):
        assert hasattr(sample_tenant, "name")
        assert hasattr(sample_tenant, "name_ar")
        assert hasattr(sample_tenant, "slug")
        assert hasattr(sample_tenant, "email")
        assert hasattr(sample_tenant, "phone_1")
        assert hasattr(sample_tenant, "country")
        assert hasattr(sample_tenant, "subscription_plan")
        assert hasattr(sample_tenant, "is_active")
        assert hasattr(sample_tenant, "created_at")
        assert hasattr(sample_tenant, "updated_at")

    def test_tenant_fields_values(self, sample_tenant):
        assert sample_tenant.name_ar == "شركة تجربة"
        assert sample_tenant.country == "AE"
        assert sample_tenant.subscription_plan == "basic"
        assert sample_tenant.is_active is True

    def test_tenant_to_dict(self, sample_tenant):
        d = sample_tenant.to_dict()
        assert "name" in d
        assert "slug" in d
        assert d["name"] == sample_tenant.name

    def test_tenant_is_subscription_active(self, sample_tenant):
        assert sample_tenant.is_subscription_active() is True


class TestUserModel:
    """User creation, password, permissions, __repr__."""

    def test_user_created(self, sample_user):
        assert sample_user.id is not None
        assert sample_user.username.startswith("testuser")

    def test_user_repr(self, sample_user):
        rep = repr(sample_user)
        assert rep.startswith("<User ")
        assert sample_user.username in rep

    def test_user_fields(self, sample_user):
        assert hasattr(sample_user, "username")
        assert hasattr(sample_user, "email")
        assert hasattr(sample_user, "full_name")
        assert hasattr(sample_user, "tenant_id")
        assert hasattr(sample_user, "role_id")
        assert hasattr(sample_user, "branch_id")
        assert hasattr(sample_user, "is_active")
        assert hasattr(sample_user, "is_owner")
        assert hasattr(sample_user, "password_hash")

    def test_user_password_hashing(self, sample_user):
        assert sample_user.check_password("password123") is True
        assert sample_user.check_password("wrongpassword") is False

    def test_user_relationships(self, sample_user, sample_tenant, sample_role, sample_branch):
        assert sample_user.tenant_id == sample_tenant.id
        assert sample_user.role_id == sample_role.id
        assert sample_user.branch_id == sample_branch.id

    def test_user_has_permission(self, sample_user):
        assert sample_user.has_permission("admin") is True

    def test_user_is_admin(self, sample_user):
        assert sample_user.is_admin() is False
        assert sample_user.is_owner is False

    def test_user_get_display_name(self, sample_user):
        assert sample_user.get_display_name() == "Test User"
        assert sample_user.get_display_name("en") == "Test User"

    def test_user_set_password_updates_hash(self, db_session, sample_user):
        old_hash = sample_user.password_hash
        sample_user.set_password("newpassword")
        assert sample_user.password_hash != old_hash
        assert sample_user.check_password("newpassword") is True


class TestRoleModel:
    """Role creation, permission checks, __repr__."""

    def test_role_created(self, sample_role):
        assert sample_role.id is not None
        assert sample_role.name.startswith("Manager")

    def test_role_repr(self, sample_role):
        rep = repr(sample_role)
        assert rep.startswith("<Role ")
        assert sample_role.name in rep

    def test_role_fields(self, sample_role):
        assert hasattr(sample_role, "name")
        assert hasattr(sample_role, "slug")
        assert hasattr(sample_role, "is_active")
        assert hasattr(sample_role, "permissions")

    def test_role_has_permission(self, sample_role, sample_permissions):
        for p in sample_permissions:
            assert sample_role.has_permission(p.code) is True

    def test_role_missing_permission(self, sample_role):
        assert sample_role.has_permission("nonexistent") is False


class TestBranchModel:
    """Branch creation, __repr__, fields."""

    def test_branch_created(self, sample_branch):
        assert sample_branch.id is not None
        assert sample_branch.name.startswith("Main Branch")

    def test_branch_repr(self, sample_branch):
        rep = repr(sample_branch)
        assert rep.startswith("<Branch ")
        assert sample_branch.name in rep
        assert sample_branch.code in rep

    def test_branch_fields(self, sample_branch):
        assert hasattr(sample_branch, "name")
        assert hasattr(sample_branch, "code")
        assert hasattr(sample_branch, "tenant_id")
        assert hasattr(sample_branch, "is_active")
        assert hasattr(sample_branch, "is_main")
        assert hasattr(sample_branch, "created_at")

    def test_branch_scoped(self, sample_branch, sample_tenant):
        assert sample_branch.tenant_id == sample_tenant.id


class TestCustomerModel:
    """Customer creation, __repr__, fields."""

    def test_customer_created(self, sample_customer):
        assert sample_customer.id is not None

    def test_customer_repr(self, sample_customer):
        rep = repr(sample_customer)
        assert rep.startswith("<Customer ")
        assert sample_customer.name in rep

    def test_customer_fields(self, sample_customer):
        assert hasattr(sample_customer, "name")
        assert hasattr(sample_customer, "email")
        assert hasattr(sample_customer, "phone")
        assert hasattr(sample_customer, "tenant_id")
        assert hasattr(sample_customer, "balance")
        assert hasattr(sample_customer, "is_active")
        assert hasattr(sample_customer, "customer_type")

    def test_customer_defaults(self, sample_customer):
        assert sample_customer.is_active is True
        assert sample_customer.customer_type == "regular"
        assert sample_customer.balance == 0

    def test_customer_tenant_scoped(self, sample_customer, sample_tenant):
        assert sample_customer.tenant_id == sample_tenant.id

    def test_customer_balance_methods(self, sample_customer):
        sample_customer.apply_sale(Decimal("100"))
        assert sample_customer.balance == Decimal("-100")
        sample_customer.apply_receipt(Decimal("40"))
        assert sample_customer.balance == Decimal("-60")
        sample_customer.apply_return(Decimal("20"))
        assert sample_customer.balance == Decimal("-40")


class TestSupplierModel:
    """Supplier creation, __repr__, fields."""

    def test_supplier_created(self, sample_supplier):
        assert sample_supplier.id is not None

    def test_supplier_repr(self, sample_supplier):
        rep = repr(sample_supplier)
        assert rep.startswith("<Supplier ")
        assert sample_supplier.name in rep

    def test_supplier_fields(self, sample_supplier):
        assert hasattr(sample_supplier, "name")
        assert hasattr(sample_supplier, "email")
        assert hasattr(sample_supplier, "phone")
        assert hasattr(sample_supplier, "tenant_id")
        assert hasattr(sample_supplier, "is_active")
        assert hasattr(sample_supplier, "supplier_type")

    def test_supplier_defaults(self, sample_supplier):
        assert sample_supplier.is_active is True
        assert sample_supplier.supplier_type == "parts"
        assert sample_supplier.rating == 3

    def test_supplier_tenant_scoped(self, sample_supplier, sample_tenant):
        assert sample_supplier.tenant_id == sample_tenant.id

    def test_supplier_balance_methods(self, sample_supplier):
        sample_supplier.apply_purchase(Decimal("500"))
        assert sample_supplier.total_purchases_aed == Decimal("500")
        sample_supplier.apply_payment(Decimal("200"))
        assert sample_supplier.total_paid_aed == Decimal("200")
        assert sample_supplier.get_balance_base() == Decimal("300")


class TestProductModel:
    """Product creation, __repr__, fields."""

    def test_product_created(self, sample_product):
        assert sample_product.id is not None

    def test_product_repr(self, sample_product):
        rep = repr(sample_product)
        assert rep.startswith("<Product ")
        assert sample_product.name in rep

    def test_product_fields(self, sample_product):
        assert hasattr(sample_product, "name")
        assert hasattr(sample_product, "sku")
        assert hasattr(sample_product, "cost_price")
        assert hasattr(sample_product, "regular_price")
        assert hasattr(sample_product, "tenant_id")
        assert hasattr(sample_product, "current_stock")
        assert hasattr(sample_product, "is_active")
        assert hasattr(sample_product, "unit")

    def test_product_defaults(self, sample_product):
        assert sample_product.cost_price == Decimal("50.000")
        assert sample_product.regular_price == Decimal("100.000")
        assert sample_product.current_stock == Decimal("100.000")
        assert sample_product.is_active is True

    def test_product_tenant_scoped(self, sample_product, sample_tenant):
        assert sample_product.tenant_id == sample_tenant.id

    def test_product_aliases(self, sample_product):
        sample_product.current_stock = Decimal("10")
        assert sample_product.stock_quantity == 10
        assert sample_product.quantity_in_stock == 10


class TestSaleModel:
    """Sale creation, __repr__, relationships."""

    def test_sale_created(self, sample_sale):
        assert sample_sale.id is not None
        assert sample_sale.sale_number == "SAL-TEST-001"

    def test_sale_repr(self, sample_sale):
        rep = repr(sample_sale)
        assert rep.startswith("<Sale ")
        assert sample_sale.sale_number in rep

    def test_sale_fields(self, sample_sale):
        assert hasattr(sample_sale, "sale_number")
        assert hasattr(sample_sale, "customer_id")
        assert hasattr(sample_sale, "seller_id")
        assert hasattr(sample_sale, "sale_date")
        assert hasattr(sample_sale, "total_amount")
        assert hasattr(sample_sale, "amount")
        assert hasattr(sample_sale, "amount_aed")
        assert hasattr(sample_sale, "paid_amount")
        assert hasattr(sample_sale, "balance_due")
        assert hasattr(sample_sale, "payment_status")
        assert hasattr(sample_sale, "status")
        assert hasattr(sample_sale, "tenant_id")

    def test_sale_defaults(self, sample_sale):
        assert sample_sale.payment_status == "unpaid"
        assert sample_sale.status == "confirmed"
        assert sample_sale.currency == "AED"
        assert sample_sale.subtotal == Decimal("200.000")
        assert sample_sale.total_amount == Decimal("210.000")

    def test_sale_relationships(self, sample_sale, sample_customer, sample_user):
        assert sample_sale.customer_id == sample_customer.id
        assert sample_sale.seller_id == sample_user.id

    def test_sale_tenant_scoped(self, sample_sale, sample_tenant):
        assert sample_sale.tenant_id == sample_tenant.id

    def test_sale_payment_status_property(self, sample_sale):
        assert sample_sale.pending_cheques_amount == 0
        assert sample_sale.confirmed_payments_amount == Decimal("0")
        assert sample_sale.balance_due == Decimal("210.000")


class TestPurchaseModel:
    """Purchase creation, __repr__, fields."""

    def test_purchase_created(self, sample_purchase):
        assert sample_purchase.id is not None
        assert sample_purchase.purchase_number == "PUR-TEST-001"

    def test_purchase_repr(self, sample_purchase):
        rep = repr(sample_purchase)
        assert rep.startswith("<Purchase ")
        assert sample_purchase.purchase_number in rep

    def test_purchase_fields(self, sample_purchase):
        assert hasattr(sample_purchase, "purchase_number")
        assert hasattr(sample_purchase, "supplier_id")
        assert hasattr(sample_purchase, "supplier_name")
        assert hasattr(sample_purchase, "purchase_date")
        assert hasattr(sample_purchase, "subtotal")
        assert hasattr(sample_purchase, "total_amount")
        assert hasattr(sample_purchase, "amount")
        assert hasattr(sample_purchase, "amount_aed")
        assert hasattr(sample_purchase, "status")
        assert hasattr(sample_purchase, "user_id")
        assert hasattr(sample_purchase, "tenant_id")

    def test_purchase_defaults(self, sample_purchase):
        assert sample_purchase.status == "confirmed"
        assert sample_purchase.currency == "AED"
        assert sample_purchase.subtotal == Decimal("100.000")
        assert sample_purchase.total_amount == Decimal("105.000")

    def test_purchase_relationships(self, sample_purchase, sample_supplier):
        assert sample_purchase.supplier_id == sample_supplier.id

    def test_purchase_tenant_scoped(self, sample_purchase, sample_tenant):
        assert sample_purchase.tenant_id == sample_tenant.id

    def test_purchase_landed_cost(self, sample_purchase):
        assert sample_purchase.freight == 0
        assert sample_purchase.total_landed_cost == 0


class TestExpenseModel:
    """Expense creation, __repr__, fields."""

    def test_expense_created(self, sample_expense):
        assert sample_expense.id is not None
        assert sample_expense.expense_number == "EXP-TEST-001"

    def test_expense_repr(self, sample_expense):
        rep = repr(sample_expense)
        assert rep.startswith("<Expense ")
        assert sample_expense.expense_number in rep

    def test_expense_fields(self, sample_expense):
        assert hasattr(sample_expense, "expense_number")
        assert hasattr(sample_expense, "category_id")
        assert hasattr(sample_expense, "description")
        assert hasattr(sample_expense, "amount")
        assert hasattr(sample_expense, "amount_aed")
        assert hasattr(sample_expense, "expense_date")
        assert hasattr(sample_expense, "user_id")
        assert hasattr(sample_expense, "tenant_id")
        assert hasattr(sample_expense, "status")

    def test_expense_defaults(self, sample_expense):
        assert sample_expense.amount == Decimal("500.000")
        assert sample_expense.amount_aed == Decimal("500.000")
        assert sample_expense.description == "Test expense"

    def test_expense_relationship(self, sample_expense, sample_expense_category):
        assert sample_expense.category_id == sample_expense_category.id

    def test_expense_tenant_scoped(self, sample_expense, sample_tenant):
        assert sample_expense.tenant_id == sample_tenant.id

    def test_expense_category_repr(self, sample_expense_category):
        rep = repr(sample_expense_category)
        assert rep.startswith("<ExpenseCategory ")
        assert sample_expense_category.name in rep


class TestChequeModel:
    """Cheque creation, status, type, __repr__."""

    def test_cheque_created(self, sample_cheque):
        assert sample_cheque.id is not None
        assert sample_cheque.cheque_number == "CHQ-TEST-001"

    def test_cheque_repr(self, sample_cheque):
        rep = repr(sample_cheque)
        assert rep.startswith("<Cheque ")
        assert sample_cheque.cheque_number in rep
        assert sample_cheque.cheque_type in rep
        assert sample_cheque.status in rep

    def test_cheque_fields(self, sample_cheque):
        assert hasattr(sample_cheque, "cheque_number")
        assert hasattr(sample_cheque, "cheque_bank_number")
        assert hasattr(sample_cheque, "cheque_type")
        assert hasattr(sample_cheque, "bank_name")
        assert hasattr(sample_cheque, "amount")
        assert hasattr(sample_cheque, "amount_aed")
        assert hasattr(sample_cheque, "issue_date")
        assert hasattr(sample_cheque, "due_date")
        assert hasattr(sample_cheque, "status")
        assert hasattr(sample_cheque, "tenant_id")

    def test_cheque_defaults(self, sample_cheque):
        assert sample_cheque.cheque_type == "incoming"
        assert sample_cheque.status == "pending"
        assert sample_cheque.is_active is True
        assert sample_cheque.amount == Decimal("10000.00")

    def test_cheque_type_ar(self, sample_cheque):
        assert sample_cheque.cheque_type_ar == "وارد"

    def test_cheque_status_properties(self, sample_cheque):
        assert sample_cheque.is_pending is True
        assert sample_cheque.is_confirmed is False

    def test_cheque_archive_restore(self, sample_cheque):
        sample_cheque.archive(reason="test archive")
        assert sample_cheque.is_active is False
        assert sample_cheque.archive_reason == "test archive"
        sample_cheque.restore()
        assert sample_cheque.is_active is True
        assert sample_cheque.archive_reason is None

    def test_cheque_tenant_scoped(self, sample_cheque, sample_tenant):
        assert sample_cheque.tenant_id == sample_tenant.id

    def test_cheque_status_update(self, sample_cheque):
        assert sample_cheque.days_until_due is None
        sample_cheque.update_status_based_on_date()
        assert sample_cheque.days_until_due is not None


class TestInvoiceSettings:
    """InvoiceSettings get_active and creation."""

    def test_invoice_settings_create(self, db_session, sample_tenant):
        from models import InvoiceSettings
        inv = InvoiceSettings(
            tenant_id=sample_tenant.id,
            company_name_ar="شركة تجربة",
            company_name_en="Test Company",
        )
        db_session.add(inv)
        db_session.commit()
        assert inv.id is not None
        assert inv.tenant_id == sample_tenant.id

    def test_invoice_settings_repr(self, db_session, sample_tenant):
        from models import InvoiceSettings
        inv = InvoiceSettings(
            tenant_id=sample_tenant.id,
            company_name_ar="شركة أزاد",
        )
        db_session.add(inv)
        db_session.commit()
        rep = repr(inv)
        assert "<InvoiceSettings " in rep
        assert "شركة أزاد" in rep

    def test_invoice_settings_get_active(self, db_session, sample_tenant):
        from models import InvoiceSettings
        settings = InvoiceSettings.get_active(tenant_id=sample_tenant.id)
        assert settings is not None
        assert settings.tenant_id == sample_tenant.id
        assert settings.company_name_ar is not None

    def test_invoice_settings_get_active_creates_on_demand(self, db_session, sample_tenant):
        from models import InvoiceSettings
        existing = InvoiceSettings.query.filter_by(tenant_id=sample_tenant.id).all()
        for e in existing:
            db_session.delete(e)
        db_session.commit()
        settings = InvoiceSettings.get_active(tenant_id=sample_tenant.id)
        assert settings is not None
        assert settings.tenant_id == sample_tenant.id


class TestPrintHistory:
    """PrintHistory creation and audit fields."""

    def test_print_history_create(self, db_session, sample_tenant, sample_user):
        from models import PrintHistory
        ph = PrintHistory(
            tenant_id=sample_tenant.id,
            user_id=sample_user.id,
            document_type="sale",
            document_id=1,
            action="print",
            ip_address="127.0.0.1",
        )
        db_session.add(ph)
        db_session.commit()
        assert ph.id is not None
        assert ph.tenant_id == sample_tenant.id

    def test_print_history_repr(self, db_session, sample_tenant):
        from models import PrintHistory
        ph = PrintHistory(
            tenant_id=sample_tenant.id,
            document_type="sale",
            document_id=42,
            action="print",
        )
        rep = repr(ph)
        assert "<PrintHistory " in rep
        assert "sale#42" in rep
        assert "print" in rep

    def test_print_history_fields(self, db_session, sample_tenant, sample_user):
        from models import PrintHistory
        ph = PrintHistory(
            tenant_id=sample_tenant.id,
            user_id=sample_user.id,
            document_type="purchase",
            document_id=99,
            action="view",
            ip_address="192.168.1.1",
        )
        db_session.add(ph)
        db_session.commit()
        assert ph.document_type == "purchase"
        assert ph.document_id == 99
        assert ph.action == "view"
        assert ph.ip_address == "192.168.1.1"

    def test_print_history_meta_json(self, db_session, sample_tenant):
        from models import PrintHistory
        ph = PrintHistory(
            tenant_id=sample_tenant.id,
            document_type="sale",
            document_id=1,
        )
        ph.meta = {"copies": 2, "format": "A4"}
        db_session.add(ph)
        db_session.commit()
        assert ph.meta == {"copies": 2, "format": "A4"}

    def test_print_history_tenant_scoped(self, db_session, sample_tenant):
        from models import PrintHistory
        ph = PrintHistory(
            tenant_id=sample_tenant.id,
            document_type="sale",
            document_id=1,
        )
        db_session.add(ph)
        db_session.commit()
        assert ph.tenant_id == sample_tenant.id
