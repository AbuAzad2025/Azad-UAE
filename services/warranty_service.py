from datetime import datetime, timedelta, timezone
from extensions import db


class WarrantyService:

    @staticmethod
    def create_claim(sale_line, claim_type, description):
        claim = WarrantyClaim(
            tenant_id=sale_line.sale.tenant_id,
            sale_id=sale_line.sale_id,
            sale_line_id=sale_line.id,
            product_id=sale_line.product_id,
            claim_type=claim_type,
            description=description,
            warranty_start_date=sale_line.sale.sale_date,
            warranty_end_date=sale_line.sale.sale_date + timedelta(days=sale_line.product.warranty_days or 0)
        )
        db.session.add(claim)
        return claim

    @staticmethod
    def get_active_warranties(tenant_id):
        now = datetime.now(timezone.utc)
        return WarrantyClaim.query.filter(
            WarrantyClaim.tenant_id == tenant_id,
            WarrantyClaim.warranty_end_date >= now,
            WarrantyClaim.status != 'resolved'
        ).all()

    @staticmethod
    def get_expiring_warranties(days=30):
        now = datetime.now(timezone.utc)
        cutoff = now + timedelta(days=days)
        return WarrantyClaim.query.filter(
            WarrantyClaim.warranty_end_date >= now,
            WarrantyClaim.warranty_end_date <= cutoff,
            WarrantyClaim.status != 'resolved'
        ).all()