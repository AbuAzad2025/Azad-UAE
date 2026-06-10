import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from extensions import db
from app import create_app

app = create_app()

WIPE_ORDER = [
    'shop_saved_payment',
    'shop_abandoned_cart',
    'shop_wishlist',
    'shop_review',
    'shop_stock_alert',
    'shop_newsletter',
    'shop_loyalty_transactions',
    'shop_loyalties',
    'shop_customer_accounts',
    'shop_product_variants',
    'store_coupons',
    'store_payment_methods',
    'tenant_stores',
    'partner_commission_entries',
    'partner_profit_distributions',
    'partner_transactions',
    'product_cost_histories',
    'product_warehouse_costs',
    'product_serials',
    'product_partners',
    'products',
    'product_categories',
    'sale_lines',
    'sales',
    'purchase_lines',
    'purchases',
    'payment_transactions',
    'payment_logs',
    'payment_vaults',
    'payments',
    'receipts',
    'card_payments',
    'cheques',
    'expenses',
    'expense_categories',
    'product_return_lines',
    'product_returns',
    'donations',
    'budget_lines',
    'budgets',
    # GL tables protected — chart of accounts is system core
    # 'gl_journal_lines',
    # 'gl_journal_entries',
    # 'gl_account_mappings',
    # 'gl_periods',
    # 'gl_accounts',
    'bank_reconciliation_items',
    'bank_reconciliations',
    'cash_boxes',
    'fixed_assets',
    'depreciation_schedules',
    'customs_taxes',
    'advanced_expenses',
    'tax_calculation_rules',
    'cost_centers',
    'profit_centers',
    'payroll_transactions',
    'salary_advances',
    'employees',
    'package_purchases',
    'packages',
    'exchange_rate_records',
    'exchange_rates',
    'currencies',
    'invoice_settings',
    'audit_logs',
    'error_audit_logs',
    'archived_records',
    'login_histories',
    'security_alerts',
    'api_keys',
    'card_vaults',
    'azad_platform_fees',
    'journal_entry_audits',
    'branches',
    'customers',
    'suppliers',
    'users',
    'roles_permissions',
    'permissions',
    'roles',
    'tenants',
    'system_settings',
    'integration_settings',
]

RESET_TABLES = [
    'gl_concept_registry',
]


def wipe_all_data():
    with app.app_context():
        print("=" * 60)
        print("FULL SYSTEM WIPE — AZAD ERP")
        print("Deleting all tenant data, sales, purchases, everything.")
        print("=" * 60)
        for table_name in WIPE_ORDER:
            try:
                result = db.session.execute(db.text(f"DELETE FROM {table_name}"))
                db.session.commit()
                print(f"  [OK] {table_name:50s} — wiped")
            except Exception as e:
                db.session.rollback()
                print(f"  [SKIP] {table_name:50s} — {str(e)[:40]}")
        for table_name in RESET_TABLES:
            try:
                result = db.session.execute(db.text(f"DELETE FROM {table_name}"))
                db.session.commit()
                print(f"  [OK] {table_name:50s} — reset")
            except Exception as e:
                db.session.rollback()
                print(f"  [SKIP] {table_name:50s} — {str(e)[:40]}")
        print("=" * 60)
        print("WIPE COMPLETE")
        print("=" * 60)


if __name__ == '__main__':
    wipe_all_data()
