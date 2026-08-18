from decimal import Decimal

from flask_babel import gettext

from extensions import db
from models import FixedAsset
from utils.helpers import generate_number
from utils.tenanting import get_active_tenant_id


class AssetService:
    @staticmethod
    def _tid(user):
        return get_active_tenant_id(user)

    @classmethod
    def create_asset(cls, data, user):
        tid = cls._tid(user)
        asset = FixedAsset(
            tenant_id=tid,
            asset_number=generate_number("FA", FixedAsset, "asset_number"),
            name_ar=data["name_ar"],
            name_en=data.get("name_en"),
            description=data.get("description"),
            category=data.get("category", "equipment"),
            asset_account_id=int(data["asset_account_id"]),
            depreciation_account_id=int(data.get("depreciation_account_id"))
            if data.get("depreciation_account_id")
            else None,
            expense_account_id=int(data.get("expense_account_id")) if data.get("expense_account_id") else None,
            purchase_date=data["purchase_date"],
            purchase_price=Decimal(str(data["purchase_price"])),
            salvage_value=Decimal(str(data.get("salvage_value", 0))),
            depreciation_method=data.get("depreciation_method", "straight_line"),
            useful_life_years=int(data["useful_life_years"]),
            useful_life_months=int(data.get("useful_life_months", 0)) or None,
            location=data.get("location"),
            cost_center_id=int(data["cost_center_id"]) if data.get("cost_center_id") else None,
            branch_id=int(data["branch_id"]) if data.get("branch_id") else None,
            book_value=Decimal(str(data["purchase_price"])),
            status="active",
            notes=data.get("notes"),
            created_by=user.id,
        )
        db.session.add(asset)
        db.session.flush()
        return asset

    @classmethod
    def update_asset(cls, asset, data):
        if asset.status not in ("active", "fully_depreciated"):
            raise ValueError(gettext("لا يمكن تعديل أصل غير نشط."))

        updatable_fields = [
            "name_ar",
            "name_en",
            "description",
            "category",
            "location",
            "notes",
        ]
        for field in updatable_fields:
            if field in data and data[field] is not None:
                setattr(asset, field, data[field])
        db.session.flush()
        return asset

    @classmethod
    def list_assets(cls, user, filters=None):
        tid = cls._tid(user)
        query = FixedAsset.query.filter_by(tenant_id=tid)
        filters = filters or {}
        if filters.get("status"):
            query = query.filter_by(status=filters["status"])
        if filters.get("category"):
            query = query.filter_by(category=filters["category"])
        if filters.get("branch_id"):
            query = query.filter_by(branch_id=int(filters["branch_id"]))
        return query.order_by(FixedAsset.created_at.desc()).all()

    @classmethod
    def post_manual_depreciation(cls, asset, period_date=None):
        if asset.status != "active":
            raise ValueError(gettext("الأصل غير نشط."))
        schedule = asset.post_depreciation(period_date=period_date)
        if schedule is None:
            raise ValueError(gettext("لا يوجد استهلاك لهذا الشهر."))
        return schedule

    @classmethod
    def dispose_asset(cls, asset, disposal_date, disposal_price, notes=None, user=None):
        if asset.status in ("disposed", "sold"):
            raise ValueError(gettext("تم التخلص من الأصل مسبقاً"))
        asset.dispose(disposal_date, disposal_price, notes=notes)
        return asset

    @classmethod
    def get_depreciation_schedule(cls, asset_id, user):
        tid = cls._tid(user)
        asset = FixedAsset.query.filter_by(id=asset_id, tenant_id=tid).first()
        if not asset:
            raise ValueError(gettext("الأصل غير موجود."))
        return asset.depreciation_schedules

    @classmethod
    def get_asset_summary(cls, user):
        tid = cls._tid(user)
        total = FixedAsset.query.filter_by(tenant_id=tid).count()
        active = FixedAsset.query.filter_by(tenant_id=tid, status="active").count()
        disposed = FixedAsset.query.filter(
            FixedAsset.tenant_id == tid,
            FixedAsset.status.in_(["disposed", "sold"]),
        ).count()
        total_cost = (
            db.session.query(db.func.coalesce(db.func.sum(FixedAsset.purchase_price), Decimal("0")))
            .filter(FixedAsset.tenant_id == tid)
            .scalar()
        )
        total_depreciation = (
            db.session.query(db.func.coalesce(db.func.sum(FixedAsset.accumulated_depreciation), Decimal("0")))
            .filter(FixedAsset.tenant_id == tid)
            .scalar()
        )
        return {
            "total": total,
            "active": active,
            "disposed": disposed,
            "total_cost": Decimal(str(total_cost)),
            "total_depreciation": Decimal(str(total_depreciation)),
        }
