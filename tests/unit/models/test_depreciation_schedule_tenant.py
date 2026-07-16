"""Tests for FixedAsset and DepreciationSchedule tenant isolation"""
from datetime import date
from decimal import Decimal
from models.fixed_asset import FixedAsset, DepreciationSchedule
from models.gl import GLAccount


class TestDepreciationScheduleTenantIsolation:
    """Test tenant isolation for FixedAsset and DepreciationSchedule"""

    def test_depreciation_schedule_model_fields(self, db_session):
        """Test that DepreciationSchedule has all required fields"""
        # Verify model structure
        assert hasattr(DepreciationSchedule, 'tenant_id')
        assert hasattr(DepreciationSchedule, 'asset_id')
        assert hasattr(DepreciationSchedule, 'period_date')
        assert hasattr(DepreciationSchedule, 'depreciation_amount')
        assert hasattr(DepreciationSchedule, 'accumulated_depreciation')
        assert hasattr(DepreciationSchedule, 'book_value')
        assert hasattr(DepreciationSchedule, 'journal_entry_id')
        assert hasattr(DepreciationSchedule, 'created_at')
        assert hasattr(DepreciationSchedule, 'tenant')
        assert hasattr(DepreciationSchedule, 'asset')
        assert hasattr(DepreciationSchedule, 'journal_entry')

    def test_fixed_asset_status_enum_values(self, db_session, sample_tenant, sample_branch):
        """Test that FixedAsset has correct enum/status values"""
        # Create GL account
        expense_account = GLAccount(
            tenant_id=sample_tenant.id,
            code='EXPENSE_001',
            name='Expense Account',
            name_ar='حساب المصروفات',
            type='expense',
            sub_type='operating',
            currency='ILS',
            is_active=True
        )
        db_session.add(expense_account)
        db_session.flush()

        # Test all status values
        statuses = ['active', 'fully_depreciated', 'disposed', 'sold']
        for status in statuses:
            asset = FixedAsset(
                tenant_id=sample_tenant.id,
                asset_number=f'TEST-{status}',
                name_ar=f'Asset {status}',
                name_en=f'Asset {status}',
                category='equipment',
                asset_account_id=1,
                depreciation_account_id=1,
                expense_account_id=expense_account.id,
                purchase_date=date(2023, 1, 1),
                purchase_price=Decimal('10000.00'),
                salvage_value=Decimal('1000.00'),
                useful_life_years=5,
                branch_id=sample_branch.id,
                status=status
            )
            db_session.add(asset)
            db_session.flush()

            assert asset.status == status
            assert asset.status_ar in ['نشط', 'مستهلك بالكامل', 'تم التخلص منه', 'تم بيعه']

    def test_depreciation_schedule_tenant_id_field(self, db_session):
        """Test that DepreciationSchedule has tenant_id field with correct properties"""
        # Check model definition
        tenant_id_column = DepreciationSchedule.__table__.c.tenant_id
        assert tenant_id_column is not None
        assert tenant_id_column.nullable == False
        assert tenant_id_column.index == True

        # Check foreign key
        fks = [fk for fk in DepreciationSchedule.__table__.foreign_keys if 'tenants' in str(fk)]
        assert len(fks) > 0
        # The foreign key should reference the tenants table
        assert 'tenants' in str(fks[0])

    def test_fixed_asset_tenant_id_field(self, db_session, sample_tenant):
        """Test that FixedAsset has tenant_id field with correct properties"""
        # Check model definition
        tenant_id_column = FixedAsset.__table__.c.tenant_id
        assert tenant_id_column is not None
        assert tenant_id_column.nullable == False
        assert tenant_id_column.index == True

        # Check foreign key
        fks = [fk for fk in FixedAsset.__table__.foreign_keys if 'tenants' in str(fk)]
        assert len(fks) > 0
        # The foreign key should reference the tenants table
        assert 'tenants' in str(fks[0])