from decimal import Decimal
from datetime import datetime, timezone
from extensions import db


class CampaignService:

    @staticmethod
    def get_active_campaigns(tenant_id, product_ids=None, category_ids=None):
        now = datetime.now(timezone.utc)
        query = Campaign.query.filter_by(tenant_id=tenant_id, is_active=True).filter(
            Campaign.start_date <= now,
            Campaign.end_date >= now
        )
        if product_ids:
            from sqlalchemy import or_
            product_filter = Campaign.applicable_products.op('&&')(product_ids)
            category_filter = Campaign.applicable_categories.op('&&')(category_ids)
            query = query.filter(or_(product_filter, category_filter))
        return query.all()

    @staticmethod
    def apply_campaigns(sale, campaigns):
        total_discount = Decimal('0')
        for campaign in campaigns:
            discount = Decimal('0')
            if campaign.campaign_type == 'percentage':
                discount = (sale.subtotal * campaign.discount_value / Decimal('100')).quantize(Decimal('0.001'))
            elif campaign.campaign_type == 'fixed':
                discount = campaign.discount_value
            if campaign.max_discount_amount:
                discount = min(discount, campaign.max_discount_amount)
            if discount > 0:
                sc = SaleCampaign(
                    tenant_id=sale.tenant_id,
                    campaign_id=campaign.id,
                    sale_id=sale.id,
                    discount_amount=discount
                )
                db.session.add(sc)
                campaign.usage_count += 1
                total_discount += discount
        return total_discount

    @staticmethod
    def validate_coupon(coupon_code, tenant_id):
        now = datetime.now(timezone.utc)
        campaign = Campaign.query.filter_by(
            tenant_id=tenant_id,
            coupon_code=coupon_code,
            is_active=True
        ).filter(
            Campaign.start_date <= now,
            Campaign.end_date >= now
        ).first()
        if campaign and (campaign.usage_limit is None or campaign.usage_count < campaign.usage_limit):
            return campaign
        return None