from decimal import Decimal
from services.print_service import PrintService
from utils.tenanting import tenant_get_or_404


def _build_label_context(product, branch_id=None):
    from models import ProductWarehouseCost
    cost = None
    if branch_id:
        pwc = ProductWarehouseCost.query.filter_by(
            product_id=product.id, warehouse_id=branch_id
        ).first()
        if pwc:
            cost = pwc.cost_price
    if cost is None:
        cost = product.cost_price or Decimal('0')
    return {
        'id': product.id,
        'name': product.name,
        'name_ar': product.name_ar or '',
        'sku': product.sku or '',
        'barcode': product.barcode or '',
        'price': product.sale_price or Decimal('0'),
        'cost': cost,
        'category': product.category.name if product.category else '',
    }


def get_product_labels_html(product_ids, tenant_id, branch_id=None):
    from models import Product
    products = []
    for pid in product_ids:
        p = tenant_get_or_404(Product, pid, tenant_id)
        products.append(_build_label_context(p, branch_id))
    return PrintService.render_print(
        'printing/product_label.html',
        {'products': products},
        tenant_id=tenant_id,
    )


def get_single_label_html(product, branch_id=None, tenant_id=None):
    ctx = _build_label_context(product, branch_id)
    return PrintService.render_print(
        'printing/product_label.html',
        {'products': [ctx]},
        tenant_id=tenant_id,
    )
