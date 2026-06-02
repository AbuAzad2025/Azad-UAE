"""Seed GL entries for inactive accounts to activate all GL accounts per tenant."""
import os, sys, random
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["DATABASE_URL"] = "postgresql+psycopg2://postgres:123@localhost:5432/azad_uae"
os.environ["SKIP_SYSTEM_INTEGRITY"] = "1"

from app import create_app
from extensions import db
from models import GLAccount, Tenant
from sqlalchemy import text
from decimal import Decimal

app = create_app()


def get_tenant_ids():
    """Get all tenant IDs."""
    tenants = Tenant.query.filter_by(is_active=True).all()
    return [(t.id, t.slug) for t in tenants]


def seed():
    """Add GL entries for inactive accounts per tenant using raw SQL."""
    with app.app_context():
        tenants = get_tenant_ids()
        print(f"Found {len(tenants)} active tenants")
        
        conn = db.engine.connect()
        
        for tenant_id, tenant_slug in tenants:
            print(f"\nProcessing tenant: {tenant_slug} (ID: {tenant_id})")
            
            # Get inactive accounts for this tenant
            result = conn.execute(text("""
                SELECT a.id, a.code, a.name, a.type
                FROM gl_accounts a
                WHERE a.tenant_id = :tenant_id
                AND NOT EXISTS (
                    SELECT 1 FROM gl_journal_lines l WHERE l.account_id = a.id
                )
            """), {"tenant_id": tenant_id})
            
            inactive = result.fetchall()
            
            if not inactive:
                print(f"  No inactive accounts found")
                continue
            
            print(f"  Found {len(inactive)} inactive accounts")
            
            # Find cash account for balancing
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
            
            # Create GL entries using raw SQL
            count = 0
            for acc_id, acc_code, acc_name, acc_type in inactive:
                # Determine debit/credit based on account type
                if acc_type in ['asset', 'expense']:
                    debit_amount = Decimal(str(random.randint(1000, 50000)))
                    credit_amount = Decimal('0')
                else:  # liability, equity, revenue
                    debit_amount = Decimal('0')
                    credit_amount = Decimal(str(random.randint(1000, 50000)))
                
                # Calculate totals
                total_debit = debit_amount + (credit_amount if acc_type in ['asset', 'expense'] else Decimal('0'))
                total_credit = credit_amount + (debit_amount if acc_type in ['asset', 'expense'] else Decimal('0'))
                
                # Insert GL entry
                entry_result = conn.execute(text("""
                    INSERT INTO gl_journal_entries 
                    (tenant_id, entry_number, entry_date, description, reference_type, entry_type, 
                     currency, exchange_rate, total_debit, total_credit, is_posted, created_at)
                    VALUES 
                    (:tenant_id, :entry_number, NOW(), :description, 'adjustment', 'manual',
                     'AED', 1.0, :total_debit, :total_credit, true, NOW())
                    RETURNING id
                """), {
                    "tenant_id": tenant_id,
                    "entry_number": f"ADJ-{tenant_slug.upper()}-{count+1:04d}",
                    "description": f"Activation entry for account {acc_code} - {acc_name}",
                    "total_debit": total_debit,
                    "total_credit": total_credit
                })
                
                entry_id = entry_result.fetchone()[0]
                
                # Insert line for the inactive account
                conn.execute(text("""
                    INSERT INTO gl_journal_lines 
                    (tenant_id, entry_id, account_id, description, debit, credit, amount_aed)
                    VALUES 
                    (:tenant_id, :entry_id, :account_id, :description, :debit, :credit, :amount_aed)
                """), {
                    "tenant_id": tenant_id,
                    "entry_id": entry_id,
                    "account_id": acc_id,
                    "description": f"Activation of {acc_name}",
                    "debit": debit_amount,
                    "credit": credit_amount,
                    "amount_aed": debit_amount + credit_amount
                })
                
                # Insert balancing line
                if acc_type in ['asset', 'expense']:
                    # Credit cash to balance
                    conn.execute(text("""
                        INSERT INTO gl_journal_lines 
                        (tenant_id, entry_id, account_id, description, debit, credit, amount_aed)
                        VALUES 
                        (:tenant_id, :entry_id, :account_id, :description, 0, :credit, :amount_aed)
                    """), {
                        "tenant_id": tenant_id,
                        "entry_id": entry_id,
                        "account_id": cash_account_id,
                        "description": f"Balancing entry for {acc_name}",
                        "credit": debit_amount,
                        "amount_aed": debit_amount
                    })
                else:
                    # Debit cash to balance
                    conn.execute(text("""
                        INSERT INTO gl_journal_lines 
                        (tenant_id, entry_id, account_id, description, debit, credit, amount_aed)
                        VALUES 
                        (:tenant_id, :entry_id, :account_id, :description, :debit, 0, :amount_aed)
                    """), {
                        "tenant_id": tenant_id,
                        "entry_id": entry_id,
                        "account_id": cash_account_id,
                        "description": f"Balancing entry for {acc_name}",
                        "debit": credit_amount,
                        "amount_aed": credit_amount
                    })
                
                count += 1
                print(f"  Activated: {acc_code} - {acc_name}")
            
            conn.commit()
            print(f"  Created {count} activation entries for {tenant_slug}")
        
        print("\n✅ Inactive accounts activation completed successfully")


if __name__ == "__main__":
    seed()
