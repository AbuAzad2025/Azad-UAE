from decimal import Decimal
from flask import render_template
from utils.tenanting import tenant_get_or_404


def get_product_labels_html(product_ids, tenant_id, branch_id=None):
    from models import Product, ProductWarehouseCost
    products = []
    for pid in product_ids:
        p = tenant_get_or_404(Product, pid, tenant_id)
        cost = None
        if branch_id:
            pwc = ProductWarehouseCost.query.filter_by(
                product_id=p.id, warehouse_id=branch_id
            ).first()
            if pwc:
                cost = pwc.cost_price
        if cost is None:
            cost = p.cost_price or Decimal('0')
        products.append({
            'id': p.id,
            'name': p.name,
            'name_ar': p.name_ar or '',
            'sku': p.sku or '',
            'barcode': p.barcode or '',
            'price': p.sale_price or Decimal('0'),
            'cost': cost,
            'category': p.category.name if p.category else '',
        })
    return render_template('printing/product_label.html', products=products)


def get_single_label_html(product, branch_id=None):
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
    ctx = {
        'id': product.id,
        'name': product.name,
        'name_ar': product.name_ar or '',
        'sku': product.sku or '',
        'barcode': product.barcode or '',
        'price': product.sale_price or Decimal('0'),
        'cost': cost,
        'category': product.category.name if product.category else '',
    }
    return render_template('printing/product_label.html', products=[ctx])
