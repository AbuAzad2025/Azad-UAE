"""Monthly fixed-asset depreciation posting."""

from __future__ import annotations

from datetime import UTC, date

from flask_babel import gettext

from extensions import db
from models.fixed_asset import FixedAsset
from utils.db_safety import atomic_transaction


class DepreciationService:
    @staticmethod
    def run_monthly(tenant_id=None, *, period_year=None, period_month=None):
        from datetime import datetime

        now = datetime.now(UTC)
        period_year = period_year or now.year
        period_month = period_month or now.month
        period_date = date(period_year, period_month, 1)

        query = FixedAsset.query.filter_by(status="active")
        if tenant_id is not None:
            query = query.filter(FixedAsset.tenant_id == int(tenant_id))
        assets = query.all()
        posted = 0
        skipped = 0
        errors = []

        for asset in assets:
            try:
                result = asset.post_depreciation(period_date=period_date)
                if result is None:
                    skipped += 1
                else:
                    posted += 1
            except ValueError as exc:
                msg = str(exc)
                if gettext("مسبقاً") in msg:
                    skipped += 1
                else:
                    errors.append(f"{asset.asset_number}: {msg}")
            except Exception as exc:
                errors.append(f"{asset.asset_number}: {exc}")

        with atomic_transaction("depreciation_run_monthly"):
            db.session.flush()

        return {"posted": posted, "skipped": skipped, "errors": errors}
