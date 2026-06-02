"""Update customer and supplier balances based on transactions."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["DATABASE_URL"] = "postgresql+psycopg2://postgres:123@localhost:5432/azad_uae"
os.environ["SKIP_SYSTEM_INTEGRITY"] = "1"

from app import create_app
from extensions import db
from models import Customer, Supplier, Sale, Purchase, Receipt, Payment
from decimal import Decimal

app = create_app()


def seed():
    with app.app_context():
        # Update customer balances based on sales and receipts
        print("Updating customer balances...")
        customers = Customer.query.all()
        for cust in customers:
            # Total sales amount
            sales_total = db.session.query(db.func.sum(Sale.total_amount)).filter_by(
                tenant_id=cust.tenant_id, customer_id=cust.id
            ).scalar() or Decimal("0")
            
            # Total receipts (payments received)
            receipts_total = db.session.query(db.func.sum(Receipt.amount)).filter_by(
                tenant_id=cust.tenant_id, customer_id=cust.id
            ).scalar() or Decimal("0")
            
            # Balance = sales - receipts (positive = customer owes us)
            balance = sales_total - receipts_total
            cust.balance = balance
            cust.total_purchases = sales_total
        db.session.commit()
        print(f"Updated {len(customers)} customer balances")
        
        # Update supplier balances based on purchases and payments
        print("Updating supplier balances...")
        suppliers = Supplier.query.all()
        for supp in suppliers:
            # Total purchases amount
            purchases_total = db.session.query(db.func.sum(Purchase.total_amount)).filter_by(
                tenant_id=supp.tenant_id, supplier_id=supp.id
            ).scalar() or Decimal("0")
            
            # Total payments made to supplier
            payments_total = db.session.query(db.func.sum(Payment.amount)).filter_by(
                tenant_id=supp.tenant_id, supplier_id=supp.id
            ).scalar() or Decimal("0")
            
            # Use the correct supplier fields
            supp.total_purchases_aed = purchases_total
            supp.total_paid_aed = payments_total
        db.session.commit()
        print(f"Updated {len(suppliers)} supplier balances")
        
        print("✅ Balances updated successfully")


if __name__ == "__main__":
    seed()
