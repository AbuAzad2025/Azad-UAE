from flask import Blueprint, abort, current_app, render_template, request
from flask_babel import gettext
from flask_login import current_user, login_required

from extensions import limiter
from models import ProductReturn, Sale
from services.logging_core import LoggingCore
from services.return_service import ReturnService
from utils.api_response import error_response, paginated_response, success_response
from utils.branching import should_show_all_branch_columns
from utils.db_safety import atomic_transaction
from utils.decorators import branch_scope_id, permission_required
from utils.tenanting import tenant_get_or_404

returns_bp = Blueprint("returns", __name__, url_prefix="/returns")


def _scoped_returns_query():
    return ReturnService.get_scoped_returns_query(current_user, branch_scope_id())


@returns_bp.route("/")
@login_required
@permission_required("manage_sales")
def index():
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)

    pagination = (
        _scoped_returns_query()
        .order_by(ProductReturn.return_date.desc())
        .paginate(page=page, per_page=per_page, error_out=False)
    )

    return render_template(
        "returns/index.html",
        returns=pagination.items,
        pagination=pagination,
        show_branch_columns=should_show_all_branch_columns(current_user),
    )


@returns_bp.route("/api/create", methods=["POST"])
@login_required
@permission_required("manage_sales")
@limiter.limit("10 per minute", methods=["POST"])
def api_create_return():
    try:
        data = request.get_json(silent=True)
        if not data:
            return error_response(message="No data provided", status_code=400)

        sale_id = data.get("sale_id")
        lines = data.get("lines", [])
        notes = data.get("notes")
        manual_refund_amount = data.get("manual_refund_amount", data.get("refund_amount"))

        if not sale_id or not lines:
            return error_response(message="Missing sale_id or lines", status_code=400)

        from utils.tenanting import tenant_get_or_404

        tenant_get_or_404(Sale, sale_id)

        with atomic_transaction("sale_return"):
            result = ReturnService.create_return(
                sale_id=sale_id,
                return_lines_data=lines,
                user=current_user,
                notes=notes,
                manual_refund_amount=manual_refund_amount,
            )

        LoggingCore.log_audit(
            "create",
            "product_returns",
            result.id,
            changes={
                "return_number": result.return_number,
                "sale_id": result.sale_id,
                "refund_amount": float(result.refund_amount or 0),
                "manual_refund_amount": manual_refund_amount,
            },
        )

        return success_response(
            data={
                "return_id": result.id,
                "return_number": result.return_number,
                "refund_amount": float(result.refund_amount or 0),
                "amount_aed": float(result.amount_aed or 0),
            },
            message="Return processed successfully",
        )

    except ValueError:
        return error_response(message=gettext("بيانات المرتجع غير صالحة"), status_code=400)
    except Exception as e:
        current_app.logger.error(f"Error creating return: {e}")
        return error_response(message="Internal server error", status_code=500)


@returns_bp.route("/api/search_sales")
@login_required
@permission_required("manage_sales")
def api_search_sales():
    """Search sales for return creation (select2 AJAX)."""
    q = (request.args.get("q") or "").strip()
    page = request.args.get("page", 1, type=int)
    per_page = 20

    if not q:
        return success_response(data=[])

    items, pagination = ReturnService.search_sales_for_return(q, page, per_page, user=current_user)

    return paginated_response(
        items=items,
        page=pagination.page,
        per_page=per_page,
        total=pagination.total,
    )


@returns_bp.route("/api/get_sale_lines")
@login_required
@permission_required("manage_sales")
def api_get_sale_lines():
    """Get sale lines for return creation."""
    sale_id = request.args.get("sale_id", type=int)
    if not sale_id:
        return error_response(message="Missing sale_id", status_code=400)

    sale = tenant_get_or_404(Sale, sale_id)

    lines = []
    for line in sale.lines:
        # Calculate available quantity (sold - already returned)
        returned_qty = sum(
            rl.quantity for r in sale.returns for rl in r.lines if rl.line_id == line.id and r.status == "approved"
        )
        available = (line.quantity or 0) - returned_qty
        if available <= 0:
            continue
        lines.append(
            {
                "id": line.id,
                "line_id": line.id,
                "product_name": line.product.name if line.product else "—",
                "variant": line.variant_name or "",
                "available_qty": available,
                "unit_price": float(line.unit_price or 0),
            }
        )

    return success_response(data={"lines": lines})


@returns_bp.route("/view/<int:id>")
@login_required
@permission_required("manage_sales")
def view(**kwargs):
    record_id = kwargs.pop("id")
    product_return = _scoped_returns_query().filter(ProductReturn.id == record_id).first()
    if not product_return:
        abort(404)

    return render_template("returns/view.html", product_return=product_return)
