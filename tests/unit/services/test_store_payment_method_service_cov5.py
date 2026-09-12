"""Cov5: store_payment_method_service — missing-tenant, empty-key, empty-config arcs."""

from __future__ import annotations

import uuid


def _custom(db_session, tenant_id, **kw):
    from services.store_payment_method_service import StorePaymentMethod

    params = {
        "tenant_id": tenant_id,
        "code": f"cov5_{uuid.uuid4().hex[:8]}",
        "name_ar": "طريقة",
        "name_en": "Method",
        "is_enabled": True,
        "is_builtin": False,
        "sort_order": 100,
    }
    params.update(kw)
    row = StorePaymentMethod(**params)
    db_session.add(row)
    db_session.flush()
    return row


def test_ensure_defaults_missing_tenant_returns(db_session):
    from services.store_payment_method_service import StorePaymentMethodService

    assert StorePaymentMethodService.ensure_defaults(tenant_id=999999999) is None


def test_ensure_defaults_resolves_tenant(mocker, db_session):
    from services.store_payment_method_service import StorePaymentMethodService

    mocker.patch("services.store_payment_method_service.get_active_tenant_id", return_value=None)
    assert StorePaymentMethodService.ensure_defaults() is None


def test_update_pops_only_missing_keys(db_session, sample_tenant):
    from services.store_payment_method_service import StorePaymentMethodService

    row = _custom(db_session, sample_tenant.id)
    row.set_config({"iban": "AE001"})
    db_session.flush()
    updated = StorePaymentMethodService.update_method(
        row.id, {"bank_name": "", "iban": "AE002"}, tenant_id=sample_tenant.id
    )
    cfg = updated.get_config()
    assert "bank_name" not in cfg
    assert cfg["iban"] == "AE002"


def test_format_bank_transfer_empty_config(db_session, sample_tenant):
    from services.store_payment_method_service import StorePaymentMethodService

    row = _custom(db_session, sample_tenant.id, code="bank_transfer")
    assert StorePaymentMethodService.format_checkout_instructions(row) == ""
