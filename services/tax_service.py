"""
Tax Calculation Service — Phase 9
Dispatches to country-specific strategy based on Tenant.vat_country.
"""

import logging
from decimal import Decimal

from extensions import db

logger = logging.getLogger(__name__)


class TaxService:
    """خدمة حساب الضريبة حسب الدولة"""

    @staticmethod
    def _get_strategy(tenant_id=None):
        from models import Tenant
        from utils.localization import get_strategy
        from utils.tenanting import get_active_tenant_id

        if tenant_id is None:
            tenant_id = get_active_tenant_id()
        tenant = Tenant.query.get(tenant_id) if tenant_id else None
        country = (getattr(tenant, "vat_country", None) or "AE").strip().upper()
        return get_strategy(country)

    @classmethod
    def calculate_sale_tax(cls, sale, tenant_id=None) -> dict:
        """
        حساب ضريبة البيع (Output VAT) استناداً إلى strategy الدولة.
        """
        strategy = cls._get_strategy(tenant_id)
        amount = Decimal(str(sale.amount_aed or 0))
        tax_rate = Decimal(str(sale.tax_rate or 0))
        result = strategy.calculate_tax(amount, tax_rate)
        return {
            "strategy": strategy.country_code,
            "tax_amount": result["tax_amount"],
            "net_amount": result["net_amount"],
            "total_amount": result["total_amount"],
            "rate_applied": result["rate_applied"],
        }

    @classmethod
    def calculate_purchase_tax(cls, purchase, tenant_id=None) -> dict:
        """
        حساب ضريبة المشتريات (Input VAT / VAT Recovery).
        """
        strategy = cls._get_strategy(tenant_id)
        amount = Decimal(str(purchase.amount_aed or 0))
        tax_rate = Decimal(str(purchase.tax_rate or 0))
        result = strategy.calculate_tax(amount, tax_rate)
        return {
            "strategy": strategy.country_code,
            "tax_amount": result["tax_amount"],
            "net_amount": result["net_amount"],
            "total_amount": result["total_amount"],
            "rate_applied": result["rate_applied"],
        }

    @classmethod
    def get_vat_return(cls, date_from: str, date_to: str, tenant_id=None) -> dict:
        """
        تقرير VAT موحد — يستخدم GL (القيود المحاسبية) بدلاً من فواتير المبيعات/المشتريات مباشرة.
        """
        from services.gl_service import GLService

        strategy = cls._get_strategy(tenant_id)
        # No fallback. These amounts are what gets filed with the tax authority:
        # emitting a return of 0/0 because the GL report failed would understate
        # the liability and is unrecoverable once filed. Let the caller's
        # transaction roll back and surface the error instead.
        #
        # A GL report that cannot answer is not a failure: a tenant whose chart
        # of accounts does not exist yet has no VAT to file, and the report
        # says so with a zero balance instead of refusing to render. The
        # accounts it could not resolve are reported back, so a zero return
        # that means "nothing configured" is not mistaken for a zero return
        # that means "nothing owed".
        gl_report = GLService.get_vat_report(
            date_from=date_from or None,
            date_to=date_to or None,
            tenant_id=tenant_id,
        )
        unresolved = list(gl_report.get("unresolved_accounts") or [])
        if unresolved:
            logger.warning(
                "VAT return for tenant %s could not resolve GL accounts %s; the return reports them as zero",
                tenant_id,
                ", ".join(unresolved),
            )
        output_vat = Decimal(str(gl_report.get("vat_output", 0)))
        input_vat = Decimal(str(gl_report.get("vat_input", 0)))

        result = strategy.format_tax_return(output_vat, input_vat, date_from, date_to)
        result["source"] = "gl"
        result["unresolved_accounts"] = unresolved
        result["category_totals"] = cls._category_sales_totals(tenant_id, date_from, date_to)
        return result

    @staticmethod
    def _category_sales_totals(tenant_id, date_from, date_to) -> dict:
        """Net sales per line VAT category for the return period.

        The authority form asks for net amounts per category (standard /
        zero-rated / exempt); the GL totals alone cannot say what zero-rated
        output was. Confirmed sales carry the same category the invoice was
        posted with, so the split is derivable per period.
        """
        from sqlalchemy import func

        from models import Sale, SaleLine
        from utils.currency_utils import convert_and_quantize_aed

        categories = {"standard": Decimal("0"), "zero": Decimal("0"), "exempt": Decimal("0")}
        if tenant_id is None:
            return {key: float(value) for key, value in categories.items()}
        query = (
            db.session.query(
                SaleLine.tax_category,
                SaleLine.line_total,
                Sale.currency,
                Sale.exchange_rate,
            )
            .outerjoin(Sale, SaleLine.sale_id == Sale.id)
            .filter(
                Sale.tenant_id == tenant_id,
                Sale.status == "confirmed",
            )
        )
        if date_from:
            query = query.filter(func.date(Sale.sale_date) >= date_from)
        if date_to:
            query = query.filter(func.date(Sale.sale_date) <= date_to)
        for category, line_total, currency, rate in query.all():
            key = (category or "standard").strip().lower()
            if key not in categories:
                key = "standard"
            converted = convert_and_quantize_aed(
                Decimal(str(line_total or 0)),
                currency or "AED",
                Decimal(str(rate or 1)),
                tenant_id=tenant_id,
            )
            categories[key] += converted
        return {key: float(value) for key, value in categories.items()}
