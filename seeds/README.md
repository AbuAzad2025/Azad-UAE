# Seeds Documentation

## Overview
This directory contains seed scripts for populating the database with test data for development and testing.

## Execution Order (IMPORTANT)
Run seeds in this order to avoid foreign key constraint violations:

### Phase 1: Core Data (Required First)
1. `seed_more_tenants.py` - Tenants, Branches, Warehouses, GL Accounts, GL Periods, Invoice Settings
2. `seed_additional_users.py` - Additional users for each tenant
3. `seed_cost_centers.py` - Cost centers (now tenant-specific)

### Phase 2: Master Data
4. `seed_employees.py` - Employees
5. `seed_suppliers.py` - Suppliers
6. `seed_customers.py` - Customers
7. `seed_merchants.py` - Merchants
8. `seed_products.py` - Products and Categories
9. `seed_packages.py` - Packages and Coupons

### Phase 3: Transactions
10. `seed_purchases.py` - Purchase Orders
11. `seed_sales.py` - Sales Orders
12. `seed_sales_returns.py` - Sales Returns
13. `seed_expenses.py` - Expenses
14. `seed_payments.py` - Payments
15. `seed_receipts.py` - Receipts
16. `seed_stock_movements.py` - Stock Movements

### Phase 4: Financial & Accounting
17. `seed_payroll.py` - Payroll Transactions
18. `seed_salary_advances.py` - Salary Advances
19. `seed_cheques.py` - Cheques (incoming/outgoing)
20. `seed_gl_entries.py` - GL Journal Entries
21. `seed_balances.py` - Update Customer/Supplier Balances

### Phase 5: Advanced Features
22. `seed_fixed_assets.py` - Fixed Assets
23. `seed_budgets.py` - Budgets and Budget Lines
24. `seed_product_serials.py` - Product Serial Numbers

## Quick Start

### Run All Seeds
```bash
python seeds/run_all_seeds.py
```

### Run Individual Seed
```bash
python seeds/seed_customers.py
```

## Notes

### Idempotency
All seed scripts are idempotent - they check for existing data before inserting to avoid duplicates.

### Tenant Scoping
- Most seeds create data for both `alhazem` and `nasrallah` tenants
- Tenant IDs are retrieved dynamically by slug
- Seeds use the tenant scoping system to ensure data isolation

### Dependencies
- `seed_balances.py` depends on sales, purchases, payments, and receipts
- `seed_gl_entries.py` depends on other transaction data
- `seed_product_serials.py` depends on products

## Manual Migrations

### Cost Centers Tenant Migration
File: `migrate_cost_centers.py`
- Added `tenant_id` column to `cost_centers` table
- Created unique constraint on `(tenant_id, code)`
- Run before `seed_cost_centers.py`

## Troubleshooting

### Foreign Key Errors
If you get foreign key constraint errors, ensure you're running seeds in the correct order.

### Duplicate Data
If you need to reset data, truncate tables in reverse dependency order before re-seeding.

### Tenant Not Found
Ensure tenants exist before running tenant-specific seeds. Run `seed_more_tenants.py` first.
