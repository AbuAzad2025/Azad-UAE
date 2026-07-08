from flask import Blueprint, request, jsonify, render_template, current_app, abort
from flask_login import login_required, current_user

from extensions import db, limiter
from services.return_service import ReturnService
from models import Sale, ProductReturn
from utils.decorators import permission_required, branch_scope_id
from utils.db_safety import atomic_transaction
from utils.branching import should_show_all_branch_columns
from services.logging_core import LoggingCore
from utils.tenanting import get_active_tenant_id, is_platform_owner


returns_bp = Blueprint('returns', __name__, url_prefix='/returns')


def _scoped_returns_query():
    query = ProductReturn.query.join(Sale, ProductReturn.sale_id == Sale.id)

    tenant_id = get_active_tenant_id(current_user)
    if tenant_id is not None:
        query = query.filter(Sale.tenant_id == tenant_id, ProductReturn.tenant_id == tenant_id)
    elif not is_platform_owner(current_user):
        query = query.filter(Sale.tenant_id < 0)
    else:
        query = query.filter(ProductReturn.tenant_id < 0)

    if current_user.is_seller():
        query = query.filter(Sale.seller_id == current_user.id)

    scoped_branch_id = branch_scope_id()
    if scoped_branch_id is not None:
        query = query.filter(Sale.branch_id == scoped_branch_id)

    return query


@returns_bp.route('/')
@login_required
@permission_required('manage_sales')
def index():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)

    pagination = _scoped_returns_query().order_by(ProductReturn.return_date.desc()).paginate(
        page=page,
        per_page=per_page,
        error_out=False
    )

    return render_template(
        'returns/index.html',
        returns=pagination.items,
        pagination=pagination,
        show_branch_columns=should_show_all_branch_columns(current_user),
    )


@returns_bp.route('/api/create', methods=['POST'])
@login_required
@permission_required('manage_sales')
@limiter.limit("10 per minute", methods=['POST'])
def api_create_return():
    try:
        data = request.get_json(silent=True)
        if not data:
            return jsonify({'success': False, 'message': 'No data provided'}), 400

        sale_id = data.get('sale_id')
        lines = data.get('lines', [])
        notes = data.get('notes')
        manual_refund_amount = data.get('manual_refund_amount', data.get('refund_amount'))

        if not sale_id or not lines:
            return jsonify({'success': False, 'message': 'Missing sale_id or lines'}), 400

        from utils.tenanting import tenant_get_or_404
        tenant_get_or_404(Sale, sale_id)

        with atomic_transaction('sale_return'):
            result = ReturnService.create_return(
                sale_id=sale_id,
                return_lines_data=lines,
                user=current_user,
                notes=notes,
                manual_refund_amount=manual_refund_amount
            )

        LoggingCore.log_audit(
            'create',
            'product_returns',
            result.id,
            changes={
                'return_number': result.return_number,
                'sale_id': result.sale_id,
                'refund_amount': float(result.refund_amount or 0),
                'manual_refund_amount': manual_refund_amount,
            }
        )

        return jsonify({
            'success': True,
            'message': 'Return processed successfully',
            'return_id': result.id,
            'return_number': result.return_number,
            'refund_amount': float(result.refund_amount or 0),
            'amount_aed': float(result.amount_aed or 0)
        })

    except ValueError:
        return jsonify({'success': False, 'message': 'بيانات المرتجع غير صالحة'}), 400
    except Exception as e:
        current_app.logger.error(f"Error creating return: {e}")
        return jsonify({'success': False, 'message': 'Internal server error'}), 500


@returns_bp.route('/view/<int:id>')
@login_required
@permission_required('manage_sales')
def view(id):
    product_return = _scoped_returns_query().filter(ProductReturn.id == id).first()
    if not product_return:
        abort(404)

    return render_template('returns/view.html', product_return=product_return)
