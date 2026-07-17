"""Label print — HTML label streams, template variables, cost fallback."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock


def _product(pid=1, **kwargs):
    p = MagicMock()
    p.id = pid
    p.name = kwargs.get("name", "Widget")
    p.name_ar = kwargs.get("name_ar", "أداة")
    p.sku = kwargs.get("sku", "SKU-1")
    p.barcode = kwargs.get("barcode", "1234567890")
    p.sale_price = kwargs.get("sale_price", Decimal("99.00"))
    p.cost_price = kwargs.get("cost_price", Decimal("50.00"))
    p.category = kwargs.get("category", MagicMock(name="Electronics"))
    return p


def _products_from_render(mock_render):
    """Extract the rendered product list from a PrintService.render_print call.

    get_product_labels_html / get_single_label_html pass extra_context as the
    second positional argument, so check both args and kwargs.
    """
    cargs = mock_render.call_args
    extra = cargs.kwargs.get("extra_context")
    if extra is None and len(cargs.args) >= 2:
        extra = cargs.args[1]
    return (extra or {})["products"]


class TestProductLabelsHtml:
    """get_product_labels_html — multi-product barcode label stream."""

    def test_renders_template_with_product_variables(self, app, mocker):
        product = _product()
        mocker.patch(
            "services.label_print_service.tenant_get_or_404", return_value=product
        )
        mock_render = mocker.patch(
            "services.print_service.PrintService.render_print",
            return_value="<html>labels</html>",
        )

        from services.label_print_service import get_product_labels_html

        with app.app_context():
            html = get_product_labels_html([1], tenant_id=5)

        assert html == "<html>labels</html>"
        products = _products_from_render(mock_render)
        assert products[0]["barcode"] == "1234567890"
        assert products[0]["price"] == Decimal("99.00")

    def test_branch_warehouse_cost_overrides_product_cost(self, app, mocker):
        product = _product(cost_price=Decimal("40"))
        pwc = MagicMock(cost_price=Decimal("35.50"))
        mocker.patch(
            "services.label_print_service.tenant_get_or_404", return_value=product
        )

        pwc_q = MagicMock()
        pwc_q.filter_by.return_value.first.return_value = pwc
        mocker.patch(
            "models.ProductWarehouseCost.query",
            new_callable=mocker.PropertyMock,
            return_value=pwc_q,
        )
        mock_render = mocker.patch(
            "services.print_service.PrintService.render_print",
            return_value="ok",
        )

        from services.label_print_service import get_product_labels_html

        with app.app_context():
            get_product_labels_html([1], tenant_id=1, branch_id=7)

        assert _products_from_render(mock_render)[0]["cost"] == Decimal("35.50")

    def test_missing_category_and_barcode_fallbacks(self, app, mocker):
        product = _product(barcode=None)
        product.category = None
        mocker.patch(
            "services.label_print_service.tenant_get_or_404", return_value=product
        )
        mock_render = mocker.patch(
            "services.print_service.PrintService.render_print",
            return_value="ok",
        )

        from services.label_print_service import get_product_labels_html

        with app.app_context():
            get_product_labels_html([1], tenant_id=1)

        row = _products_from_render(mock_render)[0]
        assert row["barcode"] == ""
        assert row["category"] == ""


class TestSingleLabelHtml:
    """get_single_label_html — single ZPL/PDF-ready HTML context."""

    def test_single_label_wraps_product_ctx(self, app, mocker):
        product = _product()
        mock_render = mocker.patch(
            "services.print_service.PrintService.render_print",
            return_value="<label/>",
        )

        from services.label_print_service import get_single_label_html

        with app.app_context():
            html = get_single_label_html(product)

        assert html == "<label/>"
        products = _products_from_render(mock_render)
        assert len(products) == 1
        assert products[0]["sku"] == "SKU-1"

    def test_branch_warehouse_cost_on_single_label(self, app, mocker):
        product = _product(cost_price=Decimal("40"))
        pwc = MagicMock(cost_price=Decimal("33.00"))
        pwc_q = MagicMock()
        pwc_q.filter_by.return_value.first.return_value = pwc
        mocker.patch(
            "models.ProductWarehouseCost.query",
            new_callable=mocker.PropertyMock,
            return_value=pwc_q,
        )
        mock_render = mocker.patch(
            "services.print_service.PrintService.render_print",
            return_value="ok",
        )

        from services.label_print_service import get_single_label_html

        with app.app_context():
            get_single_label_html(product, branch_id=3)

        assert _products_from_render(mock_render)[0]["cost"] == Decimal("33.00")

    def test_invalid_branch_id_uses_product_cost(self, app, mocker):
        product = _product(cost_price=Decimal("12.00"))
        pwc_q = MagicMock()
        pwc_q.filter_by.return_value.first.return_value = None
        mocker.patch(
            "models.ProductWarehouseCost.query",
            new_callable=mocker.PropertyMock,
            return_value=pwc_q,
        )
        mock_render = mocker.patch(
            "services.print_service.PrintService.render_print",
            return_value="ok",
        )

        from services.label_print_service import get_single_label_html

        with app.app_context():
            get_single_label_html(product, branch_id=999)

        assert _products_from_render(mock_render)[0]["cost"] == Decimal("12.00")

    def test_zero_sale_price_fallback(self, app, mocker):
        product = _product(sale_price=None, cost_price=None)
        mock_render = mocker.patch(
            "services.print_service.PrintService.render_print",
            return_value="ok",
        )

        from services.label_print_service import get_single_label_html

        with app.app_context():
            get_single_label_html(product)

        row = _products_from_render(mock_render)[0]
        assert row["price"] == Decimal("0")
        assert row["cost"] == Decimal("0")
