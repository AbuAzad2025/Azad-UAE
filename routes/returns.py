from flask import Blueprint, request, jsonify, render_template, current_app
from flask_login import login_required, current_user
from services.return_service import ReturnService
from models import Sale, ProductReturn
from utils.decorators import permission_required, branch_scope_id
from utils.branching import should_show_all_branch_columns

returns_bp = Blueprint('returns', __name__, url_prefix='/returns')


@returns_bp.route('/')
@login_required
@permission_required('manage_sales')
def index():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)

    query = ProductReturn.query.join(Sale)
    if current_user.is_seller():
        query = query.filter(Sale.seller_id == current_user.id)
    branch_id = branch_scope_id()
    if branch_id is not None:
        query = query.filter(Sale.branch_id == branch_id)
    pagination = query.order_by(ProductReturn.return_date.desc()).paginate(
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
def api_create_return():
    """
    API Endpoint to create a sales return.
    Expects JSON data:
    {
        "sale_id": int,
        "notes": str,
        "lines": [
            {
                "sale_line_id": int,
                "quantity": float,
                "condition": str,
                "notes": str
            }
        ]
    }
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'message': 'No data provided'}), 400
            
        sale_id = data.get('sale_id')
        lines = data.get('lines', [])
        notes = data.get('notes')
        
        if not sale_id or not lines:
            return jsonify({'success': False, 'message': 'Missing sale_id or lines'}), 400
            
        result = ReturnService.create_return(
            sale_id=sale_id, 
            return_lines_data=lines, 
            user_id=current_user.id, 
            notes=notes
        )
        
        return jsonify({
            'success': True, 
            'message': 'Return processed successfully',
            'return_id': result.id,
            'return_number': result.return_number
        })
        
    except ValueError as e:
        return jsonify({'success': False, 'message': str(e)}), 400
    except Exception as e:
        current_app.logger.error(f"Error creating return: {e}")
        return jsonify({'success': False, 'message': 'Internal server error'}), 500

@returns_bp.route('/view/<int:id>')
@login_required
@permission_required('manage_sales')
def view(id):
    product_return = ProductReturn.query.get_or_404(id)
    if current_user.is_seller():
        if product_return.sale and product_return.sale.seller_id != current_user.id:
            from flask import abort
            abort(403)
    return render_template('returns/view.html', product_return=product_return)
