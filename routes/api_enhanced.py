from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user
from extensions import limiter
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
    query = optimize_query(
        Sale, relationships=["customer", "seller", "lines"], strategy="joined"
    )
    query = query.filter(Sale.is_active == True)
    if tid:
        query = query.filter(Sale.tenant_id == tid)

    query = query.order_by(Sale.sale_date.desc())

    pagination = paginate_optimized(query, page=page, per_page=per_page)

    return jsonify(
        {
            "success": True,
            "sales": [sale.to_dict(include_lines=True) for sale in pagination.items],
            "total": pagination.total,
            "page": pagination.page,
            "pages": pagination.pages,
        }
    )


@api_enhanced_bp.route("/sales/<int:sale_id>", methods=["GET"])
@login_required
@permission_required("manage_sales")
def get_sale(sale_id):
    from models import Sale

    tid = get_active_tenant_id(current_user)
    query = optimize_query(
        Sale, relationships=["customer", "seller", "lines"], strategy="joined"
    )
    query = query.filter(Sale.id == sale_id)
    if tid:
        query = query.filter(Sale.tenant_id == tid)

    sale = query.first_or_404()

    return jsonify(
        {
            "success": True,
            "sale": sale.to_dict(
                include_lines=True, include_cost=current_user.can_see_costs()
            ),
        }
    )


@api_enhanced_bp.route("/customers", methods=["GET"])
@login_required
@permission_required("manage_customers")
@limiter.limit("100 per minute")
@cached_query(timeout=60, key_prefix="api_customers_list")
def get_customers():
    from models import Customer

    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)

    tid = get_active_tenant_id(current_user)
    query = Customer.query.filter_by(is_active=True)
    if tid:
        query = query.filter(Customer.tenant_id == tid)
    query = query.order_by(Customer.name)
    pagination = paginate_optimized(query, page=page, per_page=per_page)

    return jsonify(
        {
            "success": True,
            "customers": [c.to_dict() for c in pagination.items],
            "total": pagination.total,
            "page": pagination.page,
            "pages": pagination.pages,
        }
    )


@api_enhanced_bp.route("/products/search", methods=["GET"])
@login_required
@permission_required("manage_products")
@limiter.limit("200 per minute")
def search_products():
    from models import Product
    from sqlalchemy import or_

    query_text = request.args.get("q", "")
    limit = request.args.get("limit", 20, type=int)

    if not query_text:
        return jsonify({"success": False, "error": "Query required"})

    tid = get_active_tenant_id(current_user)
    products = Product.query.filter(
        Product.is_active == True,
        or_(
            Product.name.ilike(f"%{query_text}%"),
            Product.name_ar.ilike(f"%{query_text}%"),
            Product.sku.ilike(f"%{query_text}%"),
            Product.barcode.ilike(f"%{query_text}%"),
        ),
    )
    if tid:
        products = products.filter(Product.tenant_id == tid)
    products = products.limit(limit).all()

    return jsonify(
        {
            "success": True,
            "products": [p.to_dict() for p in products],
            "count": len(products),
        }
    )


@api_enhanced_bp.route("/analytics/sales-forecast", methods=["GET"])
@login_required
@permission_required("view_reports")
@cached_query(timeout=300, key_prefix="api_sales_forecast")
def sales_forecast():
    from services.ai_service import AIService

    days = request.args.get("days", 7, type=int)
    forecast = AIService.predict_sales_trend(days_ahead=days)

    return jsonify(forecast)


@api_enhanced_bp.route("/analytics/profit-margins", methods=["GET"])
@login_required
@permission_required("view_reports")
@cached_query(timeout=300, key_prefix="api_profit_margins")
def profit_margins():
    from services.ai_service import AIService

    analysis = AIService.analyze_profit_margins()
    return jsonify(analysis)
