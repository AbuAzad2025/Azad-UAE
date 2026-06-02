"""Comprehensive Accounting Report - GL, Trial Balance, Budget per tenant/branch."""
import os, sys
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)
os.chdir(project_root)
os.environ["DATABASE_URL"] = "postgresql+psycopg2://postgres:123@localhost:5432/azad_uae"
os.environ["SKIP_SYSTEM_INTEGRITY"] = "1"

from app import create_app
from extensions import db
from sqlalchemy import text
from decimal import Decimal

app = create_app()


def print_section(title):
    print(f"\n{'='*80}")
    print(f"  {title}")
    print(f"{'='*80}")


def get_tenants():
    """Get all active tenants."""
    with app.app_context():
        conn = db.engine.connect()
        result = conn.execute(text("""
            SELECT id, slug, name, default_currency 
            FROM tenants 
            WHERE is_active = true
            ORDER BY id
        """))
        return result.fetchall()


def get_branches(tenant_id):
    """Get branches for a tenant."""
    with app.app_context():
        conn = db.engine.connect()
        result = conn.execute(text("""
            SELECT id, name, code, is_main 
            FROM branches 
            WHERE tenant_id = :tenant_id
            ORDER BY is_main DESC, name
        """), {"tenant_id": tenant_id})
        return result.fetchall()


def verify_gl_entries(tenant_id, tenant_name):
    """Verify GL entries for a tenant."""
    print(f"\n--- GL Entries for {tenant_name} ---")
    
    with app.app_context():
        conn = db.engine.connect()
        
        # Total entries
        result = conn.execute(text("""
            SELECT COUNT(*), 
                   COALESCE(SUM(total_debit), 0), 
                   COALESCE(SUM(total_credit), 0)
            FROM gl_journal_entries 
            WHERE tenant_id = :tenant_id
        """), {"tenant_id": tenant_id})
        
        row = result.fetchone()
        count = row[0]
        total_debit = row[1] or Decimal('0')
        total_credit = row[2] or Decimal('0')
        
        print(f"Total Entries: {count}")
        print(f"Total Debit: {total_debit}")
        print(f"Total Credit: {total_credit}")
        
        if abs(total_debit - total_credit) < Decimal('0.01'):
            print("✅ Balanced")
        else:
            print(f"❌ Not Balanced! Diff: {total_debit - total_credit}")
        
        # Entries by reference type
        result = conn.execute(text("""
            SELECT reference_type, COUNT(*)
            FROM gl_journal_entries 
            WHERE tenant_id = :tenant_id
            GROUP BY reference_type
            ORDER BY COUNT(*) DESC
        """), {"tenant_id": tenant_id})
        
        print("\nEntries by Type:")
        for row in result:
            print(f"  {row[0]}: {row[1]}")


def verify_trial_balance(tenant_id, tenant_name):
    """Verify trial balance for a tenant."""
    print(f"\n--- Trial Balance for {tenant_name} ---")
    
    with app.app_context():
        conn = db.engine.connect()
        
        result = conn.execute(text("""
            SELECT a.type, a.code, a.name,
                   COALESCE(SUM(l.debit), 0) as total_debit,
                   COALESCE(SUM(l.credit), 0) as total_credit,
                   COALESCE(SUM(l.debit), 0) - COALESCE(SUM(l.credit), 0) as balance
            FROM gl_accounts a
            LEFT JOIN gl_journal_lines l ON a.id = l.account_id
            WHERE a.tenant_id = :tenant_id
            GROUP BY a.type, a.code, a.name
            HAVING COALESCE(SUM(l.debit), 0) > 0 OR COALESCE(SUM(l.credit), 0) > 0
            ORDER BY a.type, a.code
        """), {"tenant_id": tenant_id})
        
        print(f"{'Type':<15} {'Code':<10} {'Name':<30} {'Debit':<15} {'Credit':<15} {'Balance':<15}")
        print("-" * 100)
        
        total_debit = Decimal('0')
        total_credit = Decimal('0')
        
        for row in result:
            acc_type = row[0]
            code = row[1]
            name = row[2]
            debit = row[3] or Decimal('0')
            credit = row[4] or Decimal('0')
            balance = row[5] or Decimal('0')
            
            print(f"{acc_type:<15} {code:<10} {name:<30} {debit:<15.2f} {credit:<15.2f} {balance:<15.2f}")
            
            total_debit += debit
            total_credit += credit
        
        print("-" * 100)
        print(f"{'TOTAL':<55} {total_debit:<15.2f} {total_credit:<15.2f} {total_debit - total_credit:<15.2f}")
        
        if abs(total_debit - total_credit) < Decimal('0.01'):
            print("✅ Trial Balance is Balanced")
        else:
            print(f"❌ Trial Balance is NOT Balanced! Diff: {total_debit - total_credit}")


def verify_budgets(tenant_id, tenant_name):
    """Verify budgets for a tenant."""
    print(f"\n--- Budgets for {tenant_name} ---")
    
    with app.app_context():
        conn = db.engine.connect()
        
        # Budgets are global, not tenant-specific
        result = conn.execute(text("""
            SELECT b.budget_number, b.fiscal_year, b.status,
                   b.total_budgeted, b.total_actual, b.total_variance
            FROM budgets b
            ORDER BY b.fiscal_year DESC
        """))
        
        budgets = result.fetchall()
        
        if not budgets:
            print("No budgets found")
            return
        
        print(f"{'Budget #':<20} {'Year':<10} {'Status':<15} {'Budgeted':<15} {'Actual':<15} {'Variance':<15}")
        print("-" * 90)
        
        for row in budgets:
            budget_num = row[0]
            year = row[1]
            status = row[2]
            budgeted = row[3] or Decimal('0')
            actual = row[4] or Decimal('0')
            variance = row[5] or Decimal('0')
            
            print(f"{budget_num:<20} {year:<10} {status:<15} {budgeted:<15.2f} {actual:<15.2f} {variance:<15.2f}")


def verify_branch_accounts(tenant_id, tenant_name):
    """Verify accounts by branch for a tenant."""
    print(f"\n--- Branch-wise Accounts for {tenant_name} ---")
    
    branches = get_branches(tenant_id)
    
    if not branches:
        print("No branches found")
        return
    
    with app.app_context():
        conn = db.engine.connect()
        
        for branch_id, branch_name, branch_code, is_main in branches:
            print(f"\nBranch: {branch_name} ({branch_code}) {'[MAIN]' if is_main else ''}")
            
            result = conn.execute(text("""
                SELECT COUNT(DISTINCT e.id) as entry_count
                FROM gl_journal_entries e
                WHERE e.tenant_id = :tenant_id AND e.branch_id = :branch_id
            """), {"tenant_id": tenant_id, "branch_id": branch_id})
            
            count = result.scalar()
            print(f"  GL Entries: {count}")


def main():
    """Generate comprehensive accounting report for all tenants."""
    print("="*80)
    print("  COMPREHENSIVE ACCOUNTING REPORT")
    print("="*80)
    
    tenants = get_tenants()
    
    print(f"\nFound {len(tenants)} active tenants")
    
    for tenant_id, tenant_slug, tenant_name, currency in tenants:
        print_section(f"TENANT: {tenant_name} ({tenant_slug}) - Currency: {currency}")
        
        verify_gl_entries(tenant_id, tenant_name)
        verify_trial_balance(tenant_id, tenant_name)
        verify_budgets(tenant_id, tenant_name)
        verify_branch_accounts(tenant_id, tenant_name)
    
    print_section("REPORT COMPLETED")


if __name__ == "__main__":
    main()
