from flask import Blueprint, abort, current_app, render_template, request
from flask_babel import gettext
from flask_login import current_user, login_required
from werkzeug.exceptions import NotFound

from extensions import limiter
from models import ProductReturn, Sale
from services.idempotency_service import (
    IdempotencyHashMismatchError,
    IdempotencyInFlightError,
    IdempotencyService,
    hash_request_payload,
)
from services.logging_core import LoggingCore
from services.return_service import ReturnService
from utils.api_response import error_response, paginated_response, success_response
from utils.branching import should_show_all_branch_columns
from utils.db_safety import atomic_transaction
from utils.decorators import branch_scope_id, permission_required
from utils.tenanting import get_active_tenant_id, tenant_get_or_404

returns_bp = Blueprint("returns", __name__, url_prefix="/returns")


def _scoped_returns_query():
    return ReturnService.get_scoped_returns_query(current_user, branch_scope_id())


def _begin_idem(payload, key):
    """Begin an idempotent return inside the caller's transaction."""
    tid = get_active_tenant_id(current_user)
    request_hash = hash_request_payload({k: v for k, v in (payload or {}).items() if k != "idempotency_key"})
    try:
        record, stored = IdempotencyService.begin(
            tenant_id=int(tid or 0),
            endpoint="returns.create",
            key=key,
            user_id=getattr(current_user, "id", None),
            request_hash=request_hash,
        )
    except IdempotencyInFlightError:
        return (
            None,
            None,
            error_response(message=gettext("طلب مكرر قيد المعالجة حالياً. أعد المحاولة بعد لحظات."), status_code=409),
        )
    except IdempotencyHashMismatchError:
        return (
            None,
            None,
            error_response(message=gettext("مفتاح عدم التكرار استُخدم مع بيانات مختلفة."), status_code=422),
        )
    if stored is not None:
        body, status = stored
        return None, (body, status), None
    return record, None, None


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

        tenant_get_or_404(Sale, sale_id)

        idempotency_key = request.headers.get("Idempotency-Key") or data.get("idempotency_key")
        with atomic_transaction("sale_return"):
            idem_record = None
            if idempotency_key:
                idem_record, idem_stored, idem_error = _begin_idem(data, idempotency_key)
                if idem_error:
                    return idem_error
                if idem_stored is not None:
                    stored_body, stored_status = idem_stored
                    replay_data = {k: v for k, v in stored_body.items() if k != "success"}
                    return success_response(
                        data=replay_data,
                        meta={"idempotent_replay": True},
                        status_code=stored_status,
                    )
            result = ReturnService.create_return(
                sale_id=sale_id,
                return_lines_data=lines,
                user=current_user,
                notes=notes,
                manual_refund_amount=manual_refund_amount,
            )
            response_body = {
                "return_id": result.id,
                "return_number": result.return_number,
                "refund_amount": float(result.refund_amount or 0),
                "amount_aed": float(result.amount_aed or 0),
            }
            if idem_record is not None:
                IdempotencyService.complete(idem_record, response_body, 201)

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
            data=response_body,
            message="Return processed successfully",
        )

    except ValueError:
        return error_response(message=gettext("بيانات المرتجع غير صالحة"), status_code=400)
    except NotFound:
        # tenant_get_or_404 raises NotFound, which is an HTTPException rather than
        # a ValueError, so the broad handler below used to swallow it and answer
        # 500 "Internal server error" for a sale id that simply does not exist.
        # Re-raise it so Flask turns it into the 404 it was always meant to be.
        raise
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
                # SaleLine has no variant_name column - referencing it raised
                # AttributeError, so /returns/api/get_sale_lines answered 500 for
                # every sale that had a line, which is every sale worth returning
                # against. `notes` is the per-line free-text field that carries
                # this, so that is what the picker now shows.
                "variant": line.notes or "",
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
