from datetime import datetime, timezone, timedelta
from extensions import db


class WarrantyService:
    @staticmethod
    def create_claim(sale_line, claim_type, description):
        from models.warranty_claim import WarrantyClaim

        product = sale_line.product
        sale = sale_line.sale

        claim = WarrantyClaim(
            tenant_id=sale.tenant_id,
            sale_id=sale.id,
            sale_line_id=sale_line.id,
            product_id=product.id,
            claim_type=claim_type,
            description=description,
            warranty_start_date=sale.sale_date,
            warranty_end_date=sale.sale_date
            + timedelta(days=product.warranty_days or 0),
        )
        db.session.add(claim)
        return claim

    @staticmethod
    def get_active_warranties(tenant_id):
        from models.warranty_claim import WarrantyClaim

        now = datetime.now(timezone.utc)
        return (
            WarrantyClaim.query.filter(
                WarrantyClaim.tenant_id == tenant_id,
                WarrantyClaim.warranty_end_date >= now,
                WarrantyClaim.status != "resolved",
            )
            .order_by(WarrantyClaim.warranty_end_date.asc())
            .all()
        )

    @staticmethod
    def get_expiring_warranties(days=30, tenant_id=None):
        from models.warranty_claim import WarrantyClaim
        from utils.tenanting import get_active_tenant_id

        now = datetime.now(timezone.utc)
        end = now + timedelta(days=days)
        tid = tenant_id if tenant_id is not None else get_active_tenant_id()
        return (
            WarrantyClaim.query.filter(
                WarrantyClaim.tenant_id == tid,
                WarrantyClaim.warranty_end_date >= now,
                WarrantyClaim.warranty_end_date <= end,
                WarrantyClaim.status != "resolved",
            )
            .order_by(WarrantyClaim.warranty_end_date.asc())
            .all()
        )
