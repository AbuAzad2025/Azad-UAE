"""Generate GL entries from existing transactions manually."""
import os, sys, random
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)
os.chdir(project_root)
os.environ["DATABASE_URL"] = "postgresql+psycopg2://postgres:123@localhost:5432/azad_uae"
os.environ["SKIP_SYSTEM_INTEGRITY"] = "1"

from app import create_app
from extensions import db
from sqlalchemy import text
from decimal import Decimal
from datetime import datetime

app = create_app()


def get_gl_account(conn, tenant_id, account_type):
    """Get a GL account for a tenant by type."""
    result = conn.execute(text("""
        SELECT id FROM gl_accounts 
        WHERE tenant_id = :tenant_id AND type = :type
        LIMIT 1
    """), {"tenant_id": tenant_id, "type": account_type})
    row = result.fetchone()
    return row[0] if row else None


def generate_gl_for_sales():
    """Generate GL entries for sales without GL entries."""
    with app.app_context():
        conn = db.engine.connect()
        
        # Get sales without GL entries
        result = conn.execute(text("""
            SELECT s.id, s.sale_number, s.tenant_id, s.total_amount, s.customer_id, s.sale_date
            FROM sales s
            LEFT JOIN gl_journal_entries e ON e.reference_id = s.id AND e.reference_type = 'sale'
            WHERE e.id IS NULL
        """))
        
        sales = result.fetchall()
        print(f"Found {len(sales)} sales without GL entries")
        
        count = 0
        for sale_id, sale_number, tenant_id, total_amount, customer_id, sale_date in sales:
            # Get accounts
            revenue_acc = get_gl_account(conn, tenant_id, 'revenue')
            cash_acc = get_gl_account(conn, tenant_id, 'asset')
            ar_acc = get_gl_account(conn, tenant_id, 'asset')
            
            if not revenue_acc or not cash_acc:
                print(f"  Skipping {sale_number} - missing accounts")
                continue
            
            # Create GL entry
            entry_result = conn.execute(text("""
                INSERT INTO gl_journal_entries 
                (tenant_id, entry_number, entry_date, description, reference_type, reference_id, entry_type, 
                 currency, exchange_rate, total_debit, total_credit, is_posted, created_at)
                VALUES 
                (:tenant_id, :entry_number, :entry_date, :description, 'sale', :reference_id, 'manual',
                 'AED', 1.0, :total_debit, :total_credit, true, NOW())
                RETURNING id
            """), {
                "tenant_id": tenant_id,
                "entry_number": f"GL-{sale_number}",
                "entry_date": sale_date or datetime.now(),
                "description": f"Sale {sale_number}",
                "reference_id": sale_id,
                "total_debit": total_amount,
                "total_credit": total_amount
            })
            
            entry_id = entry_result.fetchone()[0]
            
            # Debit Cash/AR
            conn.execute(text("""
                INSERT INTO gl_journal_lines 
                (tenant_id, entry_id, account_id, description, debit, credit, amount_aed)
                VALUES 
                (:tenant_id, :entry_id, :account_id, :description, :debit, 0, :amount_aed)
            """), {
                "tenant_id": tenant_id,
                "entry_id": entry_id,
                "account_id": cash_acc,
                "description": f"Sale {sale_number}",
                "debit": total_amount,
                "amount_aed": total_amount
            })
            
            # Credit Revenue
            conn.execute(text("""
                INSERT INTO gl_journal_lines 
                (tenant_id, entry_id, account_id, description, debit, credit, amount_aed)
                VALUES 
                (:tenant_id, :entry_id, :account_id, :description, 0, :credit, :amount_aed)
            """), {
                "tenant_id": tenant_id,
                "entry_id": entry_id,
                "account_id": revenue_acc,
                "description": f"Sale {sale_number}",
                "credit": total_amount,
                "amount_aed": total_amount
            })
            
            count += 1
            if count % 10 == 0:
                conn.commit()
        
        conn.commit()
        print(f"✅ Created {count} GL entries for sales")


def generate_gl_for_purchases():
    """Generate GL entries for purchases without GL entries."""
    with app.app_context():
        conn = db.engine.connect()
        
        result = conn.execute(text("""
            SELECT p.id, p.purchase_number, p.tenant_id, p.total_amount, p.supplier_id, p.purchase_date
            FROM purchases p
            LEFT JOIN gl_journal_entries e ON e.reference_id = p.id AND e.reference_type = 'purchase'
            WHERE e.id IS NULL
        """))
        
        purchases = result.fetchall()
        print(f"Found {len(purchases)} purchases without GL entries")
        
        count = 0
        for pur_id, pur_number, tenant_id, total_amount, supplier_id, pur_date in purchases:
            expense_acc = get_gl_account(conn, tenant_id, 'expense')
            cash_acc = get_gl_account(conn, tenant_id, 'asset')
            ap_acc = get_gl_account(conn, tenant_id, 'liability')
            
            if not expense_acc or not cash_acc:
                print(f"  Skipping {pur_number} - missing accounts")
                continue
            
            entry_result = conn.execute(text("""
                INSERT INTO gl_journal_entries 
                (tenant_id, entry_number, entry_date, description, reference_type, reference_id, entry_type, 
                 currency, exchange_rate, total_debit, total_credit, is_posted, created_at)
                VALUES 
                (:tenant_id, :entry_number, :entry_date, :description, 'purchase', :reference_id, 'manual',
                 'AED', 1.0, :total_debit, :total_credit, true, NOW())
                RETURNING id
            """), {
                "tenant_id": tenant_id,
                "entry_number": f"GL-{pur_number}",
                "entry_date": pur_date or datetime.now(),
                "description": f"Purchase {pur_number}",
                "reference_id": pur_id,
                "total_debit": total_amount,
                "total_credit": total_amount
            })
            
            entry_id = entry_result.fetchone()[0]
            
            # Debit Expense
            conn.execute(text("""
                INSERT INTO gl_journal_lines 
                (tenant_id, entry_id, account_id, description, debit, credit, amount_aed)
                VALUES 
                (:tenant_id, :entry_id, :account_id, :description, :debit, 0, :amount_aed)
            """), {
                "tenant_id": tenant_id,
                "entry_id": entry_id,
                "account_id": expense_acc,
                "description": f"Purchase {pur_number}",
                "debit": total_amount,
                "amount_aed": total_amount
            })
            
            # Credit Cash/AP
            conn.execute(text("""
                INSERT INTO gl_journal_lines 
                (tenant_id, entry_id, account_id, description, debit, credit, amount_aed)
                VALUES 
                (:tenant_id, :entry_id, :account_id, :description, 0, :credit, :amount_aed)
            """), {
                "tenant_id": tenant_id,
                "entry_id": entry_id,
                "account_id": cash_acc,
                "description": f"Purchase {pur_number}",
                "credit": total_amount,
                "amount_aed": total_amount
            })
            
            count += 1
            if count % 10 == 0:
                conn.commit()
        
        conn.commit()
        print(f"✅ Created {count} GL entries for purchases")


def generate_gl_for_payments():
    """Generate GL entries for payments without GL entries."""
    with app.app_context():
        conn = db.engine.connect()
        
        result = conn.execute(text("""
            SELECT p.id, p.payment_number, p.tenant_id, p.amount, p.payment_date
            FROM payments p
            LEFT JOIN gl_journal_entries e ON e.reference_id = p.id AND e.reference_type = 'payment'
            WHERE e.id IS NULL
        """))
        
        payments = result.fetchall()
        print(f"Found {len(payments)} payments without GL entries")
        
        count = 0
        for pay_id, pay_number, tenant_id, amount, pay_date in payments:
            liability_acc = get_gl_account(conn, tenant_id, 'liability')
            cash_acc = get_gl_account(conn, tenant_id, 'asset')
            
            if not liability_acc or not cash_acc:
                print(f"  Skipping {pay_number} - missing accounts")
                continue
            
            entry_result = conn.execute(text("""
                INSERT INTO gl_journal_entries 
                (tenant_id, entry_number, entry_date, description, reference_type, reference_id, entry_type, 
                 currency, exchange_rate, total_debit, total_credit, is_posted, created_at)
                VALUES 
                (:tenant_id, :entry_number, :entry_date, :description, 'payment', :reference_id, 'manual',
                 'AED', 1.0, :total_debit, :total_credit, true, NOW())
                RETURNING id
            """), {
                "tenant_id": tenant_id,
                "entry_number": f"GL-{pay_number}",
                "entry_date": pay_date or datetime.now(),
                "description": f"Payment {pay_number}",
                "reference_id": pay_id,
                "total_debit": amount,
                "total_credit": amount
            })
            
            entry_id = entry_result.fetchone()[0]
            
            # Debit Liability
            conn.execute(text("""
                INSERT INTO gl_journal_lines 
                (tenant_id, entry_id, account_id, description, debit, credit, amount_aed)
                VALUES 
                (:tenant_id, :entry_id, :account_id, :description, :debit, 0, :amount_aed)
            """), {
                "tenant_id": tenant_id,
                "entry_id": entry_id,
                "account_id": liability_acc,
                "description": f"Payment {pay_number}",
                "debit": amount,
                "amount_aed": amount
            })
            
            # Credit Cash
            conn.execute(text("""
                INSERT INTO gl_journal_lines 
                (tenant_id, entry_id, account_id, description, debit, credit, amount_aed)
                VALUES 
                (:tenant_id, :entry_id, :account_id, :description, 0, :credit, :amount_aed)
            """), {
                "tenant_id": tenant_id,
                "entry_id": entry_id,
                "account_id": cash_acc,
                "description": f"Payment {pay_number}",
                "credit": amount,
                "amount_aed": amount
            })
            
            count += 1
            if count % 10 == 0:
                conn.commit()
        
        conn.commit()
        print(f"✅ Created {count} GL entries for payments")


def generate_gl_for_receipts():
    """Generate GL entries for receipts without GL entries."""
    with app.app_context():
        conn = db.engine.connect()
        
        result = conn.execute(text("""
            SELECT r.id, r.receipt_number, r.tenant_id, r.amount, r.receipt_date
            FROM receipts r
            LEFT JOIN gl_journal_entries e ON e.reference_id = r.id AND e.reference_type = 'receipt'
            WHERE e.id IS NULL
        """))
        
        receipts = result.fetchall()
        print(f"Found {len(receipts)} receipts without GL entries")
        
        count = 0
        for rec_id, rec_number, tenant_id, amount, rec_date in receipts:
            asset_acc = get_gl_account(conn, tenant_id, 'asset')
            cash_acc = get_gl_account(conn, tenant_id, 'asset')
            
            if not asset_acc or not cash_acc:
                print(f"  Skipping {rec_number} - missing accounts")
                continue
            
            entry_result = conn.execute(text("""
                INSERT INTO gl_journal_entries 
                (tenant_id, entry_number, entry_date, description, reference_type, reference_id, entry_type, 
                 currency, exchange_rate, total_debit, total_credit, is_posted, created_at)
                VALUES 
                (:tenant_id, :entry_number, :entry_date, :description, 'receipt', :reference_id, 'manual',
                 'AED', 1.0, :total_debit, :total_credit, true, NOW())
                RETURNING id
            """), {
                "tenant_id": tenant_id,
                "entry_number": f"GL-{rec_number}",
                "entry_date": rec_date or datetime.now(),
                "description": f"Receipt {rec_number}",
                "reference_id": rec_id,
                "total_debit": amount,
                "total_credit": amount
            })
            
            entry_id = entry_result.fetchone()[0]
            
            # Debit Cash
            conn.execute(text("""
                INSERT INTO gl_journal_lines 
                (tenant_id, entry_id, account_id, description, debit, credit, amount_aed)
                VALUES 
                (:tenant_id, :entry_id, :account_id, :description, :debit, 0, :amount_aed)
            """), {
                "tenant_id": tenant_id,
                "entry_id": entry_id,
                "account_id": cash_acc,
                "description": f"Receipt {rec_number}",
                "debit": amount,
                "amount_aed": amount
            })
            
            # Credit AR/Asset
            conn.execute(text("""
                INSERT INTO gl_journal_lines 
                (tenant_id, entry_id, account_id, description, debit, credit, amount_aed)
                VALUES 
                (:tenant_id, :entry_id, :account_id, :description, 0, :credit, :amount_aed)
            """), {
                "tenant_id": tenant_id,
                "entry_id": entry_id,
                "account_id": asset_acc,
                "description": f"Receipt {rec_number}",
                "credit": amount,
                "amount_aed": amount
            })
            
            count += 1
            if count % 10 == 0:
                conn.commit()
        
        conn.commit()
        print(f"✅ Created {count} GL entries for receipts")


def generate_gl_for_expenses():
    """Generate GL entries for expenses without GL entries."""
    with app.app_context():
        conn = db.engine.connect()
        
        result = conn.execute(text("""
            SELECT e.id, e.description, e.tenant_id, e.amount, e.expense_date
            FROM expenses e
            LEFT JOIN gl_journal_entries ge ON ge.reference_id = e.id AND ge.reference_type = 'expense'
            WHERE ge.id IS NULL
        """))
        
        expenses = result.fetchall()
        print(f"Found {len(expenses)} expenses without GL entries")
        
        count = 0
        for exp_id, description, tenant_id, amount, exp_date in expenses:
            expense_acc = get_gl_account(conn, tenant_id, 'expense')
            cash_acc = get_gl_account(conn, tenant_id, 'asset')
            
            if not expense_acc or not cash_acc:
                print(f"  Skipping expense {exp_id} - missing accounts")
                continue
            
            entry_result = conn.execute(text("""
                INSERT INTO gl_journal_entries 
                (tenant_id, entry_number, entry_date, description, reference_type, reference_id, entry_type, 
                 currency, exchange_rate, total_debit, total_credit, is_posted, created_at)
                VALUES 
                (:tenant_id, :entry_number, :entry_date, :description, 'expense', :reference_id, 'manual',
                 'AED', 1.0, :total_debit, :total_credit, true, NOW())
                RETURNING id
            """), {
                "tenant_id": tenant_id,
                "entry_number": f"GL-EXP-{count+1:04d}",
                "entry_date": exp_date or datetime.now(),
                "description": description or f"Expense {exp_id}",
                "reference_id": exp_id,
                "total_debit": amount,
                "total_credit": amount
            })
            
            entry_id = entry_result.fetchone()[0]
            
            # Debit Expense
            conn.execute(text("""
                INSERT INTO gl_journal_lines 
                (tenant_id, entry_id, account_id, description, debit, credit, amount_aed)
                VALUES 
                (:tenant_id, :entry_id, :account_id, :description, :debit, 0, :amount_aed)
            """), {
                "tenant_id": tenant_id,
                "entry_id": entry_id,
                "account_id": expense_acc,
                "description": description or f"Expense {exp_id}",
                "debit": amount,
                "amount_aed": amount
            })
            
            # Credit Cash
            conn.execute(text("""
                INSERT INTO gl_journal_lines 
                (tenant_id, entry_id, account_id, description, debit, credit, amount_aed)
                VALUES 
                (:tenant_id, :entry_id, :account_id, :description, 0, :credit, :amount_aed)
            """), {
                "tenant_id": tenant_id,
                "entry_id": entry_id,
                "account_id": cash_acc,
                "description": description or f"Expense {exp_id}",
                "credit": amount,
                "amount_aed": amount
            })
            
            count += 1
            if count % 10 == 0:
                conn.commit()
        
        conn.commit()
        print(f"✅ Created {count} GL entries for expenses")


def generate_gl_for_payroll():
    """Generate GL entries for payroll transactions without GL entries."""
    with app.app_context():
        conn = db.engine.connect()
        
        result = conn.execute(text("""
            SELECT p.id, p.employee_id, p.tenant_id, p.net_salary, p.payment_date, p.month, p.year
            FROM payroll_transactions p
            LEFT JOIN gl_journal_entries e ON e.reference_id = p.id AND e.reference_type = 'payroll'
            WHERE e.id IS NULL
        """))
        
        payroll = result.fetchall()
        print(f"Found {len(payroll)} payroll transactions without GL entries")
        
        count = 0
        for pay_id, emp_id, tenant_id, net_salary, pay_date, month, year in payroll:
            expense_acc = get_gl_account(conn, tenant_id, 'expense')
            cash_acc = get_gl_account(conn, tenant_id, 'asset')
            liability_acc = get_gl_account(conn, tenant_id, 'liability')
            
            if not expense_acc or not cash_acc:
                print(f"  Skipping payroll {pay_id} - missing accounts")
                continue
            
            entry_result = conn.execute(text("""
                INSERT INTO gl_journal_entries 
                (tenant_id, entry_number, entry_date, description, reference_type, reference_id, entry_type, 
                 currency, exchange_rate, total_debit, total_credit, is_posted, created_at)
                VALUES 
                (:tenant_id, :entry_number, :entry_date, :description, 'payroll', :reference_id, 'manual',
                 'AED', 1.0, :total_debit, :total_credit, true, NOW())
                RETURNING id
            """), {
                "tenant_id": tenant_id,
                "entry_number": f"GL-PAY-{count+1:04d}",
                "entry_date": pay_date or datetime.now(),
                "description": f"Payroll {month}/{year} - Employee {emp_id}",
                "reference_id": pay_id,
                "total_debit": net_salary,
                "total_credit": net_salary
            })
            
            entry_id = entry_result.fetchone()[0]
            
            # Debit Salary Expense
            conn.execute(text("""
                INSERT INTO gl_journal_lines 
                (tenant_id, entry_id, account_id, description, debit, credit, amount_aed)
                VALUES 
                (:tenant_id, :entry_id, :account_id, :description, :debit, 0, :amount_aed)
            """), {
                "tenant_id": tenant_id,
                "entry_id": entry_id,
                "account_id": expense_acc,
                "description": f"Payroll {month}/{year}",
                "debit": net_salary,
                "amount_aed": net_salary
            })
            
            # Credit Cash
            conn.execute(text("""
                INSERT INTO gl_journal_lines 
                (tenant_id, entry_id, account_id, description, debit, credit, amount_aed)
                VALUES 
                (:tenant_id, :entry_id, :account_id, :description, 0, :credit, :amount_aed)
            """), {
                "tenant_id": tenant_id,
                "entry_id": entry_id,
                "account_id": cash_acc,
                "description": f"Payroll {month}/{year}",
                "credit": net_salary,
                "amount_aed": net_salary
            })
            
            count += 1
            if count % 10 == 0:
                conn.commit()
        
        conn.commit()
        print(f"✅ Created {count} GL entries for payroll")


def generate_gl_for_stock_movements():
    """Generate GL entries for stock movements without GL entries."""
    with app.app_context():
        conn = db.engine.connect()
        
        result = conn.execute(text("""
            SELECT s.id, s.tenant_id, s.product_id, s.quantity, s.movement_type, s.created_at
            FROM stock_movements s
            LEFT JOIN gl_journal_entries e ON e.reference_id = s.id AND e.reference_type = 'stock_movement'
            WHERE e.id IS NULL
        """))
        
        movements = result.fetchall()
        print(f"Found {len(movements)} stock movements without GL entries")
        
        count = 0
        for move_id, tenant_id, product_id, quantity, move_type, move_date in movements:
            # Skip zero quantity movements
            if quantity == 0:
                continue
            
            inventory_acc = get_gl_account(conn, tenant_id, 'asset')
            cash_acc = get_gl_account(conn, tenant_id, 'asset')
            expense_acc = get_gl_account(conn, tenant_id, 'expense')
            
            if not inventory_acc or not cash_acc:
                print(f"  Skipping movement {move_id} - missing accounts")
                continue
            
            # Calculate amount (simplified - should use product cost)
            amount = Decimal(str(abs(quantity))) * Decimal("100")
            
            entry_result = conn.execute(text("""
                INSERT INTO gl_journal_entries 
                (tenant_id, entry_number, entry_date, description, reference_type, reference_id, entry_type, 
                 currency, exchange_rate, total_debit, total_credit, is_posted, created_at)
                VALUES 
                (:tenant_id, :entry_number, :entry_date, :description, 'stock_movement', :reference_id, 'manual',
                 'AED', 1.0, :total_debit, :total_credit, true, NOW())
                RETURNING id
            """), {
                "tenant_id": tenant_id,
                "entry_number": f"GL-STK-{count+1:04d}",
                "entry_date": move_date or datetime.now(),
                "description": f"Stock movement {move_type} - Product {product_id}",
                "reference_id": move_id,
                "total_debit": amount,
                "total_credit": amount
            })
            
            entry_id = entry_result.fetchone()[0]
            
            if move_type in ['in', 'purchase', 'return']:
                # Debit Inventory, Credit Cash/AP
                conn.execute(text("""
                    INSERT INTO gl_journal_lines 
                    (tenant_id, entry_id, account_id, description, debit, credit, amount_aed)
                    VALUES 
                    (:tenant_id, :entry_id, :account_id, :description, :debit, 0, :amount_aed)
                """), {
                    "tenant_id": tenant_id,
                    "entry_id": entry_id,
                    "account_id": inventory_acc,
                    "description": f"Stock {move_type}",
                    "debit": amount,
                    "amount_aed": amount
                })
                
                conn.execute(text("""
                    INSERT INTO gl_journal_lines 
                    (tenant_id, entry_id, account_id, description, debit, credit, amount_aed)
                    VALUES 
                    (:tenant_id, :entry_id, :account_id, :description, 0, :credit, :amount_aed)
                """), {
                    "tenant_id": tenant_id,
                    "entry_id": entry_id,
                    "account_id": cash_acc,
                    "description": f"Stock {move_type}",
                    "credit": amount,
                    "amount_aed": amount
                })
            else:
                # Credit Inventory, Debit COGS/Expense
                conn.execute(text("""
                    INSERT INTO gl_journal_lines 
                    (tenant_id, entry_id, account_id, description, debit, credit, amount_aed)
                    VALUES 
                    (:tenant_id, :entry_id, :account_id, :description, :debit, 0, :amount_aed)
                """), {
                    "tenant_id": tenant_id,
                    "entry_id": entry_id,
                    "account_id": expense_acc,
                    "description": f"Stock {move_type}",
                    "debit": amount,
                    "amount_aed": amount
                })
                
                conn.execute(text("""
                    INSERT INTO gl_journal_lines 
                    (tenant_id, entry_id, account_id, description, debit, credit, amount_aed)
                    VALUES 
                    (:tenant_id, :entry_id, :account_id, :description, 0, :credit, :amount_aed)
                """), {
                    "tenant_id": tenant_id,
                    "entry_id": entry_id,
                    "account_id": inventory_acc,
                    "description": f"Stock {move_type}",
                    "credit": amount,
                    "amount_aed": amount
                })
            
            count += 1
            if count % 10 == 0:
                conn.commit()
        
        conn.commit()
        print(f"✅ Created {count} GL entries for stock movements")


def main():
    """Generate GL entries for all transactions."""
    print("="*80)
    print("  GENERATING GL ENTRIES FROM TRANSACTIONS")
    print("="*80)
    
    generate_gl_for_sales()
    generate_gl_for_purchases()
    generate_gl_for_payments()
    generate_gl_for_receipts()
    generate_gl_for_expenses()
    generate_gl_for_payroll()
    generate_gl_for_stock_movements()
    
    print("\n✅ GL entries generation completed")


if __name__ == "__main__":
    main()
