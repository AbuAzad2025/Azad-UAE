"""Performance baseline harness — measures query count + latency on hot endpoints.

NOT part of CI (CI matrix groups run tests/unit, tests/e2e, tests/integration
only). Run manually:

    .venv/Scripts/python.exe -m pytest tests/perf/test_baseline.py -q -p no:cacheprovider -s

Seeds a realistic dataset (40 customers, 100 products, 60 sales) into the
ephemeral test DB, then times each endpoint and counts SQL statements via
SQLAlchemy engine events. Use it before/after query optimizations to prove
improvement with numbers instead of guessing.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import event

ENDPOINTS = [
    "/",
    "/sales/",
    "/customers/",
    "/purchases/",
    "/expenses/",
    "/payments/",
    "/pos/",
    "/pos/grid",
    "/pos/api/products",
    "/reports/",
]


def _seed_bulk(db_session, tenant, user):
    from models import Customer, Product, Sale

    customers = [
        Customer(
            tenant_id=tenant.id,
            name=f"Perf Customer {i}",
            phone=f"0500000{i:03d}",
            is_active=True,
        )
        for i in range(40)
    ]
    db_session.add_all(customers)

    products = [
        Product(
            tenant_id=tenant.id,
            name=f"Perf Product {i}",
            sku=f"SKU-PERF-{i:04d}",
            cost_price=Decimal("10.000"),
            regular_price=Decimal("25.000"),
            current_stock=Decimal("50.000"),
        )
        for i in range(100)
    ]
    db_session.add_all(products)
    db_session.flush()

    now = datetime.now(timezone.utc)
    sales = [
        Sale(
            tenant_id=tenant.id,
            sale_number=f"SAL-PERF-{i:05d}",
            customer_id=customers[i % 40].id,
            seller_id=user.id,
            sale_date=now,
            subtotal=Decimal("100.000"),
            total_amount=Decimal("105.000"),
            amount=Decimal("105.000"),
            amount_aed=Decimal("105.000"),
            balance_due=Decimal("0"),
            currency="AED",
        )
        for i in range(60)
    ]
    db_session.add_all(sales)
    db_session.commit()


class QueryCounter:
    def __init__(self, engine):
        self.engine = engine
        self.count = 0

    def __enter__(self):
        self.count = 0
        event.listen(self.engine, "before_cursor_execute", self._on_execute)
        return self

    def __exit__(self, *_):
        event.remove(self.engine, "before_cursor_execute", self._on_execute)

    def _on_execute(self, conn, cursor, statement, parameters, context, executemany):
        self.count += 1


def test_baseline(auth_client, db_session, sample_tenant, sample_user, capsys):
    from extensions import db

    _seed_bulk(db_session, sample_tenant, sample_user)

    results = []
    for path in ENDPOINTS:
        auth_client.get(path)  # warm-up (imports, template compile, caches)
        with QueryCounter(db.engine) as qc:
            start = time.perf_counter()
            resp = auth_client.get(path)
            elapsed_ms = (time.perf_counter() - start) * 1000
        results.append((path, resp.status_code, elapsed_ms, qc.count))

    with capsys.disabled():
        print("\n\n=== PERFORMANCE BASELINE ===")
        print(f"{'endpoint':<24} {'status':<7} {'time_ms':>9} {'queries':>8}")
        for path, status, ms, count in results:
            print(f"{path:<24} {status:<7} {ms:>9.1f} {count:>8}")
