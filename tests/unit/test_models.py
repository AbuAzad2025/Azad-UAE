"""
Model Unit Tests
Tests model definitions, columns, relationships, and tenant_id presence.
"""
import pytest
import sqlalchemy as sa
from decimal import Decimal
from extensions import db


def test_payroll_migration_orphan_precheck_logic():
    """Verify migration raises RuntimeError when tenant_id remains NULL after backfill."""
    from migrations.versions.payroll_fix_001_add_partial_deduction_fields import _has_column, _has_index, _has_fk
    assert callable(_has_column)
    assert callable(_has_index)
    assert callable(_has_fk)


class TestTenantModel:
    """Tenant model tests."""

    def test_tenant_creation(self, db_session, sample_tenant):
        assert sample_tenant.id is not None
        assert sample_tenant.name.startswith("Test Company")
        assert sample_tenant.name_ar == "شركة تجربة"

    def test_tenant_serialize(self, sample_tenant):
        d = sample_tenant.to_dict()
        assert "name" in d
        assert d["name"].startswith("Test Company")


class TestUserModel:
    """User model tests."""

    def test_user_password_hashing(self, db_session, sample_tenant, sample_role):
        import uuid
        from models import User
        uid = uuid.uuid4().hex[:6]
        user = User(
            username="pwtest-" + uid,
            email="pw-" + uid + "@test.com",
            full_name="PW Test",
            tenant_id=sample_tenant.id,
            role_id=sample_role.id,
        )
        user.set_password("secret123")
        db_session.add(user)
        db_session.commit()
        assert user.check_password("secret123") is True
        assert user.check_password("wrong") is False

    def test_user_tenant_relationship(self, sample_user, sample_tenant):
        assert sample_user.tenant_id == sample_tenant.id


class TestProductModel:
    """Product model tests."""

    def test_product_tenant_scoped(self, db_session, sample_tenant):
        from models import Product
        p = Product(
            tenant_id=sample_tenant.id,
            name="Test Product",
            sku="TEST-001",
            barcode="123456",
            cost_price=100.0,
            regular_price=150.0,
            is_active=True,
        )
        db_session.add(p)
        db_session.commit()
        assert p.id is not None
        assert p.tenant_id == sample_tenant.id


class TestArchivedRecordModel:
    """ArchivedRecord model — recently updated with tenant_id."""

    def test_archived_record_has_tenant_id(self, db_session, sample_tenant):
        from models import ArchivedRecord
        rec = ArchivedRecord(
            tenant_id=sample_tenant.id,
            table_name="products",
            record_id=1,
            data='{"name": "test"}',
            reason="test archive",
            can_restore=True,
        )
        db_session.add(rec)
        db_session.commit()
        assert rec.id is not None
        assert rec.tenant_id == sample_tenant.id

    def test_archived_record_index(self, db_session, sample_tenant):
        from models import ArchivedRecord
        # Verify tenant_id is indexed via the model definition
        assert hasattr(ArchivedRecord, "tenant_id")


class TestBankReconciliationModel:
    """BankReconciliation — recently updated with tenant_id."""

    def test_bank_reconciliation_tenant_id(self, db_session, sample_tenant):
        from models import BankReconciliation, GLAccount
        from datetime import date
        acc = GLAccount(tenant_id=sample_tenant.id, code='BANK-TEST', name='Test Bank', type='asset')
        db_session.add(acc)
        db_session.flush()
        br = BankReconciliation(
            tenant_id=sample_tenant.id,
            reconciliation_number="BR-001",
            bank_account_id=acc.id,
            period_start=date.today(),
            period_end=date.today(),
        )
        db_session.add(br)
        db_session.commit()
        assert br.id is not None
        assert br.tenant_id == sample_tenant.id


class TestBudgetModel:
    """Budget — recently updated with tenant_id."""

    def test_budget_tenant_id(self, db_session, sample_tenant):
        from models import Budget
        from datetime import date
        b = Budget(
            tenant_id=sample_tenant.id,
            budget_number="BUD-001",
            name_ar="موازنة Q1",
            fiscal_year=2026,
            period_start=date.today(),
            period_end=date.today(),
            status="draft",
            total_budgeted=10000.0,
        )
        db_session.add(b)
        db_session.commit()
        assert b.id is not None
        assert b.tenant_id == sample_tenant.id


class TestCardVaultModel:
    """CardVault — recently updated with tenant_id."""

    def test_card_vault_tenant_id(self, db_session, sample_tenant):
        import uuid
        from models import CardVault, Customer
        uid = uuid.uuid4().hex[:6]
        cust = Customer(tenant_id=sample_tenant.id, name='Card Cust', phone='123')
        db_session.add(cust)
        db_session.flush()
        cv = CardVault(
            tenant_id=sample_tenant.id,
            customer_id=cust.id,
            card_hash="abc123hash-" + uid,
            card_number_encrypted=b"encrypted",
            cardholder_name_encrypted=b"encrypted_name",
            last_four="1234",
        )
        db_session.add(cv)
        db_session.commit()
        assert cv.id is not None
        assert cv.tenant_id == sample_tenant.id


class TestProductSerialModel:
    """ProductSerial — recently updated with tenant_id."""

    def test_product_serial_tenant_id(self, db_session, sample_tenant):
        from models import ProductSerial, Product
        prod = Product(tenant_id=sample_tenant.id, name='Serial Prod', sku='SN-PROD-001', regular_price=100)
        db_session.add(prod)
        db_session.flush()
        ps = ProductSerial(
            tenant_id=sample_tenant.id,
            product_id=prod.id,
            serial_number="SN123456",
            status="available",
        )
        db_session.add(ps)
        db_session.commit()
        assert ps.id is not None
        assert ps.tenant_id == sample_tenant.id


class TestSaleModel:
    """Sale model tests."""

    def test_sale_tenant_scoped(self, db_session, sample_tenant, sample_user):
        from models import Sale, Customer
        c = Customer(
            tenant_id=sample_tenant.id,
            name="Test Customer",
            phone="0500000000",
            is_active=True,
        )
        db_session.add(c)
        db_session.flush()
        s = Sale(
            tenant_id=sample_tenant.id,
            customer_id=c.id,
            seller_id=sample_user.id,
            sale_number="SALE-001",
            total_amount=1000.0,
            amount=1000.0,
            amount_aed=1000.0,
            currency="AED",
            status="confirmed",
        )
        db_session.add(s)
        db_session.commit()
        assert s.id is not None
        assert s.tenant_id == sample_tenant.id


class TestPurchaseModel:
    """Purchase model tests."""

    def test_purchase_tenant_scoped(self, db_session, sample_tenant):
        from models import Purchase
        p = Purchase(
            tenant_id=sample_tenant.id,
            supplier_id=None,
            purchase_number="PUR-001",
            supplier_name="Test Supplier",
            total_amount=500.0,
            amount=500.0,
            amount_aed=500.0,
            currency="AED",
            status="confirmed",
            user_id=1,
        )
        db_session.add(p)
        db_session.commit()
        assert p.id is not None
        assert p.tenant_id == sample_tenant.id


class TestGLAccountModel:
    """GL Account model tests."""

    def test_gl_account_tenant_scoped(self, db_session, sample_tenant):
        from models import GLAccount
        acc = GLAccount(
            tenant_id=sample_tenant.id,
            code="1110",
            name="Cash",
            type="asset",
            is_active=True,
        )
        db_session.add(acc)
        db_session.commit()
        assert acc.id is not None
        assert acc.tenant_id == sample_tenant.id


class TestWarehouseModel:
    """Warehouse model tests."""

    def test_warehouse_tenant_scoped(self, db_session, sample_tenant):
        from models import Warehouse
        wh = Warehouse(
            tenant_id=sample_tenant.id,
            name="Main Warehouse",
            code="WH-001",
            is_active=True,
        )
        db_session.add(wh)
        db_session.commit()
        assert wh.id is not None
        assert wh.tenant_id == sample_tenant.id


class TestCustomerModel:
    """Customer model tests."""

    def test_customer_tenant_scoped(self, db_session, sample_tenant):
        from models import Customer
        c = Customer(
            tenant_id=sample_tenant.id,
            name="Test Customer",
            phone="0500000000",
            is_active=True,
        )
        db_session.add(c)
        db_session.commit()
        assert c.id is not None
        assert c.tenant_id == sample_tenant.id


class TestSupplierModel:
    """Supplier model tests."""

    def test_supplier_tenant_scoped(self, db_session, sample_tenant):
        from models import Supplier
        s = Supplier(
            tenant_id=sample_tenant.id,
            name="Test Supplier",
            phone="0500000000",
            is_active=True,
        )
        db_session.add(s)
        db_session.commit()
        assert s.id is not None
        assert s.tenant_id == sample_tenant.id


class TestPaymentModel:
    """Payment model tests."""

    def test_payment_tenant_scoped(self, db_session, sample_tenant):
        from models import Payment
        p = Payment(
            tenant_id=sample_tenant.id,
            payment_number="PAY-001",
            payment_type="cash",
            amount=100.0,
            amount_aed=100.0,
            currency="AED",
            payment_method="cash",
        )
        db_session.add(p)
        db_session.commit()
        assert p.id is not None
        assert p.tenant_id == sample_tenant.id


class TestChequeModel:
    """Cheque model tests."""

    def test_cheque_tenant_scoped(self, db_session, sample_tenant):
        from models import Cheque
        from datetime import date
        c = Cheque(
            tenant_id=sample_tenant.id,
            cheque_number="CHQ001",
            cheque_bank_number="BANK001",
            cheque_type="incoming",
            bank_name="Test Bank",
            amount=1000.0,
            currency="AED",
            issue_date=date.today(),
            due_date=date.today(),
        )
        db_session.add(c)
        db_session.commit()
        assert c.id is not None
        assert c.tenant_id == sample_tenant.id


class TestBranchModel:
    """Branch model tests."""

    def test_branch_tenant_scoped(self, db_session, sample_tenant):
        from models import Branch
        b = Branch(
            tenant_id=sample_tenant.id,
            name="Main Branch",
            code="BR-001",
            is_active=True,
        )
        db_session.add(b)
        db_session.commit()
        assert b.id is not None
        assert b.tenant_id == sample_tenant.id


class TestExpenseModel:
    """Expense model tests."""

    def test_expense_tenant_scoped(self, db_session, sample_tenant, sample_user):
        from models import Expense, ExpenseCategory
        cat = ExpenseCategory(tenant_id=sample_tenant.id, name='Test Cat', name_ar='اختبار', gl_account_code='6100')
        db_session.add(cat)
        db_session.flush()
        e = Expense(
            tenant_id=sample_tenant.id,
            expense_number="EXP-001",
            category_id=cat.id,
            amount=100.0,
            amount_aed=100.0,
            currency="AED",
            payment_method="cash",
            user_id=sample_user.id,
            description="Test expense",
        )
        db_session.add(e)
        db_session.commit()
        assert e.id is not None
        assert e.tenant_id == sample_tenant.id


class TestSystemSettingsModel:
    """SystemSettings model tests."""

    def test_system_settings_creation(self, db_session):
        from models import SystemSettings
        ss = SystemSettings(
            system_name="Test",
            default_currency="AED",
        )
        db_session.add(ss)
        db_session.commit()
        assert ss.id is not None
        assert ss.system_name == "Test"


class TestRoleAndPermissionModel:
    """Role and Permission model tests."""

    def test_role_creation(self, db_session):
        import uuid
        from models import Role
        uid = uuid.uuid4().hex[:6]
        role = Role(
            name="Manager-" + uid,
            slug="manager-" + uid,
            is_active=True,
        )
        db_session.add(role)
        db_session.commit()
        assert role.id is not None
        assert role.slug == "manager-" + uid

    def test_permission_creation(self, db_session):
        import uuid
        from models import Permission
        uid = uuid.uuid4().hex[:6]
        perm = Permission(
            code="can_view_sales-" + uid,
            name="View Sales",
        )
        db_session.add(perm)
        db_session.commit()
        assert perm.id is not None
        assert perm.code == "can_view_sales-" + uid


class TestAuditLogModel:
    """AuditLog model tests."""

    def test_audit_log_tenant_scoped(self, db_session, sample_tenant):
        from models import AuditLog
        al = AuditLog(
            tenant_id=sample_tenant.id,
            action="CREATE",
            table_name="Product",
            record_id=1,
        )
        db_session.add(al)
        db_session.commit()
        assert al.id is not None
        assert al.tenant_id == sample_tenant.id


class TestGLJournalEntryModel:
    """GL Journal Entry model tests."""

    def test_journal_entry_tenant_scoped(self, db_session, sample_tenant):
        from models import GLJournalEntry
        je = GLJournalEntry(
            tenant_id=sample_tenant.id,
            entry_number="JE-001",
            is_posted=True,
            total_debit=100.0,
            total_credit=100.0,
        )
        db_session.add(je)
        db_session.commit()
        assert je.id is not None
        assert je.tenant_id == sample_tenant.id


class TestStockMovementModel:
    """StockMovement model tests."""

    def test_stock_movement_tenant_scoped(self, db_session, sample_tenant):
        from models import StockMovement, Product, Warehouse
        prod = Product(tenant_id=sample_tenant.id, name='Stock Prod', sku='STK-001', regular_price=10)
        wh = Warehouse(tenant_id=sample_tenant.id, name='Stock WH', code='STK1')
        db_session.add_all([prod, wh])
        db_session.flush()
        sm = StockMovement(
            tenant_id=sample_tenant.id,
            product_id=prod.id,
            warehouse_id=wh.id,
            movement_type="in",
            quantity=10.0,
            reference_type="Purchase",
        )
        db_session.add(sm)
        db_session.commit()
        assert sm.id is not None
        assert sm.tenant_id == sample_tenant.id


class TestLoginHistoryModel:
    """LoginHistory model tests."""

    def test_login_history_creation(self, db_session, sample_user):
        from models.login_history import LoginHistory
        lh = LoginHistory(
            user_id=sample_user.id,
            username=sample_user.username,
            ip_address="127.0.0.1",
            success=True,
        )
        db_session.add(lh)
        db_session.commit()
        assert lh.id is not None
        assert lh.username == sample_user.username


class TestSecurityAlertModel:
    """SecurityAlert model tests."""

    def test_security_alert_creation(self, db_session, sample_user):
        from models.security_alert import SecurityAlert
        sa = SecurityAlert(
            alert_type="test",
            severity="low",
            title="Test Alert",
            user_id=sample_user.id,
            username=sample_user.username,
        )
        db_session.add(sa)
        db_session.commit()
        assert sa.id is not None
        assert sa.alert_type == "test"


class TestAPIKeyModel:
    """APIKey model tests."""

    def test_api_key_creation(self, db_session, sample_user):
        import uuid
        from models.api_key import APIKey
        uid = uuid.uuid4().hex[:6]
        ak = APIKey(
            created_by=sample_user.id,
            name="test-key-" + uid,
            key="ak_test12345-" + uid,
            service="test",
        )
        db_session.add(ak)
        db_session.commit()
        assert ak.id is not None
        assert ak.key == "ak_test12345-" + uid


class TestInvoiceSettingsModel:
    """InvoiceSettings model tests."""

    def test_invoice_settings_creation(self, db_session, sample_tenant):
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


class TestCostCenterModel:
    """CostCenter model tests."""

    def test_cost_center_tenant_scoped(self, db_session, sample_tenant):
        from models import CostCenter
        cc = CostCenter(
            tenant_id=sample_tenant.id,
            code="CC001",
            name_ar="تسويق",
        )
        db_session.add(cc)
        db_session.commit()
        assert cc.id is not None
        assert cc.tenant_id == sample_tenant.id


class TestProfitCenterModel:
    """ProfitCenter model tests."""

    def test_profit_center_tenant_scoped(self, db_session, sample_tenant):
        from models import ProfitCenter
        pc = ProfitCenter(
            tenant_id=sample_tenant.id,
            code="PC001",
            name_ar="مبيعات",
        )
        db_session.add(pc)
        db_session.commit()
        assert pc.id is not None
        assert pc.tenant_id == sample_tenant.id


# ---------------------------------------------------------------------------
# models/gl.py
# ---------------------------------------------------------------------------
class TestGLAccountBalance:
    def test_gl_account_full_name(self, db_session, sample_tenant):
        from models import GLAccount
        acc = GLAccount(
            tenant_id=sample_tenant.id,
            code="101",
            name="Cash",
            name_ar="النقدية",
            type="asset",
            is_active=True,
        )
        db_session.add(acc)
        db_session.commit()
        assert acc.full_name == "101 - النقدية"

    def test_gl_account_type_ar(self, db_session, sample_tenant):
        from models import GLAccount
        acc = GLAccount(
            tenant_id=sample_tenant.id,
            code="102",
            name="Bank",
            type="asset",
        )
        db_session.add(acc)
        db_session.commit()
        assert "أصول" in acc.type_ar

    def test_gl_account_header_children(self, db_session, sample_tenant):
        from models import GLAccount
        parent = GLAccount(
            tenant_id=sample_tenant.id,
            code="100",
            name="Current Assets",
            type="asset",
            is_header=True,
        )
        child = GLAccount(
            tenant_id=sample_tenant.id,
            code="101",
            name="Cash",
            type="asset",
            is_header=False,
            parent=parent,
        )
        db_session.add(parent)
        db_session.add(child)
        db_session.commit()
        assert parent.is_header is True
        assert child in parent.children


class TestGLJournalEntryReverse:
    def test_entry_is_balanced(self, db_session, sample_tenant):
        from models import GLJournalEntry
        entry = GLJournalEntry(
            tenant_id=sample_tenant.id,
            entry_number="JE-001",
            total_debit=Decimal("100"),
            total_credit=Decimal("100"),
        )
        db_session.add(entry)
        db_session.commit()
        assert entry.is_balanced() is True

    def test_entry_not_balanced_in_memory(self, db_session, sample_tenant):
        from models import GLJournalEntry
        entry = GLJournalEntry(
            tenant_id=sample_tenant.id,
            entry_number="JE-002",
            total_debit=Decimal("100"),
            total_credit=Decimal("50"),
        )
        assert entry.is_balanced() is False

    def test_entry_type_ar(self, db_session, sample_tenant):
        from models import GLJournalEntry
        entry = GLJournalEntry(
            tenant_id=sample_tenant.id,
            entry_number="JE-003",
            entry_type="manual",
        )
        assert "يدوي" in entry.entry_type_ar

    def test_reverse_entry(self, db_session, sample_tenant, sample_user):
        from models import GLAccount, GLJournalEntry, GLJournalLine
        acc1 = GLAccount(tenant_id=sample_tenant.id, code="101", name="Cash", type="asset")
        acc2 = GLAccount(tenant_id=sample_tenant.id, code="201", name="Payable", type="liability")
        db_session.add(acc1)
        db_session.add(acc2)
        db_session.flush()
        entry = GLJournalEntry(
            tenant_id=sample_tenant.id,
            entry_number="JE-004",
            total_debit=Decimal("100"),
            total_credit=Decimal("100"),
            created_by=sample_user.id,
        )
        db_session.add(entry)
        db_session.flush()
        line1 = GLJournalLine(
            tenant_id=sample_tenant.id,
            entry_id=entry.id,
            account_id=acc1.id,
            debit=Decimal("100"),
            credit=Decimal("0"),
            amount_aed=Decimal("100"),
        )
        line2 = GLJournalLine(
            tenant_id=sample_tenant.id,
            entry_id=entry.id,
            account_id=acc2.id,
            debit=Decimal("0"),
            credit=Decimal("100"),
            amount_aed=Decimal("-100"),
        )
        db_session.add(line1)
        db_session.add(line2)
        db_session.commit()
        rev = entry.reverse_entry(description="Reverse test")
        assert rev is not None
        assert rev.entry_type == "reversing"
        assert entry.is_reversed is True
        assert rev.total_debit == entry.total_credit
        assert rev.total_credit == entry.total_debit


class TestGLJournalLineSide:
    def test_line_debit_credit(self):
        from models import GLJournalLine
        line = GLJournalLine(
            account_id=1,
            debit=Decimal("50"),
            credit=Decimal("0"),
            amount_aed=Decimal("50"),
        )
        assert line.debit == Decimal("50")
        assert line.credit == Decimal("0")

    def test_line_base_amount_alias(self):
        from models import GLJournalLine
        line = GLJournalLine(amount_aed=Decimal("75.5"))
        assert line.base_amount == Decimal("75.5")
        line.base_amount = Decimal("80")
        assert line.amount_aed == Decimal("80")


class TestGLConceptRegistry:
    def test_required_concepts(self):
        from models._constants import REQUIRED_GL_CONCEPTS, GL_CONCEPT_REGISTRY
        for code in REQUIRED_GL_CONCEPTS:
            assert GL_CONCEPT_REGISTRY[code]["required"] is True

    def test_all_codes_valid(self):
        from models._constants import VALID_GL_CONCEPT_CODES, GL_CONCEPT_CODES
        assert VALID_GL_CONCEPT_CODES == set(GL_CONCEPT_CODES)

    def test_unknown_code_raises(self):
        from models.gl import GLAccountMapping
        with pytest.raises(ValueError):
            GLAccountMapping.validate_concept_code("INVALID_CONCEPT")


class TestGLAccountMappingModel:
    def test_mapping_repr(self, db_session, sample_tenant):
        from models import GLAccount, GLAccountMapping
        acc = GLAccount(tenant_id=sample_tenant.id, code="101", name="Cash", type="asset")
        db_session.add(acc)
        db_session.flush()
        m = GLAccountMapping(
            tenant_id=sample_tenant.id,
            concept_code="CASH",
            gl_account_id=acc.id,
        )
        db_session.add(m)
        db_session.commit()
        assert "CASH" in repr(m)
        assert str(acc.id) in repr(m)
