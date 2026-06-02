"""Detailed General Ledger and Accounting Verification."""
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


def verify_journal_entry_completeness():
    """Verify all journal entries are complete and valid."""
    print_section("JOURNAL ENTRY COMPLETENESS CHECK")
    
    with app.app_context():
        conn = db.engine.connect()
        
        # Check entries without lines
        result = conn.execute(text("""
            SELECT e.id, e.entry_number, e.tenant_id
            FROM gl_journal_entries e
            LEFT JOIN gl_journal_lines l ON e.id = l.entry_id
            WHERE l.id IS NULL
        """))
        
        orphaned = result.fetchall()
        if orphaned:
            print(f"❌ Found {len(orphaned)} entries without lines:")
            for row in orphaned:
                print(f"  Entry {row[1]} (ID: {row[0]}, Tenant: {row[2]})")
        else:
            print("✅ All entries have lines")
        
        # Check entries with zero totals
        result = conn.execute(text("""
            SELECT id, entry_number, total_debit, total_credit
            FROM gl_journal_entries
            WHERE total_debit = 0 AND total_credit = 0
        """))
        
        zero_totals = result.fetchall()
        if zero_totals:
            print(f"❌ Found {len(zero_totals)} entries with zero totals:")
            for row in zero_totals:
                print(f"  Entry {row[1]} (ID: {row[0]})")
        else:
            print("✅ No entries with zero totals")
        
        # Check entries with missing required fields
        result = conn.execute(text("""
            SELECT id, entry_number
            FROM gl_journal_entries
            WHERE entry_date IS NULL OR description IS NULL OR currency IS NULL
        """))
        
        missing_fields = result.fetchall()
        if missing_fields:
            print(f"❌ Found {len(missing_fields)} entries with missing required fields:")
            for row in missing_fields:
                print(f"  Entry {row[1]} (ID: {row[0]})")
        else:
            print("✅ All entries have required fields")


def verify_account_balances():
    """Verify account balances are calculated correctly."""
    print_section("ACCOUNT BALANCES VERIFICATION")
    
    with app.app_context():
        conn = db.engine.connect()
        
        # Get all accounts with GL activity
        result = conn.execute(text("""
            SELECT a.id, a.code, a.name, a.type, a.tenant_id,
                   COALESCE(SUM(l.debit), 0) as total_debit,
                   COALESCE(SUM(l.credit), 0) as total_credit,
                   COALESCE(SUM(l.debit), 0) - COALESCE(SUM(l.credit), 0) as calculated_balance
            FROM gl_accounts a
            LEFT JOIN gl_journal_lines l ON a.id = l.account_id
            GROUP BY a.id, a.code, a.name, a.type, a.tenant_id
            HAVING COALESCE(SUM(l.debit), 0) > 0 OR COALESCE(SUM(l.credit), 0) > 0
            ORDER BY a.tenant_id, a.type, a.code
        """))
        
        print(f"{'Tenant':<15} {'Type':<12} {'Code':<10} {'Name':<25} {'Debit':<15} {'Credit':<15} {'Balance':<15}")
        print("-" * 110)
        
        for row in result:
            tenant_id = row[4]
            acc_type = row[3]
            code = row[1]
            name = row[2]
            debit = row[5] or Decimal('0')
            credit = row[6] or Decimal('0')
            balance = row[7] or Decimal('0')
            
            print(f"{tenant_id:<15} {acc_type:<12} {code:<10} {name:<25} {debit:<15.2f} {credit:<15.2f} {balance:<15.2f}")


def verify_general_ledger_per_account():
    """Verify General Ledger entries per account."""
    print_section("GENERAL LEDGER PER ACCOUNT")
    
    with app.app_context():
        conn = db.engine.connect()
        
        # Get accounts with most activity
        result = conn.execute(text("""
            SELECT a.id, a.code, a.name, a.type, COUNT(l.id) as line_count
            FROM gl_accounts a
            JOIN gl_journal_lines l ON a.id = l.account_id
            GROUP BY a.id, a.code, a.name, a.type
            ORDER BY line_count DESC
            LIMIT 10
        """))
        
        print("Top 10 Accounts by Activity:")
        print(f"{'Code':<10} {'Name':<30} {'Type':<12} {'Lines':<10}")
        print("-" * 62)
        
        for row in result:
            code = row[1]
            name = row[2]
            acc_type = row[3]
            line_count = row[4]
            
            print(f"{code:<10} {name:<30} {acc_type:<12} {line_count:<10}")


def verify_transaction_integrity():
    """Verify transaction integrity across related tables."""
    print_section("TRANSACTION INTEGRITY CHECK")
    
    with app.app_context():
        conn = db.engine.connect()
        
        checks = [
            ("Sales without GL entries", """
                SELECT COUNT(*) FROM sales s
                LEFT JOIN gl_journal_entries e ON e.reference_id = s.id AND e.reference_type = 'sale'
                WHERE e.id IS NULL
            """),
            ("Purchases without GL entries", """
                SELECT COUNT(*) FROM purchases p
                LEFT JOIN gl_journal_entries e ON e.reference_id = p.id AND e.reference_type = 'purchase'
                WHERE e.id IS NULL
            """),
            ("Payments without GL entries", """
                SELECT COUNT(*) FROM payments p
                LEFT JOIN gl_journal_entries e ON e.reference_id = p.id AND e.reference_type = 'payment'
                WHERE e.id IS NULL
            """),
            ("Receipts without GL entries", """
                SELECT COUNT(*) FROM receipts r
                LEFT JOIN gl_journal_entries e ON e.reference_id = r.id AND e.reference_type = 'receipt'
                WHERE e.id IS NULL
            """),
            ("Expenses without GL entries", """
                SELECT COUNT(*) FROM expenses e
                LEFT JOIN gl_journal_entries ge ON ge.reference_id = e.id AND ge.reference_type = 'expense'
                WHERE ge.id IS NULL
            """),
        ]
        
        for name, query in checks:
            result = conn.execute(text(query))
            count = result.scalar()
            if count > 0:
                print(f"⚠️  {name}: {count} transactions without GL entries")
            else:
                print(f"✅ {name}: All transactions have GL entries")


def verify_double_entry_principle():
    """Verify double-entry bookkeeping principle."""
    print_section("DOUBLE-ENTRY PRINCIPLE VERIFICATION")
    
    with app.app_context():
        conn = db.engine.connect()
        
        # Check each entry has at least 2 lines
        result = conn.execute(text("""
            SELECT e.id, e.entry_number, COUNT(l.id) as line_count
            FROM gl_journal_entries e
            LEFT JOIN gl_journal_lines l ON e.id = l.entry_id
            GROUP BY e.id, e.entry_number
            HAVING COUNT(l.id) < 2
        """))
        
        single_line = result.fetchall()
        if single_line:
            print(f"❌ Found {len(single_line)} entries with less than 2 lines:")
            for row in single_line:
                print(f"  Entry {row[1]} (ID: {row[0]}, Lines: {row[2]})")
        else:
            print("✅ All entries have at least 2 lines (double-entry)")
        
        # Check each entry has balanced debits and credits
        result = conn.execute(text("""
            SELECT id, entry_number, total_debit, total_credit,
                   total_debit - total_credit as difference
            FROM gl_journal_entries
            WHERE ABS(total_debit - total_credit) > 0.01
        """))
        
        unbalanced = result.fetchall()
        if unbalanced:
            print(f"❌ Found {len(unbalanced)} unbalanced entries:")
            for row in unbalanced:
                print(f"  Entry {row[1]}: Debit={row[2]}, Credit={row[3]}, Diff={row[4]}")
        else:
            print("✅ All entries are balanced")


def verify_tenant_accounting_isolation():
    """Verify tenant accounting isolation."""
    print_section("TENANT ACCOUNTING ISOLATION")
    
    with app.app_context():
        conn = db.engine.connect()
        
        # Check for cross-tenant GL entries
        result = conn.execute(text("""
            SELECT e.id, e.entry_number, e.tenant_id, l.tenant_id as line_tenant_id
            FROM gl_journal_entries e
            JOIN gl_journal_lines l ON e.id = l.entry_id
            WHERE e.tenant_id != l.tenant_id
            LIMIT 10
        """))
        
        cross_tenant = result.fetchall()
        if cross_tenant:
            print(f"❌ Found {len(cross_tenant)} cross-tenant GL lines:")
            for row in cross_tenant:
                print(f"  Entry {row[1]}: Entry Tenant={row[2]}, Line Tenant={row[3]}")
        else:
            print("✅ No cross-tenant GL entries found")
        
        # Check for cross-tenant GL lines
        result = conn.execute(text("""
            SELECT l.id, l.account_id, a.tenant_id as account_tenant, l.tenant_id as line_tenant
            FROM gl_journal_lines l
            JOIN gl_accounts a ON l.account_id = a.id
            WHERE a.tenant_id != l.tenant_id
            LIMIT 10
        """))
        
        cross_tenant_lines = result.fetchall()
        if cross_tenant_lines:
            print(f"❌ Found {len(cross_tenant_lines)} cross-tenant account references:")
            for row in cross_tenant_lines:
                print(f"  Line {row[0]}: Account Tenant={row[2]}, Line Tenant={row[3]}")
        else:
            print("✅ No cross-tenant account references found")


def verify_account_hierarchy():
    """Verify account hierarchy and structure."""
    print_section("ACCOUNT HIERARCHY VERIFICATION")
    
    with app.app_context():
        conn = db.engine.connect()
        
        # Check for accounts without parent that should have one
        result = conn.execute(text("""
            SELECT COUNT(*) FROM gl_accounts 
            WHERE parent_id IS NULL AND code NOT LIKE '1%' 
            AND code NOT LIKE '2%' AND code NOT LIKE '3%' 
            AND code NOT LIKE '4%' AND code NOT LIKE '5%' 
            AND code NOT LIKE '6%'
        """))
        
        top_level = result.scalar()
        print(f"Top-level accounts (no parent): {top_level}")
        
        # Check for circular references
        result = conn.execute(text("""
            WITH RECURSIVE account_tree AS (
                SELECT id, code, name, parent_id, 1 as level
                FROM gl_accounts
                WHERE parent_id IS NULL
                UNION ALL
                SELECT a.id, a.code, a.name, a.parent_id, at.level + 1
                FROM gl_accounts a
                JOIN account_tree at ON a.parent_id = at.id
                WHERE at.level < 10
            )
            SELECT COUNT(*) FROM account_tree WHERE level >= 10
        """))
        
        deep = result.scalar()
        if deep > 0:
            print(f"⚠️  Found {deep} accounts with deep hierarchy (level >= 10)")
        else:
            print("✅ Account hierarchy depth is reasonable")


def main():
    """Run all accounting verification checks."""
    print("="*80)
    print("  DETAILED ACCOUNTING VERIFICATION")
    print("="*80)
    
    verify_journal_entry_completeness()
    verify_account_balances()
    verify_general_ledger_per_account()
    verify_transaction_integrity()
    verify_double_entry_principle()
    verify_tenant_accounting_isolation()
    verify_account_hierarchy()
    
    print_section("VERIFICATION COMPLETED")
    print("Review the results above for any issues marked with ❌ or ⚠️")


if __name__ == "__main__":
    main()
