"""
Clean up [TEST-STORE] and [UAT-TEST] customer leftovers safely.
Run this when PostgreSQL is available.
"""
import os
import sys

# Set DATABASE_URL with password (PostgreSQL is on port 5432)
os.environ["DATABASE_URL"] = "postgresql+psycopg2://postgres:123@localhost:5432/azad_uae"
os.environ["SQLALCHEMY_DATABASE_URI"] = "postgresql+psycopg2://postgres:123@localhost:5432/azad_uae"

from app import create_app
from extensions import db
from models import Customer, Sale, Payment, ProductPartner, PartnerCommissionEntry

app = create_app()

with app.app_context():
    print("=== Checking for [TEST-STORE] and [UAT-TEST] customers ===")
    
    test_customers = Customer.query.filter(
        Customer.name.ilike('%[TEST-STORE]%') | 
        Customer.name.ilike('%TEST-STORE%') |
        Customer.name.ilike('%[UAT-TEST]%') |
        Customer.name.ilike('%UAT-TEST%') |
        Customer.name.ilike('%UAT-2-TMP%')
    ).all()
    
    print(f"Found {len(test_customers)} test customers:")
    
    for customer in test_customers:
        print(f"\n--- Customer {customer.id} ---")
        print(f"Name: {customer.name}")
        print(f"Tenant ID: {customer.tenant_id}")
        print(f"Phone: {customer.phone}")
        print(f"Email: {customer.email}")
        print(f"Created At: {customer.created_at}")
        
        # Check relationships
        sales = Sale.query.filter_by(customer_id=customer.id).all()
        print(f"Sales: {len(sales)}")
        if sales:
            for sale in sales:
                print(f"  - {sale.sale_number} ({sale.created_at})")
        
        payments = Payment.query.filter_by(customer_id=customer.id).all()
        print(f"Payments: {len(payments)}")
        if payments:
            for payment in payments:
                print(f"  - {payment.payment_number} ({payment.created_at})")
        
        product_partners = ProductPartner.query.filter_by(customer_id=customer.id).all()
        print(f"Product Partners: {len(product_partners)}")
        
        partner_commissions = PartnerCommissionEntry.query.filter_by(customer_id=customer.id).all()
        print(f"Partner Commissions: {len(partner_commissions)}")
    
    # Delete automatically
    if test_customers:
        print(f"\n🗑️  Deleting {len(test_customers)} test customers...")
        for customer in test_customers:
            # Delete in reverse order of dependencies
            PartnerCommissionEntry.query.filter_by(customer_id=customer.id).delete()
            ProductPartner.query.filter_by(customer_id=customer.id).delete()
            # Sales and payments should cascade if FKs are set up correctly
            # If not, we need to delete them manually
            for sale in Sale.query.filter_by(customer_id=customer.id).all():
                db.session.delete(sale)
            for payment in Payment.query.filter_by(customer_id=customer.id).all():
                db.session.delete(payment)
            db.session.delete(customer)
        
        db.session.commit()
        print(f"\n✅ Deleted {len(test_customers)} test customers")
    else:
        print("\n✅ No test customers found")
