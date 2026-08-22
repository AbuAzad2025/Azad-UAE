from flask import Blueprint, request
from flask_login import current_user, login_required

from extensions import limiter
from utils.api_response import error_response, paginated_response, success_response
from utils.cache_decorators import cached_query
from utils.decorators import permission_required
from utils.query_optimizer import optimize_query, paginate_optimized
from utils.tenanting import get_active_tenant_id

api_enhanced_bp = Blueprint("api_enhanced", __name__, url_prefix="/api/v2")


@api_enhanced_bp.route("/sales", methods=["GET"])
@login_required
@permission_required("manage_sales")
@limiter.limit("100 per minute")
@cached_query(timeout=60, key_prefix="api_sales_list")
def get_sales():
    from models import Sale

    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)

    tid = get_active_tenant_id(current_user)
    query = optimize_query(Sale, relationships=["customer", "seller", "lines"], strategy="joined")
    query = query.filter(Sale.is_active)
    if tid:
        query = query.filter(Sale.tenant_id == tid)

    query = query.order_by(Sale.sale_date.desc())

    pagination = paginate_optimized(query, page=page, per_page=per_page)

    return paginated_response(
        items=[sale.to_dict(include_lines=True) for sale in pagination.items],
        page=pagination.page,
        per_page=pagination.per_page,
        total=pagination.total,
    )


@api_enhanced_bp.route("/sales/<int:sale_id>", methods=["GET"])
@login_required
@permission_required("manage_sales")
def get_sale(sale_id):
    from models import Sale

    tid = get_active_tenant_id(current_user)
    query = optimize_query(Sale, relationships=["customer", "seller", "lines"], strategy="joined")
    query = query.filter(Sale.id == sale_id)
    if tid:
        query = query.filter(Sale.tenant_id == tid)

    sale = query.first_or_404()

    return success_response(data={"sale": sale.to_dict(include_lines=True, include_cost=current_user.can_see_costs())})


@api_enhanced_bp.route("/customers", methods=["GET"])
@login_required
@permission_required("manage_customers")
@limiter.limit("100 per minute")
@cached_query(timeout=60, key_prefix="api_customers_list")
def get_customers():
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)

    tid = get_active_tenant_id(current_user)

    from services.customer_service import CustomerService

    pagination = CustomerService.list_active_paginated(tid, page, per_page)

    return paginated_response(
        items=[c.to_dict() for c in pagination.items],
        page=pagination.page,
        per_page=pagination.per_page,
        total=pagination.total,
    )


@api_enhanced_bp.route("/products/search", methods=["GET"])
@login_required
@permission_required("manage_products")
@limiter.limit("200 per minute")
def search_products():
    query_text = request.args.get("q", "")
    limit = request.args.get("limit", 20, type=int)

    if not query_text:
        return error_response("Query required", status_code=200)

    tid = get_active_tenant_id(current_user)

    from services.product_service import ProductService

    products = ProductService.search_active_products(query_text, tid, limit)

    return success_response(data={"products": [p.to_dict() for p in products], "count": len(products)})


@api_enhanced_bp.route("/analytics/sales-forecast", methods=["GET"])
@login_required
@permission_required("view_reports")
@cached_query(timeout=300, key_prefix="api_sales_forecast")
def sales_forecast():
    from services.ai_service import AIService

    days = request.args.get("days", 7, type=int)
    forecast = AIService.predict_sales_trend(days_ahead=days)

    return success_response(data=forecast)


@api_enhanced_bp.route("/analytics/profit-margins", methods=["GET"])
@login_required
@permission_required("view_reports")
@cached_query(timeout=300, key_prefix="api_profit_margins")
def profit_margins():
    from services.ai_service import AIService

    analysis = AIService.analyze_profit_margins()
    return success_response(data=analysis)
