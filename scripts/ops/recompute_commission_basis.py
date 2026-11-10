#!/usr/bin/env python3
"""Re-basis historical product-commission entries on the current margin rules.

The commission margin used to subtract base-currency cost from
invoice-currency revenue (and to gross down zero/exempt lines). Historical
entries carry the stored ``cost_basis`` needed to re-derive them exactly.

Usage:
    python scripts/ops/recompute_commission_basis.py            # dry-run report
    python scripts/ops/recompute_commission_basis.py --apply    # rewrite entries

The rewrite is explicit (never silent): draft distributions of affected
periods are deleted and recreated through ``create_distributions`` so they
reflect the new basis; approved/paid distributions are only reported —
their partner balances and transactions are not touched by this script.
"""

from __future__ import annotations

import argparse
import sys
from decimal import Decimal
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tenant-id", type=int, default=None)
    parser.add_argument("--apply", action="store_true", help="actually rewrite entries")
    args = parser.parse_args()

    from app import create_app
    from extensions import db
    from models import PartnerCommissionEntry, PartnerProfitDistribution, Sale, SaleLine
    from services.partner_service import PartnerService
    from services.sale_service import SaleService

    app = create_app()
    changed = 0
    affected = 0
    with app.app_context():
        query = PartnerCommissionEntry.query
        if args.tenant_id:
            query = query.filter_by(tenant_id=args.tenant_id)
        entries = query.all()
        for entry in entries:
            sale = db.session.get(Sale, entry.sale_id)
            line = db.session.get(SaleLine, entry.sale_line_id) if entry.sale_line_id else None
            if sale is None or line is None:
                print(f"entry {entry.id}: missing sale/line — skipped")
                continue
            margin, base, commission = SaleService.recompute_commission_basis(entry, sale, line)
            old = (
                Decimal(str(entry.profit_margin or 0)),
                Decimal(str(entry.base_amount_aed or 0)),
                Decimal(str(entry.commission_amount_aed or 0)),
            )
            new = (margin, base, commission)
            if old == new:
                continue
            changed += 1
            print(
                f"entry {entry.id} tenant={entry.tenant_id}: "
                f"margin {old[0]} -> {new[0]}, base {old[1]} -> {new[1]}, "
                f"commission {old[2]} -> {new[2]}"
            )
            if args.apply:
                entry.profit_margin, entry.base_amount_aed, entry.commission_amount_aed = new
                affected += 1
        if args.apply and changed:
            db.session.flush()
            db.session.commit()
            # Recreate draft distributions so they use the new basis.

            tenants = {e.tenant_id for e in entries}
            for tenant_id in tenants:
                drafts = PartnerProfitDistribution.query.filter_by(tenant_id=tenant_id, status="draft").all()
                periods = {(d.period_start, d.period_end) for d in drafts}
                for dist in drafts:
                    db.session.delete(dist)
                db.session.flush()
                for period_start, period_end in periods:
                    created = PartnerService.create_distributions(tenant_id, period_start, period_end)
                    print(
                        f"tenant {tenant_id}: recreated {len(created)} draft distributions "
                        f"for {period_start}..{period_end}"
                    )
            print(f"rewrote {affected} commission entries")
        else:
            print(f"dry-run: {changed} entries would change (run with --apply to rewrite)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
