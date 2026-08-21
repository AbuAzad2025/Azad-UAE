"""Concurrent tenant-scoped GL posting integration test (M1)."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from time import sleep

from sqlalchemy.exc import IntegrityError, PendingRollbackError

from models import GLJournalEntry, GLJournalLine, Sale
from services.sale_service import SaleService
from services.stock_service import StockService
from utils.db_safety import atomic_transaction
from utils.gl_reference_types import GLRef


class TestGLPostingConcurrency:
    def test_concurrent_sales_produce_balanced_unique_gl_entries(
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
        """Two simultaneous sales against the same tenant produce balanced, unique GL."""
        StockService.add_stock(demo_product.id, 100, warehouse_id=demo_warehouse.id)
        db_session.commit()

        tenant_id = demo_tenant.id
        warehouse_id = demo_warehouse.id
        customer_id = demo_customer.id
        seller_id = demo_user.id
        product_id = demo_product.id

        def _create_sale(worker_id: int):
            with app.app_context():
                from extensions import db
                from models import Customer, Product, User

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
                        with atomic_transaction(f"concurrent_sale_worker_{worker_id}_{attempt}"):
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
                        return sale.id, sale.sale_number
                    except (IntegrityError, PendingRollbackError):
                        db.session.rollback()
                        sleep(0.1 * (attempt + 1))
                raise RuntimeError(f"Worker {worker_id} failed to create sale after retries")

        results = []
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(_create_sale, i) for i in range(2)]
            for future in futures:
                results.append(future.result())

        sale_ids = [sid for sid, _ in results]
        sale_numbers = [num for _, num in results]

        # Unique sale numbers within tenant
        assert len(set(sale_numbers)) == len(sale_numbers)

        # Refresh main session so it sees committed worker data
        db_session.expire_all()

        for sale_id in sale_ids:
            sale = Sale.query.filter_by(id=sale_id, tenant_id=tenant_id).first()
            assert sale is not None
            assert sale.tenant_id == tenant_id

            gl_entry = GLJournalEntry.query.filter_by(
                reference_type=GLRef.SALE,
                reference_id=sale_id,
                tenant_id=tenant_id,
            ).first()
            assert gl_entry is not None

            total_debit = sum(Decimal(str(line.debit or 0)) for line in gl_entry.lines)
            total_credit = sum(Decimal(str(line.credit or 0)) for line in gl_entry.lines)
            assert total_debit == total_credit

            for line in gl_entry.lines:
                assert line.tenant_id == tenant_id

        # Unique GL entry numbers within tenant
        entries = GLJournalEntry.query.filter(
            GLJournalEntry.tenant_id == tenant_id,
            GLJournalEntry.reference_type == GLRef.SALE,
            GLJournalEntry.reference_id.in_(sale_ids),
        ).all()
        entry_numbers = [e.entry_number for e in entries]
        assert len(set(entry_numbers)) == len(entry_numbers)

        # No cross-tenant leakage
        foreign = GLJournalEntry.query.filter(
            GLJournalEntry.reference_type == GLRef.SALE,
            GLJournalEntry.reference_id.in_(sale_ids),
            GLJournalEntry.tenant_id != tenant_id,
        ).first()
        assert foreign is None

        # Cleanup worker-committed rows so savepoint-based tests are not affected
        from models import SaleLine

        SaleLine.query.filter(SaleLine.sale_id.in_(sale_ids)).delete(synchronize_session=False)
        GLJournalLine.query.filter(GLJournalLine.entry_id.in_([e.id for e in entries])).delete(
            synchronize_session=False
        )
        GLJournalEntry.query.filter(
            GLJournalEntry.reference_type == GLRef.SALE,
            GLJournalEntry.reference_id.in_(sale_ids),
        ).delete(synchronize_session=False)
        Sale.query.filter(Sale.id.in_(sale_ids)).delete(synchronize_session=False)
        db_session.commit()
