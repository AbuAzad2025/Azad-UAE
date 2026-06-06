"""Check payroll records in the database."""
import os, sys
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)
os.chdir(project_root)
os.environ["DATABASE_URL"] = "postgresql+psycopg2://postgres:123@localhost:5432/azad_uae"
os.environ["SKIP_SYSTEM_INTEGRITY"] = "1"

from app import create_app
from extensions import db
from sqlalchemy import text

app = create_app()


def check_payroll():
    """Check payroll records."""
    with app.app_context():
        conn = db.engine.connect()
        
        # Check employees
        try:
            result = conn.execute(text("SELECT COUNT(*) FROM employees"))
            emp_count = result.scalar()
            print(f"Employees: {emp_count}")
        except Exception as e:
            print(f"Error checking employees: {e}")
        
        # Check payroll transactions
        try:
            result = conn.execute(text("SELECT COUNT(*) FROM payroll_transactions"))
            count = result.scalar()
            print(f"Payroll transactions: {count}")
            
            if count > 0:
                result = conn.execute(text("""
                    SELECT p.id, p.employee_id, p.tenant_id, p.month, p.year, p.net_salary, p.payment_date
                    FROM payroll_transactions p
                    LIMIT 10
                """))
                
                print("\nSample payroll transactions:")
                print(f"{'ID':<5} {'Employee':<10} {'Tenant':<10} {'Month':<6} {'Year':<6} {'Net Salary':<15} {'Date':<15}")
                print("-" * 70)
                for row in result:
                    print(f"{row[0]:<5} {row[1]:<10} {row[2]:<10} {row[3]:<6} {row[4]:<6} {row[5]:<15.2f} {row[6]}")
        except Exception as e:
            print(f"Error checking payroll transactions: {e}")
        
        # Check salary advances
        try:
            result = conn.execute(text("SELECT COUNT(*) FROM salary_advances"))
            adv_count = result.scalar()
            print(f"Salary advances: {adv_count}")
        except Exception as e:
            print(f"Error checking salary advances: {e}")
        
        # Check if payroll has GL entries
        try:
            result = conn.execute(text("""
                SELECT COUNT(*) FROM payroll_transactions p
                LEFT JOIN gl_journal_entries e ON e.reference_id = p.id AND e.reference_type = 'payroll'
                WHERE e.id IS NULL
            """))
            without_gl = result.scalar()
            print(f"Payroll transactions without GL entries: {without_gl}")
        except Exception as e:
            print(f"Error checking payroll GL entries: {e}")


if __name__ == "__main__":
    check_payroll()
