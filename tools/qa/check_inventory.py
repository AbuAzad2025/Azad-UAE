"""Check inventory/stock data in the database."""
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


def check_inventory():
    """Check inventory/stock records."""
    with app.app_context():
        conn = db.engine.connect()
        
        # Check products
        try:
            result = conn.execute(text("SELECT COUNT(*) FROM products"))
            prod_count = result.scalar()
            print(f"Products: {prod_count}")
        except Exception as e:
            print(f"Error checking products: {e}")
        
        # Check product serials
        try:
            result = conn.execute(text("SELECT COUNT(*) FROM product_serials"))
            serial_count = result.scalar()
            print(f"Product Serials: {serial_count}")
        except Exception as e:
            print(f"Error checking product serials: {e}")
        
        # Check stock movements
        try:
            result = conn.execute(text("SELECT COUNT(*) FROM stock_movements"))
            movement_count = result.scalar()
            print(f"Stock Movements: {movement_count}")
        except Exception as e:
            print(f"Error checking stock movements: {e}")
        
        # Check warehouses
        try:
            result = conn.execute(text("SELECT COUNT(*) FROM warehouses"))
            wh_count = result.scalar()
            print(f"Warehouses: {wh_count}")
        except Exception as e:
            print(f"Error checking warehouses: {e}")
        
        # Check if stock movements have GL entries
        try:
            result = conn.execute(text("""
                SELECT COUNT(*) FROM stock_movements s
                LEFT JOIN gl_journal_entries e ON e.reference_id = s.id AND e.reference_type = 'stock_movement'
                WHERE e.id IS NULL
            """))
            without_gl = result.scalar()
            print(f"Stock movements without GL entries: {without_gl}")
        except Exception as e:
            print(f"Error checking stock movement GL entries: {e}")


if __name__ == "__main__":
    check_inventory()
