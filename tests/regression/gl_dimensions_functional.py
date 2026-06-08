import os
os.environ['FLASK_APP'] = 'app.py'
from app import create_app
from extensions import db
from datetime import datetime, timezone

app = create_app()

with app.app_context():
    print("\n" + "="*70)
    print("FUNCTIONAL TEST: GL POSTING WITH NEW DIMENSION FIELDS")
    print("="*70)

    # Get required data
    from models.gl import GLAccount, GLJournalEntry, GLJournalLine
    from models.branch import Branch
    from models.warehouse import Warehouse
    from models.cost_center import CostCenter
    from models.tenant import Tenant
    from services.gl_service import GLService
    from sqlalchemy import text

    # 1. Get test data
    print("\n1. RETRIEVING TEST DATA:")

    tenant = db.session.query(Tenant).first()
    print(f"   ✓ Tenant: {tenant.name if tenant else 'NOT FOUND'}")

    branch = db.session.query(Branch).filter_by(tenant_id=tenant.id if tenant else 1).first()
    print(f"   ✓ Branch: {branch.name if branch else 'NOT FOUND'}")

    warehouse = db.session.query(Warehouse).filter_by(tenant_id=tenant.id if tenant else 1).first()
    print(f"   ✓ Warehouse: {warehouse.name_ar if warehouse else 'NOT FOUND'}")

    cost_center = db.session.query(CostCenter).filter_by(tenant_id=tenant.id if tenant else 1).first()
    print(f"   ✓ Cost Center: {cost_center.name_ar if cost_center else 'NOT FOUND'}")

    # Get GL accounts
    cash_account = db.session.query(GLAccount).filter(
        GLAccount.code == '1000'
    ).first()
    if not cash_account:
        cash_account = db.session.query(GLAccount).filter(
            GLAccount.type == 'asset'
        ).first()

    expense_account = db.session.query(GLAccount).filter(
        GLAccount.type == 'expense'
    ).first()

    print(f"   ✓ Cash Account: {cash_account.code if cash_account else 'NOT FOUND'}")
    print(f"   ✓ Expense Account: {expense_account.code if expense_account else 'NOT FOUND'}")

    if not all([tenant, branch, warehouse, cost_center, cash_account, expense_account]):
        print("\n   ⚠ Missing required data for testing!")
    else:
        # 2. Test GL Service with new fields
        print("\n2. TESTING GL SERVICE CREATE_JOURNAL_ENTRY WITH DIMENSIONS:")

        try:
            # Create test entry using GLService
            service = GLService()

            # Prepare journal entry lines with dimension fields
            lines = [
                {
                    'code': cash_account.code,
                    'debit': 1000,
                    'credit': 0,
                    'description': 'Test Debit with Dimensions',
                    'branch_id': branch.id,
                    'warehouse_id': warehouse.id,
                    'cost_center_id': cost_center.id,
                },
                {
                    'code': expense_account.code,
                    'debit': 0,
                    'credit': 1000,
                    'description': 'Test Credit with Dimensions',
                    'branch_id': branch.id,
                    'warehouse_id': warehouse.id,
                    'cost_center_id': cost_center.id,
                }
            ]

            # Create entry with the correct signature
            entry = service.create_journal_entry(
                date=datetime.now(timezone.utc).date(),
                description='Test GL Entry with Dimensions',
                lines=lines,
                branch_id=branch.id,
                reference_type='TEST',
                reference_id=999,
                tenant_id=tenant.id
            )
            print(f"   ✓ Entry Created: {entry.id}")
            print(f"   ✓ Entry Number: {entry.entry_number}")
            print(f"   ✓ Entry Posted: {entry.is_posted}")

            # Check if dimensions were saved
            print("\n   Checking dimension fields in created lines:")
            for i, line in enumerate(entry.lines, 1):
                print(f"\n   Line {i}:")
                print(f"     - account_id: {line.account_id}")
                print(f"     - debit: {line.debit}")
                print(f"     - credit: {line.credit}")
                print(f"     - branch_id: {line.branch_id}")
                print(f"     - warehouse_id: {line.warehouse_id}")
                print(f"     - cost_center_id: {line.cost_center_id}")

                # Verify dimensions match what was passed
                if line.branch_id == branch.id:
                    print(f"     ✓ branch_id matches")
                else:
                    print(f"     ⚠ branch_id mismatch: expected {branch.id}, got {line.branch_id}")

                if line.warehouse_id == warehouse.id:
                    print(f"     ✓ warehouse_id matches")
                else:
                    print(f"     ⚠ warehouse_id mismatch: expected {warehouse.id}, got {line.warehouse_id}")

                if line.cost_center_id == cost_center.id:
                    print(f"     ✓ cost_center_id matches")
                else:
                    print(f"     ⚠ cost_center_id mismatch: expected {cost_center.id}, got {line.cost_center_id}")

            # 3. Test reversal with dimensions
            print("\n3. TESTING REVERSAL WITH DIMENSION PROPAGATION:")

            reversed_entry = service.reverse_entry(entry.id, tenant.id, 'Test reversal with dimensions')
            print(f"   ✓ Reversed Entry Created: {reversed_entry.id}")
            print(f"   ✓ Reversal entry number: {reversed_entry.entry_number}")

            # Check reversed lines have dimensions
            print("\n   Checking dimensions in reversed lines:")
            for i, line in enumerate(reversed_entry.lines, 1):
                matches = (
                    line.branch_id == entry.lines[i-1].branch_id and
                    line.warehouse_id == entry.lines[i-1].warehouse_id and
                    line.cost_center_id == entry.lines[i-1].cost_center_id
                )
                status = "✓" if matches else "⚠"
                print(f"   {status} Reversed Line {i}: dimensions propagated correctly")

        except Exception as e:
            print(f"   ✗ ERROR: {str(e)}")
            import traceback
            traceback.print_exc()

    print("\n" + "="*70)
    print("TEST COMPLETE")
    print("="*70)
