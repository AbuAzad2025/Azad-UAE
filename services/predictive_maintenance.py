from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, Optional
from extensions import db


class PredictiveMaintenanceService:
    @staticmethod
    def predict_next_maintenance(product_id: int) -> Optional[Dict]:
        from models import Sale, SaleLine

        sales_history = (
            db.session.query(SaleLine)
            .join(Sale)
            .filter(SaleLine.product_id == product_id, Sale.status == "confirmed")
            .order_by(Sale.sale_date.desc())
            .limit(10)
            .all()
        )

        if len(sales_history) < 2:
            return None

        intervals = []
        for i in range(len(sales_history) - 1):
            current_sale = sales_history[i].sale
            previous_sale = sales_history[i + 1].sale
            interval = (current_sale.sale_date - previous_sale.sale_date).days
            intervals.append(interval)

        avg_interval = sum(intervals) / len(intervals)
        last_sale_date = sales_history[0].sale.sale_date
        next_maintenance = last_sale_date + timedelta(days=avg_interval)

        days_until = (next_maintenance - datetime.now().date()).days

        confidence = min(len(sales_history) / 10.0, 1.0)

        return {
            "product_id": product_id,
            "last_sale_date": last_sale_date.isoformat(),
            "predicted_next_maintenance": next_maintenance.isoformat(),
            "days_until": max(0, days_until),
            "avg_interval_days": round(avg_interval, 1),
            "confidence": round(confidence, 2),
            "sales_analyzed": len(sales_history),
        }

    @staticmethod
    def get_maintenance_alerts(threshold_days: int = 30) -> list:
        from models import Product

        products = Product.query.filter_by(is_active=True).all()
        alerts = []

        for product in products:
            prediction = PredictiveMaintenanceService.predict_next_maintenance(
                product.id
            )
            if prediction and prediction["days_until"] <= threshold_days:
                alerts.append(
                    {
                        "product_id": product.id,
                        "product_name": product.name,
                        "days_until_maintenance": prediction["days_until"],
                        "urgency": (
                            "high" if prediction["days_until"] <= 7 else "medium"
                        ),
                        "confidence": prediction["confidence"],
                    }
                )

        return sorted(alerts, key=lambda x: x["days_until_maintenance"])

    @staticmethod
    def analyze_product_lifecycle(product_id: int) -> Dict:
        from models import Sale, SaleLine

        sales = (
            db.session.query(SaleLine)
            .join(Sale)
            .filter(SaleLine.product_id == product_id, Sale.status == "confirmed")
            .order_by(Sale.sale_date.asc())
            .all()
        )

        if not sales:
            return {"status": "no_data"}

        total_quantity = sum(Decimal(str(line.quantity)) for line in sales)
        first_sale = sales[0].sale.sale_date
        last_sale = sales[-1].sale.sale_date
        days_active = (last_sale - first_sale).days or 1

        avg_sales_per_month = (total_quantity / days_active) * 30

        return {
            "product_id": product_id,
            "total_sold": float(total_quantity),
            "first_sale_date": first_sale.isoformat(),
            "last_sale_date": last_sale.isoformat(),
            "days_active": days_active,
            "avg_monthly_sales": round(float(avg_sales_per_month), 2),
            "total_transactions": len(sales),
            "lifecycle_stage": PredictiveMaintenanceService._determine_lifecycle_stage(
                days_active, len(sales)
            ),
        }

    @staticmethod
    def _determine_lifecycle_stage(days_active: int, transaction_count: int) -> str:
        if days_active < 30:
            return "introduction"
        elif days_active < 180 and transaction_count > 10:
            return "growth"
        elif transaction_count > 20:
            return "maturity"
        else:
            return "decline"
