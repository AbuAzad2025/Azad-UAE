"""Concurrent stock deduction guard across POS terminals (M4)."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier
from time import sleep

from sqlalchemy.exc import IntegrityError, PendingRollbackError

from models import ProductWarehouseStock, Sale
from services.sale_service import SaleService
from services.stock_service import StockService
from utils.db_safety import atomic_transaction


class TestStockConcurrencyGuard:
    def test_concurrent_pos_sales_for_single_item_block_negative_stock(
        self,
        app,
        db_session,
        demo_tenant,
        demo_branch,
        demo_warehouse,
        demo_user,
        demo_customer,
        demo_product,
        demo_gl_accounts,
    ):
        """When stock=1, exactly one of two concurrent POS sales succeeds."""
        StockService.add_stock(demo_product.id, 1, warehouse_id=demo_warehouse.id)
        db_session.commit()

        tenant_id = demo_tenant.id
        warehouse_id = demo_warehouse.id
        customer_id = demo_customer.id
        seller_id = demo_user.id
        product_id = demo_product.id
        barrier = Barrier(2)

        def _attempt_sale(worker_id: int):
            with app.app_context():
                from extensions import db
                from models import Customer, Product, User

                barrier.wait(timeout=5)
                for attempt in range(5):
                    local_customer = db.session.get(Customer, customer_id)
                    local_seller = db.session.get(User, seller_id)
                    local_product = db.session.get(Product, product_id)
                    lines = [
                        {
                            "product": local_product,
                            "quantity": 1,
                            "unit_price": 100,
                            "discount_percent": 0,
                        }
                    ]
                    try:
                        with atomic_transaction(f"concurrent_stock_sale_worker_{worker_id}_{attempt}"):
                            sale = SaleService.create_sale(
                                customer=local_customer,
                                seller=local_seller,
                                lines_data=lines,
                                warehouse_id=warehouse_id,
                                currency="AED",
                                tax_rate=0,
                                discount_amount=0,
                                shipping_cost=0,
                            )
                            db.session.flush()
                        return {"sale_id": sale.id, "error": None}
                    except (IntegrityError, PendingRollbackError):
                        db.session.rollback()
                        sleep(0.1 * (attempt + 1))
                    except Exception as exc:
                        db.session.rollback()
                        return {"sale_id": None, "error": str(exc)}
                return {"sale_id": None, "error": "exhausted retries on duplicate sale number"}

        results = []
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(_attempt_sale, i) for i in range(2)]
            for future in futures:
                results.append(future.result())

        successes = [r for r in results if r["sale_id"] is not None]
        failures = [r for r in results if r["sale_id"] is None]

        # Exactly one sale should succeed
        assert len(successes) == 1, f"Expected exactly one success, got {len(successes)}"
        assert len(failures) == 1

        # Stock must not be negative
        db_session.expire_all()
        pws = ProductWarehouseStock.query.filter_by(
            tenant_id=tenant_id,
            product_id=product_id,
            warehouse_id=warehouse_id,
        ).first()
        assert pws is not None
        assert pws.quantity >= 0

        # Successful sale must be the one that deducted the stock
        assert pws.quantity == Decimal("0")

        # Cleanup
        sale_ids = [r["sale_id"] for r in successes if r["sale_id"]]
        if sale_ids:
            from models.gl import GLJournalEntry, GLJournalLine
            from utils.gl_reference_types import GLRef

            entries = GLJournalEntry.query.filter(
                GLJournalEntry.reference_id.in_(sale_ids),
                GLJournalEntry.reference_type.in_([GLRef.SALE, GLRef.SALE_COGS]),
            ).all()
            from models import SaleLine

            SaleLine.query.filter(SaleLine.sale_id.in_(sale_ids)).delete(synchronize_session=False)
            GLJournalLine.query.filter(
                GLJournalLine.entry_id.in_([e.id for e in entries])
            ).delete(synchronize_session=False)
            GLJournalEntry.query.filter(GLJournalEntry.id.in_([e.id for e in entries])).delete(
                synchronize_session=False
            )
            Sale.query.filter(Sale.id.in_(sale_ids)).delete(synchronize_session=False)
            db_session.commit()
