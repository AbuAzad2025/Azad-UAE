from datetime import datetime, timezone
from decimal import Decimal
from extensions import db


class CampaignService:

    @staticmethod
    def get_active_campaigns(tenant_id, product_ids=None, category_ids=None):
        from models.campaign import Campaign

        now = datetime.now(timezone.utc)
        query = Campaign.query.filter_by(tenant_id=tenant_id, is_active=True).filter(
            Campaign.start_date <= now,
            Campaign.end_date >= now,
        )

        if product_ids:
            product_ids = set(product_ids)
            query = query.filter(
                (Campaign.applicable_products.is_(None)) |
                (Campaign.applicable_products == []) |
                (Campaign.applicable_products.overlap(product_ids))
            )

        if category_ids:
            category_ids = set(category_ids)
            query = query.filter(
                (Campaign.applicable_categories.is_(None)) |
                (Campaign.applicable_categories == []) |
                (Campaign.applicable_categories.overlap(category_ids))
            )

        return query.order_by(Campaign.created_at.desc()).all()

    @staticmethod
    def apply_campaigns(sale, campaigns):
        from models.campaign import SaleCampaign

        total_discount = Decimal('0')
        now = datetime.now(timezone.utc)

        for campaign in campaigns:
            if campaign.usage_limit and campaign.usage_count >= campaign.usage_limit:
                continue

            discount = Decimal('0')
            if campaign.campaign_type == 'percentage':
                discount = (Decimal(str(sale.subtotal)) * Decimal(str(campaign.discount_value)) / Decimal('100')).quantize(Decimal('0.001'))
                if campaign.max_discount_amount:
                    discount = min(discount, Decimal(str(campaign.max_discount_amount)))
            elif campaign.campaign_type == 'fixed':
                discount = Decimal(str(campaign.discount_value))
            elif campaign.campaign_type == 'bundle':
                discount = Decimal(str(campaign.discount_value))

            if discount > Decimal('0'):
                sc = SaleCampaign(
                    tenant_id=sale.tenant_id,
                    campaign_id=campaign.id,
                    sale_id=sale.id,
                    discount_amount=discount,
                )
                db.session.add(sc)
                campaign.usage_count += 1
                total_discount += discount

        return total_discount

    @staticmethod
    def validate_coupon(coupon_code, tenant_id):
        from models.campaign import Campaign

        now = datetime.now(timezone.utc)
        return Campaign.query.filter_by(
            tenant_id=tenant_id,
            coupon_code=coupon_code,
            is_active=True,
        ).filter(
            Campaign.start_date <= now,
            Campaign.end_date >= now,
        ).first()