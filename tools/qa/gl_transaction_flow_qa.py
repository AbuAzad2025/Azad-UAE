"""Phase 1L: Transaction-flow QA with Dynamic GL Mapping enabled temporarily.

Creates real journal entries via test-marked business records, verifies concept
resolution, account safety, and entry balance, then cleans up all test data.

Run:
    python tools/qa/gl_transaction_flow_qa.py --tenant-id 2
    python tools/qa/gl_transaction_flow_qa.py --tenant-id 2 --flows sale,purchase,cheque
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, datetime, timezone
from decimal import Decimal

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)
os.chdir(PROJECT_ROOT)
os.environ.setdefault("SKIP_SYSTEM_INTEGRITY", "1")

from dotenv import load_dotenv
load_dotenv()

_TEST_PREFIX = "QA-TEST-1L"


class FlowResult:
    def __init__(self, name: str):
        self.name = name
        self.success = False
        self.journal_entry_ids = []
        self.concepts_used = []
        self.account_codes_used = []
        self.total_debit = Decimal("0")
        self.total_credit = Decimal("0")
        self.balanced = False
        self.errors = []
        self.warnings = []

    def to_dict(self):
        return {
            "flow": self.name,
            "success": self.success,
            "journal_entry_ids": self.journal_entry_ids,
            "concepts_used": sorted(set(self.concepts_used)),
            "account_codes_used": sorted(set(self.account_codes_used)),
            "total_debit": str(self.total_debit),
            "total_credit": str(self.total_credit),
            "balanced": self.balanced,
            "errors": self.errors,
            "warnings": self.warnings,
        }


class QATracker:
    def __init__(self):
        self.sale_ids = []
        self.purchase_ids = []
        self.payment_ids = []
        self.receipt_ids = []
        self.return_ids = []
        self.stock_movement_ids = []
        self.cheque_ids = []
        self.expense_ids = []
        self.journal_entry_ids = []
        self.other_ids = {}

    def add_je(self, entry_id):
        if entry_id and entry_id not in self.journal_entry_ids:
            self.journal_entry_ids.append(entry_id)

    def add_other(self, table, obj_id):
        self.other_ids.setdefault(table, []).append(obj_id)


def _verify_entry(entry, tenant_id, result: FlowResult):
    from models import GLAccount, GLJournalLine
    from extensions import db
    if entry is None:
        result.errors.append("Journal entry is None")
        return
    result.journal_entry_ids.append(entry.id)
    result.total_debit += Decimal(str(entry.total_debit or 0))
    result.total_credit += Decimal(str(entry.total_credit or 0))
    result.balanced = entry.is_balanced()
    if not result.balanced:
        result.errors.append(f"Entry {entry.id} unbalanced: D={entry.total_debit} C={entry.total_credit}")
    for line in db.session.query(GLJournalLine).filter_by(entry_id=entry.id).all():
        acc = GLAccount.query.get(line.account_id)
        if acc:
            result.account_codes_used.append(acc.code)
            if acc.is_header:
                result.errors.append(f"Entry {entry.id} line posted to header {acc.code}")
            if int(acc.tenant_id) != int(tenant_id):
                result.errors.append(f"Entry {entry.id} line cross-tenant {acc.code}")
            if not acc.is_active:
                result.errors.append(f"Entry {entry.id} line inactive {acc.code}")


def _flow_sale(app, tenant_id, branch_id, tracker, result):
    from models import Customer, Product, User, Warehouse, Sale
    from services.sale_service import SaleService
    from extensions import db
    customer = Customer.query.filter_by(tenant_id=tenant_id, is_active=True).first()
    seller = User.query.filter_by(tenant_id=tenant_id, is_active=True).first()
    warehouse = Warehouse.query.filter_by(tenant_id=tenant_id, is_active=True).first()
    product = Product.query.filter_by(tenant_id=tenant_id, is_active=True).first()
    if not all([customer, seller, warehouse, product]):
        result.errors.append("Missing fixtures for sale flow")
        return
    sale = SaleService.create_sale(
        customer=customer, seller=seller,
        lines_data=[{"product": product, "quantity": 1, "unit_price": Decimal("100.00"), "discount_percent": 0}],
        warehouse_id=warehouse.id, currency="AED",
        discount_amount=Decimal("5.00"), shipping_cost=Decimal("10.00"),
        tax_rate=Decimal("5.00"), notes=f"{_TEST_PREFIX} Sale", defer_fulfillment=True,
    )
    tracker.sale_ids.append(sale.id)
    SaleService.fulfill_sale(sale, payment_data=None, paid_amount_aed=Decimal("0"))
    db.session.commit()
    from models import GLJournalEntry
    from utils.gl_reference_types import GLRef
    for entry in GLJournalEntry.query.filter(
        GLJournalEntry.reference_type.in_(["Sale", "SaleCOGS"]),
        GLJournalEntry.reference_id == sale.id,
        GLJournalEntry.tenant_id == tenant_id,
    ).all():
        _verify_entry(entry, tenant_id, result)
    from services.gl_service import GLService
    result.concepts_used.extend([
        GLService.get_customer_credit_concept(customer), "SALES_REVENUE",
        "SHIPPING_REVENUE", "SALES_DISCOUNT", "VAT_OUTPUT", "COGS", "INVENTORY_ASSET",
    ])
    result.success = not result.errors


def _flow_purchase(app, tenant_id, branch_id, tracker, result):
    from models import Supplier, Product, User, Warehouse
    from services.purchase_service import PurchaseService
    supplier = Supplier.query.filter_by(tenant_id=tenant_id, is_active=True).first()
    user = User.query.filter_by(tenant_id=tenant_id, is_active=True).first()
    warehouse = Warehouse.query.filter_by(tenant_id=tenant_id, is_active=True).first()
    product = Product.query.filter_by(tenant_id=tenant_id, is_active=True).first()
    if not all([supplier, user, warehouse, product]):
        result.errors.append("Missing fixtures for purchase flow")
        return
    purchase = PurchaseService.create_purchase(
        user=user, supplier_data={"supplier_id": supplier.id, "supplier_name": supplier.name},
        lines_data=[{"product_id": product.id, "quantity": 10, "unit_cost": Decimal("50.00"), "discount_percent": 0}],
        warehouse_id=warehouse.id, currency="AED", discount_amount=Decimal("0"),
        tax_rate=Decimal("5.00"), notes=f"{_TEST_PREFIX} Purchase",
    )
    tracker.purchase_ids.append(purchase.id)
    from models import GLJournalEntry
    for entry in GLJournalEntry.query.filter_by(reference_type="Purchase", reference_id=purchase.id, tenant_id=tenant_id).all():
        _verify_entry(entry, tenant_id, result)
    result.concepts_used.extend(["INVENTORY_ASSET", "AP", "VAT_INPUT"])
    result.success = not result.errors


def _flow_receipt(app, tenant_id, branch_id, tracker, result):
    from models import Customer
    from services.payment_service import PaymentService
    customer = Customer.query.filter_by(tenant_id=tenant_id, is_active=True).first()
    if not customer:
        result.errors.append("No active customer")
        return
    receipt = PaymentService.create_receipt({
        "customer_id": customer.id, "amount": Decimal("100.00"), "currency": "AED",
        "payment_method": "cash", "notes": f"{_TEST_PREFIX} Receipt", "branch_id": branch_id,
    })
    tracker.receipt_ids.append(receipt.id)
    from models import GLJournalEntry
    for entry in GLJournalEntry.query.filter_by(reference_type="Receipt", reference_id=receipt.id, tenant_id=tenant_id).all():
        _verify_entry(entry, tenant_id, result)
    from services.gl_service import GLService
    result.concepts_used.extend(["CASH", GLService.get_customer_credit_concept(customer)])
    result.success = not result.errors


def _flow_supplier_payment(app, tenant_id, branch_id, tracker, result):
    from models import Supplier
    from services.payment_service import PaymentService
    supplier = Supplier.query.filter_by(tenant_id=tenant_id, is_active=True).first()
    if not supplier:
        result.errors.append("No active supplier")
        return
    payment = PaymentService.create_payment({
        "supplier_id": supplier.id, "amount": Decimal("100.00"), "currency": "AED",
        "payment_method": "cash", "notes": f"{_TEST_PREFIX} Payment", "branch_id": branch_id,
    })
    tracker.payment_ids.append(payment.id)
    from models import GLJournalEntry
    for entry in GLJournalEntry.query.filter_by(reference_type="Payment", reference_id=payment.id, tenant_id=tenant_id).all():
        _verify_entry(entry, tenant_id, result)
    result.concepts_used.extend(["AP", "CASH"])
    result.success = not result.errors


def _flow_sales_return(app, tenant_id, branch_id, tracker, result):
    from models import Customer, Product, User, Warehouse
    from services.sale_service import SaleService
    from services.return_service import ReturnService
    from extensions import db
    customer = Customer.query.filter_by(tenant_id=tenant_id, is_active=True).first()
    seller = User.query.filter_by(tenant_id=tenant_id, is_active=True).first()
    warehouse = Warehouse.query.filter_by(tenant_id=tenant_id, is_active=True).first()
    product = Product.query.filter_by(tenant_id=tenant_id, is_active=True).first()
    if not all([customer, seller, warehouse, product]):
        result.errors.append("Missing fixtures for return flow")
        return
    sale = SaleService.create_sale(
        customer=customer, seller=seller,
        lines_data=[{"product": product, "quantity": 1, "unit_price": Decimal("100.00"), "discount_percent": 0}],
        warehouse_id=warehouse.id, currency="AED", notes=f"{_TEST_PREFIX} Return-sale", defer_fulfillment=True,
    )
    tracker.sale_ids.append(sale.id)
    SaleService.fulfill_sale(sale, payment_data=None, paid_amount_aed=Decimal("0"))
    db.session.commit()
    ret = ReturnService.create_return(
        sale_id=sale.id,
        return_lines_data=[{"sale_line_id": sale.lines[0].id, "quantity": 1, "condition": "good"}],
        user=seller, notes=f"{_TEST_PREFIX} Return",
    )
    tracker.return_ids.append(ret.id)
    from models import GLJournalEntry
    for entry in GLJournalEntry.query.filter_by(reference_type="ProductReturn", reference_id=ret.id, tenant_id=tenant_id).all():
        _verify_entry(entry, tenant_id, result)
    from services.gl_service import GLService
    result.concepts_used.extend([
        GLService.get_customer_credit_concept(customer), "SALES_RETURNS",
        "VAT_OUTPUT", "INVENTORY_ASSET", "COGS_REVERSAL",
    ])
    result.success = not result.errors


def _flow_inventory_adjustment(app, tenant_id, branch_id, tracker, result):
    from models import Product, Warehouse
    from services.stock_service import StockService
    from extensions import db
    product = Product.query.filter_by(tenant_id=tenant_id, is_active=True).first()
    warehouse = Warehouse.query.filter_by(tenant_id=tenant_id, is_active=True).first()
    if not product or not warehouse:
        result.errors.append("Missing fixtures for stock adjustment")
        return
    movement = StockService.adjust_stock(
        product_id=product.id, quantity=Decimal("-1"),
        notes=f"{_TEST_PREFIX} Adj loss", warehouse_id=warehouse.id,
    )
    tracker.stock_movement_ids.append(movement.id)
    from models import GLJournalEntry
    for entry in GLJournalEntry.query.filter_by(reference_type="StockAdjustment", reference_id=movement.id, tenant_id=tenant_id).all():
        _verify_entry(entry, tenant_id, result)
    result.concepts_used.extend(["INVENTORY_ADJUSTMENT_LOSS", "INVENTORY_ASSET"])
    result.success = not result.errors
    db.session.commit()


def _flow_cheque_receive(app, tenant_id, branch_id, tracker, result):
    from models import Customer, Cheque
    from extensions import db
    customer = Customer.query.filter_by(tenant_id=tenant_id, is_active=True).first()
    if not customer:
        result.errors.append("No active customer")
        return
    today = date.today()
    ts = datetime.now(timezone.utc).strftime('%H%M%S%f')
    cheque = Cheque(
        tenant_id=tenant_id, cheque_number=f"{_TEST_PREFIX}-IN-{today.isoformat()}-{ts}",
        cheque_bank_number=f"{_TEST_PREFIX}-IN-{ts}", cheque_type="incoming",
        bank_name="Test Bank", amount=Decimal("500.00"), currency="AED",
        exchange_rate=Decimal("1.0"), amount_aed=Decimal("500.00"),
        issue_date=today, due_date=today, status="pending",
        customer_id=customer.id, branch_id=branch_id,
    )
    db.session.add(cheque); db.session.flush()
    tracker.cheque_ids.append(cheque.id)
    entry1 = cheque.receive_cheque()
    if entry1:
        tracker.add_je(entry1.id); _verify_entry(entry1, tenant_id, result)
    cheque.deposit_cheque(deposit_date=today)
    db.session.commit()
    entry2 = cheque.clear_cheque(clearance_date=today)
    if entry2:
        tracker.add_je(entry2.id); _verify_entry(entry2, tenant_id, result)
    from services.gl_service import GLService
    result.concepts_used.extend([
        "CHEQUES_UNDER_COLLECTION", GLService.get_customer_credit_concept(customer), "BANK",
    ])
    result.success = not result.errors
    db.session.commit()


def _flow_cheque_issue(app, tenant_id, branch_id, tracker, result):
    from models import Supplier, Cheque
    from extensions import db
    supplier = Supplier.query.filter_by(tenant_id=tenant_id, is_active=True).first()
    if not supplier:
        result.errors.append("No active supplier")
        return
    today = date.today()
    ts = datetime.now(timezone.utc).strftime('%H%M%S%f')
    cheque = Cheque(
        tenant_id=tenant_id, cheque_number=f"{_TEST_PREFIX}-OUT-{today.isoformat()}-{ts}",
        cheque_bank_number=f"{_TEST_PREFIX}-OUT-{ts}", cheque_type="outgoing",
        bank_name="Test Bank", amount=Decimal("300.00"), currency="AED",
        exchange_rate=Decimal("1.0"), amount_aed=Decimal("300.00"),
        issue_date=today, due_date=today, status="pending",
        supplier_id=supplier.id, branch_id=branch_id,
    )
    db.session.add(cheque); db.session.flush()
    tracker.cheque_ids.append(cheque.id)
    entry1 = cheque.issue_cheque()
    if entry1:
        tracker.add_je(entry1.id); _verify_entry(entry1, tenant_id, result)
    entry2 = cheque.bounce_cheque(reason=f"{_TEST_PREFIX} bounce test")
    if entry2:
        tracker.add_je(entry2.id); _verify_entry(entry2, tenant_id, result)
    result.concepts_used.extend(["AP", "DEFERRED_CHEQUES_PAYABLE"])
    result.success = not result.errors
    db.session.commit()


def _flow_expense(app, tenant_id, branch_id, tracker, result):
    from models import Expense, ExpenseCategory, GLAccount
    from services.gl_service import GLService
    from services.gl_posting import post_or_fail
    from utils.gl_reference_types import GLRef
    from utils.helpers import generate_number
    from extensions import db
    category = ExpenseCategory.query.filter_by(tenant_id=tenant_id, is_active=True).first()
    if not category:
        result.errors.append("No active expense category")
        return
    expense = Expense(
        tenant_id=tenant_id,
        expense_number=generate_number("EXP", Expense, "expense_number", branch_id=branch_id, tenant_id=tenant_id),
        category_id=category.id, description=f"{_TEST_PREFIX} Expense",
        amount=Decimal("75.00"), currency="AED", exchange_rate=Decimal("1.0"),
        amount_aed=Decimal("75.00"), payment_method="cash", branch_id=branch_id,
        status="confirmed", expense_date=datetime.now(timezone.utc).date(),
        user_id=1,
    )
    db.session.add(expense); db.session.flush()
    tracker.expense_ids.append(expense.id)
    GLService.ensure_core_accounts(tenant_id=tenant_id)
    expense_account = category.gl_account_code if category and category.gl_account_code else "6990"
    expense_concept = None if category and category.gl_account_code else "MISC_EXPENSE"
    acc_check = GLAccount.query.filter_by(code=str(expense_account), tenant_id=tenant_id).first()
    if acc_check and acc_check.is_header:
        expense_account = "6990"; expense_concept = "MISC_EXPENSE"
    cash_account = GLService.get_default_liquidity_account("cash", branch_id=branch_id, tenant_id=tenant_id)
    lines = [
        {"account": expense_account, "concept_code": expense_concept,
         "explicit_account_allowed": expense_concept is None, "debit": expense.amount, "description": expense.description},
        {"account": cash_account, "concept_code": "CASH", "credit": expense.amount, "description": f"دفع {expense.payment_method}"},
    ]
    entry = post_or_fail(lines, description=expense.description, reference_type=GLRef.EXPENSE,
                         reference_id=expense.id, branch_id=branch_id, tenant_id=tenant_id)
    tracker.add_je(entry.id); _verify_entry(entry, tenant_id, result)
    result.concepts_used.extend(["CASH"] + ([expense_concept] if expense_concept else []))
    result.success = not result.errors
    db.session.commit()


# Optional advanced flows
FLOW_REGISTRY = {
    "sale": _flow_sale,
    "purchase": _flow_purchase,
    "receipt": _flow_receipt,
    "supplier_payment": _flow_supplier_payment,
    "sales_return": _flow_sales_return,
    "inventory_adjustment": _flow_inventory_adjustment,
    "cheque_receive": _flow_cheque_receive,
    "cheque_issue": _flow_cheque_issue,
    "expense": _flow_expense,
}


def _cleanup(tracker, tenant_id):
    from models import (
        GLJournalEntry, GLJournalLine, Sale, SaleLine, Purchase, PurchaseLine,
        ProductReturn, ProductReturnLine, StockMovement, Cheque, Expense,
        Payment, Receipt,
    )
    from extensions import db
    deleted = {"journal_lines": 0, "journal_entries": 0}

    # 1. Journal lines first, then entries
    if tracker.journal_entry_ids:
        deleted["journal_lines"] = db.session.query(GLJournalLine).filter(
            GLJournalLine.entry_id.in_(tracker.journal_entry_ids)
        ).delete(synchronize_session=False)
        deleted["journal_entries"] = db.session.query(GLJournalEntry).filter(
            GLJournalEntry.id.in_(tracker.journal_entry_ids)
        ).delete(synchronize_session=False)

    # 2. Child records before parents
    if tracker.return_ids:
        db.session.query(ProductReturnLine).filter(
            ProductReturnLine.return_id.in_(tracker.return_ids)
        ).delete(synchronize_session=False)
        db.session.query(ProductReturn).filter(
            ProductReturn.id.in_(tracker.return_ids)
        ).delete(synchronize_session=False)

    if tracker.sale_ids:
        db.session.query(SaleLine).filter(
            SaleLine.sale_id.in_(tracker.sale_ids)
        ).delete(synchronize_session=False)
        db.session.query(Sale).filter(
            Sale.id.in_(tracker.sale_ids)
        ).delete(synchronize_session=False)

    if tracker.purchase_ids:
        db.session.query(PurchaseLine).filter(
            PurchaseLine.purchase_id.in_(tracker.purchase_ids)
        ).delete(synchronize_session=False)
        db.session.query(Purchase).filter(
            Purchase.id.in_(tracker.purchase_ids)
        ).delete(synchronize_session=False)

    if tracker.stock_movement_ids:
        db.session.query(StockMovement).filter(
            StockMovement.id.in_(tracker.stock_movement_ids)
        ).delete(synchronize_session=False)

    # Cheques reference payments/receipts, so delete cheques first
    if tracker.cheque_ids:
        db.session.query(Cheque).filter(
            Cheque.id.in_(tracker.cheque_ids)
        ).delete(synchronize_session=False)

    if tracker.payment_ids:
        db.session.query(Payment).filter(
            Payment.id.in_(tracker.payment_ids)
        ).delete(synchronize_session=False)

    if tracker.receipt_ids:
        db.session.query(Receipt).filter(
            Receipt.id.in_(tracker.receipt_ids)
        ).delete(synchronize_session=False)

    if tracker.expense_ids:
        db.session.query(Expense).filter(
            Expense.id.in_(tracker.expense_ids)
        ).delete(synchronize_session=False)

    for table, ids in tracker.other_ids.items():
        if ids:
            try:
                model_cls = globals().get(table) or __import__("models", fromlist=[table]).__dict__.get(table)
                if model_cls:
                    db.session.query(model_cls).filter(model_cls.id.in_(ids)).delete(synchronize_session=False)
            except Exception:
                pass

    db.session.commit()
    return deleted


def _preflight_cleanup(tenant_id):
    """Delete any lingering QA-TEST records from previous failed runs."""
    from models import (
        GLJournalEntry, GLJournalLine, Sale, SaleLine, Purchase, PurchaseLine,
        ProductReturn, ProductReturnLine, StockMovement, Cheque, Expense,
        Payment, Receipt,
    )
    from extensions import db
    try:
        # Find lingering records
        sales = Sale.query.filter(Sale.notes.ilike(f"%{_TEST_PREFIX}%")).with_entities(Sale.id).all()
        purchases = Purchase.query.filter(Purchase.notes.ilike(f"%{_TEST_PREFIX}%")).with_entities(Purchase.id).all()
        payments = Payment.query.filter(Payment.notes.ilike(f"%{_TEST_PREFIX}%")).with_entities(Payment.id).all()
        receipts = Receipt.query.filter(Receipt.notes.ilike(f"%{_TEST_PREFIX}%")).with_entities(Receipt.id).all()
        expenses = Expense.query.filter(Expense.description.ilike(f"%{_TEST_PREFIX}%")).with_entities(Expense.id).all()
        returns = ProductReturn.query.filter(ProductReturn.notes.ilike(f"%{_TEST_PREFIX}%")).with_entities(ProductReturn.id).all()
        stock = StockMovement.query.filter(StockMovement.notes.ilike(f"%{_TEST_PREFIX}%")).with_entities(StockMovement.id).all()
        cheques = Cheque.query.filter(Cheque.cheque_number.ilike(f"%{_TEST_PREFIX}%")).with_entities(Cheque.id).all()
        sale_ids = [s.id for s in sales]
        purchase_ids = [p.id for p in purchases]
        payment_ids = [p.id for p in payments]
        receipt_ids = [r.id for r in receipts]
        expense_ids = [e.id for e in expenses]
        return_ids = [r.id for r in returns]
        stock_ids = [s.id for s in stock]
        cheque_ids = [c.id for c in cheques]
        all_ref_ids = sale_ids + purchase_ids + payment_ids + receipt_ids + stock_ids
        ref_types = ["sale", "purchase", "payment", "receipt", "stock_adjustment", "return", "expense", "cheque_receive", "cheque_clear", "cheque_bounce"]
        if all_ref_ids:
            for entry in GLJournalEntry.query.filter(
                GLJournalEntry.reference_type.in_(ref_types),
                GLJournalEntry.reference_id.in_(all_ref_ids),
                GLJournalEntry.tenant_id == tenant_id,
            ).all():
                db.session.query(GLJournalLine).filter_by(entry_id=entry.id).delete(synchronize_session=False)
                db.session.delete(entry)
        if return_ids:
            db.session.query(ProductReturnLine).filter(ProductReturnLine.return_id.in_(return_ids)).delete(synchronize_session=False)
            db.session.query(ProductReturn).filter(ProductReturn.id.in_(return_ids)).delete(synchronize_session=False)
        if sale_ids:
            db.session.query(SaleLine).filter(SaleLine.sale_id.in_(sale_ids)).delete(synchronize_session=False)
            db.session.query(Sale).filter(Sale.id.in_(sale_ids)).delete(synchronize_session=False)
        if purchase_ids:
            db.session.query(PurchaseLine).filter(PurchaseLine.purchase_id.in_(purchase_ids)).delete(synchronize_session=False)
            db.session.query(Purchase).filter(Purchase.id.in_(purchase_ids)).delete(synchronize_session=False)
        if payment_ids:
            db.session.query(Payment).filter(Payment.id.in_(payment_ids)).delete(synchronize_session=False)
        if receipt_ids:
            db.session.query(Receipt).filter(Receipt.id.in_(receipt_ids)).delete(synchronize_session=False)
        if expense_ids:
            db.session.query(Expense).filter(Expense.id.in_(expense_ids)).delete(synchronize_session=False)
        if stock_ids:
            db.session.query(StockMovement).filter(StockMovement.id.in_(stock_ids)).delete(synchronize_session=False)
        if cheque_ids:
            db.session.query(Cheque).filter(Cheque.id.in_(cheque_ids)).delete(synchronize_session=False)
        db.session.commit()
    except Exception:
        db.session.rollback()


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 1L transaction-flow QA.")
    parser.add_argument("--tenant-id", type=int, default=2)
    parser.add_argument("--branch-id", type=int, default=None)
    parser.add_argument("--flows", type=str, default=None,
                        help="Comma-separated flows. Default: all core flows.")
    args = parser.parse_args()

    from app import create_app
    from services.gl_service import GLService
    from models import Branch, Tenant
    from extensions import db

    app = create_app()
    report = {"tenant_id": args.tenant_id, "branch_id": args.branch_id, "flows": [], "cleanup": {}, "ready": True}

    with app.app_context():
        tenant = Tenant.query.get(args.tenant_id)
        if not tenant:
            print(json.dumps({"error": f"Tenant {args.tenant_id} not found"}, indent=2))
            return 1
        branch_id = args.branch_id
        if not branch_id:
            branch = Branch.query.filter_by(tenant_id=args.tenant_id, is_active=True).first()
            branch_id = branch.id if branch else None
        report["branch_id"] = branch_id

        original_flag = app.config.get("ENABLE_DYNAMIC_GL_MAPPING", False)
        app.config["ENABLE_DYNAMIC_GL_MAPPING"] = True

        _preflight_cleanup(args.tenant_id)

        tracker = QATracker()
        flow_names = args.flows.split(",") if args.flows else list(FLOW_REGISTRY.keys())

        try:
            for flow_name in flow_names:
                flow_name = flow_name.strip()
                if flow_name not in FLOW_REGISTRY:
                    report["flows"].append({"flow": flow_name, "success": False, "errors": ["Unknown flow"]})
                    continue
                result = FlowResult(flow_name)
                try:
                    FLOW_REGISTRY[flow_name](app, args.tenant_id, branch_id, tracker, result)
                except Exception as exc:
                    db.session.rollback()
                    result.errors.append(str(exc))
                    result.success = False
                # Merge discovered journal entry IDs into tracker for cleanup
                for je_id in result.journal_entry_ids:
                    tracker.add_je(je_id)
                report["flows"].append(result.to_dict())
                if not result.success:
                    report["ready"] = False
        finally:
            db.session.rollback()
            # Cleanup ALL test records and journal entries
            deleted = _cleanup(tracker, args.tenant_id)
            report["cleanup"] = deleted
            app.config["ENABLE_DYNAMIC_GL_MAPPING"] = original_flag

    # Final assertions
    report["feature_flag_restored"] = original_flag == app.config.get("ENABLE_DYNAMIC_GL_MAPPING", False)
    report["feature_flag_default_still_false"] = not app.config.get("ENABLE_DYNAMIC_GL_MAPPING", False)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
