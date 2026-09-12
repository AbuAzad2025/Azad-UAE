"""Cov5: store_checkout_service — existing-customer empty-fields branches."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock

import pytest


def test_shop_account_existing_customer_empty_fields(
    mocker,
    tenant_store,
    sample_customer,
    sample_user,
    sample_product_with_stock,
):
    from services.store_checkout_service import StoreCheckoutService

    mocker.patch(
        "services.store_checkout_service.StorePaymentMethodService.validate_for_checkout",
        return_value=MagicMock(code="cod", name_ar="COD"),
    )
    mocker.patch(
        "services.store_checkout_service.StoreService.online_stock_map",
        return_value={sample_product_with_stock.id: Decimal("10")},
    )
    mocker.patch(
        "services.store_checkout_service.StockService.check_availability_in_warehouse",
        return_value=(True, ""),
    )
    sale_mock = MagicMock()
    create = mocker.patch(
        "services.store_checkout_service.SaleService.create_sale",
        return_value=sale_mock,
    )
    mocker.patch(
        "services.store_notification_service.StoreNotificationService.notify_new_order",
    )
    account = MagicMock(customer_id=sample_customer.id)
    sample_user.is_owner = True
    StoreCheckoutService.create_web_order(
        tenant_store,
        {str(sample_product_with_stock.id): 1},
        "",
        "",
        "",
        shop_account=account,
    )
    assert create.call_args.kwargs["customer"].id == sample_customer.id


def test_build_lines_missing_product_raises(mocker, sample_tenant, online_warehouse):
    from services.store_checkout_service import StoreCheckoutService

    mocker.patch(
        "services.store_checkout_service.StoreService.online_stock_map",
        return_value={},
    )
    with pytest.raises(ValueError, match="غير متاح"):
        StoreCheckoutService.build_lines_from_cart(sample_tenant.id, {"999999999": 1}, online_warehouse.id)


def test_build_lines_unavailable_raises(
    mocker, sample_tenant, online_warehouse, sample_product_with_stock
):
    from services.store_checkout_service import StoreCheckoutService

    mocker.patch(
        "services.store_checkout_service.StoreService.online_stock_map",
        return_value={sample_product_with_stock.id: Decimal("10")},
    )
    mocker.patch(
        "services.store_checkout_service.StockService.check_availability_in_warehouse",
        return_value=(False, "short"),
    )
    with pytest.raises(ValueError, match="short"):
        StoreCheckoutService.build_lines_from_cart(
            sample_tenant.id, {str(sample_product_with_stock.id): 1}, online_warehouse.id
        )
