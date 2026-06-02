"""Fix unbalanced GL entries by adding missing balancing lines."""
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


def fix_unbalanced_entries():
    """Fix unbalanced GL entries by adding missing debit lines."""
    with app.app_context():
        conn = db.engine.connect()
        
        # Get unbalanced entries
        result = conn.execute(text("""
            SELECT id, entry_number, tenant_id, total_debit, total_credit, 
                   total_debit - total_credit as difference
            FROM gl_journal_entries
            WHERE ABS(total_debit - total_credit) > 0.01
            ORDER BY difference DESC
        """))
        
        unbalanced = result.fetchall()
        
        if not unbalanced:
            print("No unbalanced entries found")
            return
        
        print(f"Found {len(unbalanced)} unbalanced entries")
        
        for entry_id, entry_number, tenant_id, total_debit, total_credit, difference in unbalanced:
            print(f"\nFixing entry: {entry_number}")
            print(f"  Debit: {total_debit}, Credit: {total_credit}, Diff: {difference}")
            
            # Find cash account for this tenant
            cash_result = conn.execute(text("""
                SELECT id FROM gl_accounts 
                WHERE tenant_id = :tenant_id AND code = '1100'
                LIMIT 1
            """), {"tenant_id": tenant_id})
            
            cash_row = cash_result.fetchone()
            if not cash_row:
                # Try any asset account
                cash_result = conn.execute(text("""
                    SELECT id FROM gl_accounts 
                    WHERE tenant_id = :tenant_id AND type = 'asset'
                    LIMIT 1
                """), {"tenant_id": tenant_id})
                cash_row = cash_result.fetchone()
            
            if not cash_row:
                print(f"  Skipping - no balancing account found")
                continue
            
            cash_account_id = cash_row[0]
            
            # Add missing debit line
            if difference < 0:  # Credit > Debit, need to add debit
                debit_amount = abs(difference)
                conn.execute(text("""
                    INSERT INTO gl_journal_lines 
                    (tenant_id, entry_id, account_id, description, debit, credit, amount_aed)
                    VALUES 
                    (:tenant_id, :entry_id, :account_id, :description, :debit, 0, :amount_aed)
                """), {
                    "tenant_id": tenant_id,
                    "entry_id": entry_id,
                    "account_id": cash_account_id,
                    "description": f"Balancing entry for {entry_number}",
                    "debit": debit_amount,
                    "amount_aed": debit_amount
                })
                
                # Update entry totals
                conn.execute(text("""
                    UPDATE gl_journal_entries 
                    SET total_debit = total_debit + :debit
                    WHERE id = :entry_id
                """), {
                    "debit": debit_amount,
                    "entry_id": entry_id
                })
                
                print(f"  Added debit line: {debit_amount}")
        
        conn.commit()
        print("\n✅ Fixed all unbalanced entries")


if __name__ == "__main__":
    fix_unbalanced_entries()
