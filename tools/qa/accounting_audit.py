"""Accounting Audit Script - Verify GL entries and account balances."""
import os, sys
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)
os.chdir(project_root)
os.environ["DATABASE_URL"] = "postgresql+psycopg2://postgres:123@localhost:5432/azad_uae"
os.environ["SKIP_SYSTEM_INTEGRITY"] = "1"

from app import create_app
from extensions import db
from sqlalchemy import func, text
from decimal import Decimal

app = create_app()


def print_section(title):
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}")


def audit_gl_entries_balance():
    """Check if each GL entry has balanced debits and credits."""
    print_section("GL ENTRIES BALANCE CHECK")
    
    with app.app_context():
        conn = db.engine.connect()
        
        # Get totals
        result = conn.execute(text("""
            SELECT 
                COALESCE(SUM(total_debit), 0) as total_debit,
                COALESCE(SUM(total_credit), 0) as total_credit,
                COUNT(*) as count
            FROM gl_journal_entries
        """))
        
        row = result.fetchone()
        total_debit = row[0] or Decimal('0')
        total_credit = row[1] or Decimal('0')
        count = row[2]
        
        print(f"Total GL Entries: {count}")
        print(f"Total Debits: {total_debit}")
        print(f"Total Credits: {total_credit}")
        
        if abs(total_debit - total_credit) < Decimal('0.01'):
            print("✅ GL entries are balanced")
        else:
            print(f"❌ GL entries are NOT balanced! Difference: {total_debit - total_credit}")
        
        # Check individual entries
        result = conn.execute(text("""
            SELECT id, entry_number, total_debit, total_credit, 
                   total_debit - total_credit as difference
            FROM gl_journal_entries
            WHERE ABS(total_debit - total_credit) > 0.01
            ORDER BY difference DESC
            LIMIT 10
        """))
        
        unbalanced = result.fetchall()
        if unbalanced:
            print(f"\n⚠️  Found {len(unbalanced)} unbalanced entries:")
            for row in unbalanced:
                print(f"  Entry {row[1]}: Debit={row[2]}, Credit={row[3]}, Diff={row[4]}")
        else:
            print("\n✅ All individual GL entries are balanced")


def audit_account_balances():
    """Verify account balances from GL lines."""
    print_section("ACCOUNT BALANCES VERIFICATION")
    
    with app.app_context():
        conn = db.engine.connect()
        
        # Get account type summary
        result = conn.execute(text("""
            SELECT a.type, 
                   COUNT(DISTINCT a.id) as account_count,
                   COALESCE(SUM(l.debit), 0) as total_debit,
                   COALESCE(SUM(l.credit), 0) as total_credit
            FROM gl_accounts a
            LEFT JOIN gl_journal_lines l ON a.id = l.account_id
            GROUP BY a.type
            ORDER BY a.type
        """))
        
        print(f"{'Type':<20} {'Accounts':<12} {'Total Debit':<20} {'Total Credit':<20}")
        print("-" * 72)
        for row in result:
            print(f"{row[0]:<20} {row[1]:<12} {row[2]:<20.2f} {row[3]:<20.2f}")
        
        # Check for accounts with no activity
        result = conn.execute(text("""
            SELECT a.code, a.name, a.type
            FROM gl_accounts a
            LEFT JOIN gl_journal_lines l ON a.id = l.account_id
            WHERE l.id IS NULL
            LIMIT 10
        """))
        
        inactive = result.fetchall()
        if inactive:
            print(f"\n⚠️  Found {len(inactive)} accounts with no GL activity:")
            for row in inactive:
                print(f"  {row[0]} - {row[1]} ({row[2]})")
        else:
            print("\n✅ All accounts have GL activity")


def audit_orphaned_records():
    """Check for orphaned records (records without valid references)."""
    print_section("ORPHANED RECORDS CHECK")
    
    with app.app_context():
        conn = db.engine.connect()
        
        checks = [
            ("GL Lines without Entry", """
                SELECT COUNT(*) FROM gl_journal_lines l
                LEFT JOIN gl_journal_entries e ON l.entry_id = e.id
                WHERE e.id IS NULL
            """),
            ("GL Lines without Account", """
                SELECT COUNT(*) FROM gl_journal_lines l
                LEFT JOIN gl_accounts a ON l.account_id = a.id
                WHERE a.id IS NULL
            """),
            ("GL Entries without Lines", """
                SELECT COUNT(*) FROM gl_journal_entries e
                LEFT JOIN gl_journal_lines l ON e.id = l.entry_id
                WHERE l.id IS NULL
            """),
            ("Sales without Customer", """
                SELECT COUNT(*) FROM sales s
                LEFT JOIN customers c ON s.customer_id = c.id
                WHERE c.id IS NULL AND s.customer_id IS NOT NULL
            """),
            ("Purchases without Supplier", """
                SELECT COUNT(*) FROM purchases p
                LEFT JOIN suppliers s ON p.supplier_id = s.id
                WHERE s.id IS NULL AND p.supplier_id IS NOT NULL
            """),
        ]
        
        for name, query in checks:
            result = conn.execute(text(query))
            count = result.scalar()
            if count > 0:
                print(f"❌ {name}: {count} orphaned records")
            else:
                print(f"✅ {name}: No orphaned records")


def audit_tenant_isolation():
    """Verify tenant data isolation."""
    print_section("TENANT ISOLATION CHECK")
    
    with app.app_context():
        conn = db.engine.connect()
        
        # Check for records with NULL tenant_id in tenant-scoped tables
        checks = [
            ("Customers", "customers"),
            ("Suppliers", "suppliers"),
            ("Products", "products"),
            ("Sales", "sales"),
            ("Purchases", "purchases"),
            ("Expenses", "expenses"),
            ("Employees", "employees"),
            ("Cost Centers", "cost_centers"),
        ]
        
        for name, table in checks:
            result = conn.execute(text(f"""
                SELECT COUNT(*) FROM {table} WHERE tenant_id IS NULL
            """))
            count = result.scalar()
            if count > 0:
                print(f"❌ {name}: {count} records with NULL tenant_id")
            else:
                print(f"✅ {name}: All records have tenant_id")


def audit_summary():
    """Generate audit summary."""
    print_section("AUDIT SUMMARY")
    
    with app.app_context():
        conn = db.engine.connect()
        
        # Record counts
        tables = [
            ("GL Entries", "gl_journal_entries"),
            ("GL Lines", "gl_journal_lines"),
            ("GL Accounts", "gl_accounts"),
            ("Customers", "customers"),
            ("Suppliers", "suppliers"),
            ("Products", "products"),
            ("Sales", "sales"),
            ("Purchases", "purchases"),
            ("Payments", "payments"),
            ("Receipts", "receipts"),
            ("Expenses", "expenses"),
            ("Cheques", "cheques"),
            ("Cost Centers", "cost_centers"),
            ("Tenants", "tenants"),
            ("Users", "users"),
        ]
        
        print(f"{'Table':<25} {'Count':<15}")
        print("-" * 40)
        for name, table in tables:
            result = conn.execute(text(f"SELECT COUNT(*) FROM {table}"))
            count = result.scalar()
            print(f"{name:<25} {count:<15}")


def main():
    """Run all audit checks."""
    print("="*70)
    print("  ACCOUNTING AUDIT REPORT")
    print("="*70)
    
    audit_summary()
    audit_gl_entries_balance()
    audit_account_balances()
    audit_orphaned_records()
    audit_tenant_isolation()
    
    print_section("AUDIT COMPLETED")
    print("Review the results above for any issues marked with ❌")


if __name__ == "__main__":
    main()
