from datetime import datetime, timezone
from decimal import Decimal

from extensions import db


class CampaignService:
    @staticmethod
    def _filter_json_overlap(campaigns, attr, ids):
        allowed = set(ids)
        matched = []
        for campaign in campaigns:
            values = getattr(campaign, attr, None)
            if not values:
                matched.append(campaign)
                continue
            if not isinstance(values, list):
                matched.append(campaign)
                continue
            if set(values) & allowed:
                matched.append(campaign)
        return matched

    @staticmethod
    def calculate_roi(cost, revenue):
        cost_d = Decimal(str(cost or 0))
        revenue_d = Decimal(str(revenue or 0))
        if cost_d == 0:
            return Decimal("0")
        return ((revenue_d - cost_d) / cost_d * Decimal("100")).quantize(
            Decimal("0.01")
        )

    @staticmethod
    def get_campaign_roi_metrics(campaign, total_revenue=None):
        cost = Decimal(str(campaign.discount_value or 0))
        usage = int(getattr(campaign, "usage_count", 0) or 0)
        total_cost = cost * Decimal(str(usage))
        revenue = Decimal(str(total_revenue or 0))
        roi = CampaignService.calculate_roi(total_cost, revenue)
        return {
            "campaign_id": campaign.id,
            "campaign_name": getattr(campaign, "name", ""),
            "unit_cost": float(cost),
            "usage_count": usage,
            "total_cost": float(total_cost),
            "total_revenue": float(revenue),
            "roi": float(roi),
        }

    @staticmethod
    def safe_commission_rate(commission_rate):
        rate = Decimal(str(commission_rate or 0))
        if rate < 0:
            rate = Decimal("0")
        if rate > Decimal("100"):
            rate = Decimal("100")
        return rate

    @staticmethod
    def calculate_safe_commission(total_revenue, commission_rate):
        revenue = Decimal(str(total_revenue or 0))
        rate = CampaignService.safe_commission_rate(commission_rate)
        return (revenue * rate / Decimal("100")).quantize(Decimal("0.01"))

    @staticmethod
    def get_active_campaigns(tenant_id, product_ids=None, category_ids=None):
        from models.campaign import Campaign

        now = datetime.now(timezone.utc)
        query = Campaign.query.filter_by(tenant_id=tenant_id, is_active=True).filter(
            Campaign.start_date <= now,
            Campaign.end_date >= now,
        )

        if product_ids:
            campaigns = CampaignService._filter_json_overlap(
                query.order_by(Campaign.created_at.desc()).all(),
                "applicable_products",
                product_ids,
            )
            if category_ids:
                return CampaignService._filter_json_overlap(
                    campaigns,
                    "applicable_categories",
                    category_ids,
                )
            return campaigns

        if category_ids:
            return CampaignService._filter_json_overlap(
                query.order_by(Campaign.created_at.desc()).all(),
                "applicable_categories",
                category_ids,
            )

        return query.order_by(Campaign.created_at.desc()).all()

    @staticmethod
    def apply_campaigns(sale, campaigns):
        from models.campaign import SaleCampaign

        total_discount = Decimal("0")
        datetime.now(timezone.utc)

        for campaign in campaigns:
            if campaign.usage_limit and campaign.usage_count >= campaign.usage_limit:
                continue

            discount = Decimal("0")
            if campaign.campaign_type == "percentage":
                discount = (
                    Decimal(str(sale.subtotal))
                    * Decimal(str(campaign.discount_value))
                    / Decimal("100")
                ).quantize(Decimal("0.001"))
                if campaign.max_discount_amount:
                    discount = min(discount, Decimal(str(campaign.max_discount_amount)))
            elif campaign.campaign_type == "fixed":
                discount = Decimal(str(campaign.discount_value))
            elif campaign.campaign_type == "bundle":
                discount = Decimal(str(campaign.discount_value))

            if discount > Decimal("0"):
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
        return (
            Campaign.query.filter_by(
                tenant_id=tenant_id,
                coupon_code=coupon_code,
                is_active=True,
            )
            .filter(
                Campaign.start_date <= now,
                Campaign.end_date >= now,
            )
            .first()
        )
