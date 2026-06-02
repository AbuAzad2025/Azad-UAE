"""Master seed runner - executes all seed scripts in the correct order."""
import os, sys, subprocess
from pathlib import Path

# Get the seeds directory
seeds_dir = Path(__file__).parent

# Seeds in execution order
SEEDS_ORDER = [
    # Phase 1: Core Data (Required First)
    "seed_more_tenants.py",
    "seed_additional_users.py",
    "seed_cost_centers.py",
    
    # Phase 2: Master Data
    "seed_employees.py",
    "seed_suppliers.py",
    "seed_customers.py",
    "seed_merchants.py",
    "seed_products.py",
    "seed_packages.py",
    
    # Phase 3: Transactions
    "seed_purchases.py",
    "seed_sales.py",
    "seed_sales_returns.py",
    "seed_expenses.py",
    "seed_payments.py",
    "seed_receipts.py",
    "seed_stock_movements.py",
    
    # Phase 4: Financial & Accounting
    "seed_payroll.py",
    "seed_salary_advances.py",
    "seed_cheques.py",
    "seed_gl_entries.py",
    "seed_balances.py",
    
    # Phase 5: Advanced Features
    "seed_fixed_assets.py",
    "seed_budgets.py",
    "seed_product_serials.py",
]


def run_seed(seed_file):
    """Run a single seed script."""
    seed_path = seeds_dir / seed_file
    if not seed_path.exists():
        print(f"⚠️  Skipping {seed_file} - file not found")
        return False
    
    print(f"\n{'='*60}")
    print(f"Running: {seed_file}")
    print(f"{'='*60}")
    
    try:
        result = subprocess.run(
            [sys.executable, str(seed_path)],
            cwd=seeds_dir.parent,
            capture_output=False,
            text=True
        )
        if result.returncode == 0:
            print(f"✅ {seed_file} completed successfully")
            return True
        else:
            print(f"❌ {seed_file} failed with exit code {result.returncode}")
            return False
    except Exception as e:
        print(f"❌ {seed_file} failed with error: {e}")
        return False


def main():
    """Run all seeds in order."""
    print("="*60)
    print("MASTER SEED RUNNER")
    print("="*60)
    print(f"Seeds directory: {seeds_dir}")
    print(f"Total seeds to run: {len(SEEDS_ORDER)}")
    
    results = []
    for seed_file in SEEDS_ORDER:
        success = run_seed(seed_file)
        results.append((seed_file, success))
    
    # Summary
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    successful = sum(1 for _, success in results if success)
    failed = len(results) - successful
    
    print(f"Total: {len(results)}")
    print(f"✅ Successful: {successful}")
    print(f"❌ Failed: {failed}")
    
    if failed > 0:
        print("\nFailed seeds:")
        for seed_file, success in results:
            if not success:
                print(f"  - {seed_file}")
        sys.exit(1)
    else:
        print("\n🎉 All seeds completed successfully!")
        sys.exit(0)


if __name__ == "__main__":
    main()
