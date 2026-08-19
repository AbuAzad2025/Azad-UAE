"""Unit tests for StorePaymentMethodService."""

from __future__ import annotations

import uuid

import pytest

from extensions import db
from models.store_payment_method import StorePaymentMethod
from services.store_payment_method_service import (
    DEFAULT_METHODS,
    StorePaymentMethodService,
)

_TID = 1


@pytest.fixture(autouse=True)
def _app_context(app):
    with app.app_context():
        yield


@pytest.fixture(autouse=True)
def _transaction_rollback(db_session):
    yield
    db_session.rollback()


def _custom(
    db_session,
    *,
    code=None,
    name_ar="طريقة",
    name_en="Method",
    is_enabled=True,
    is_builtin=False,
    sort_order=100,
    config=None,
    tenant_id=_TID,
):
    row = StorePaymentMethod(
        tenant_id=tenant_id,
        code=code or f"custom_{uuid.uuid4().hex[:10]}",
        name_ar=name_ar,
        name_en=name_en,
        is_enabled=is_enabled,
        is_builtin=is_builtin,
        sort_order=sort_order,
    )
    if config:
        row.set_config(config)
    db_session.add(row)
    db_session.flush()
    return row


class TestEnsureDefaults:
    def test_creates_missing_and_skips_existing(self, db_session):
        StorePaymentMethodService.ensure_defaults(tenant_id=_TID)
        before = StorePaymentMethod.query.filter_by(tenant_id=_TID).count()

        StorePaymentMethodService.ensure_defaults(tenant_id=_TID)
        after = StorePaymentMethod.query.filter_by(tenant_id=_TID).count()

        assert after == before
        codes = {m.code for m in StorePaymentMethod.query.filter_by(tenant_id=_TID).all()}
        for item in DEFAULT_METHODS:
            assert item["code"] in codes

    def test_recreates_deleted_defaults(self, db_session):
        StorePaymentMethodService.ensure_defaults(tenant_id=_TID)
        cod = StorePaymentMethod.query.filter_by(tenant_id=_TID, code="cod").first()
        bank = StorePaymentMethod.query.filter_by(tenant_id=_TID, code="bank_transfer").first()
        db_session.delete(cod)
        db_session.delete(bank)
        db_session.flush()

        StorePaymentMethodService.ensure_defaults(tenant_id=_TID)

        recreated_cod = StorePaymentMethod.query.filter_by(tenant_id=_TID, code="cod").first()
        recreated_bank = StorePaymentMethod.query.filter_by(tenant_id=_TID, code="bank_transfer").first()
        assert recreated_cod is not None
        assert recreated_cod.is_builtin is True
        assert recreated_bank is not None
        assert recreated_bank.get_config().get("iban") == ""

    def test_commit_failure_rolls_back(self, db_session, mocker):
        mocker.patch.object(db.session, "commit", side_effect=RuntimeError("db fail"))
        with pytest.raises(RuntimeError, match="db fail"):
            StorePaymentMethodService.ensure_defaults(tenant_id=_TID)


class TestListAll:
    def test_returns_all_ordered(self, db_session):
        _custom(db_session, sort_order=5)
        _custom(db_session, sort_order=1)
        rows = StorePaymentMethodService.list_all(tenant_id=_TID)
        orders = [m.sort_order for m in rows]
        assert orders == sorted(orders)

    def test_enabled_only(self, db_session):
        enabled = _custom(db_session, is_enabled=True)
        _custom(db_session, is_enabled=False)
        rows = StorePaymentMethodService.list_all(enabled_only=True, tenant_id=_TID)
        assert all(m.is_enabled for m in rows)
        assert enabled.id in {m.id for m in rows}


class TestListForCheckout:
    def test_excludes_online_pay_when_not_configured(self, db_session, mocker):
        StorePaymentMethodService.ensure_defaults(tenant_id=_TID)
        online = StorePaymentMethod.query.filter_by(tenant_id=_TID, code="online_pay").first()
        if online:
            online.is_enabled = True
            db_session.flush()
        mocker.patch(
            "services.store_online_payment_service.StoreOnlinePaymentService.is_configured",
            return_value=False,
        )
        codes = {m.code for m in StorePaymentMethodService.list_for_checkout(tenant_id=_TID)}
        assert "online_pay" not in codes

    def test_includes_online_pay_when_configured(self, db_session, mocker):
        StorePaymentMethodService.ensure_defaults(tenant_id=_TID)
        online = StorePaymentMethod.query.filter_by(tenant_id=_TID, code="online_pay").first()
        online.is_enabled = True
        db_session.flush()
        mocker.patch(
            "services.store_online_payment_service.StoreOnlinePaymentService.is_configured",
            return_value=True,
        )
        codes = {m.code for m in StorePaymentMethodService.list_for_checkout(tenant_id=_TID)}
        assert "online_pay" in codes

    def test_import_error_filters_online_pay(self, db_session, mocker):
        mocker.patch.dict("sys.modules", {"services.store_online_payment_service": None})
        StorePaymentMethodService.ensure_defaults(tenant_id=_TID)
        online = StorePaymentMethod.query.filter_by(tenant_id=_TID, code="online_pay").first()
        if online:
            online.is_enabled = True
            db_session.flush()
        codes = {m.code for m in StorePaymentMethodService.list_for_checkout(tenant_id=_TID)}
        assert "online_pay" not in codes


class TestGetByCode:
    def test_empty_code_returns_none(self):
        assert StorePaymentMethodService.get_by_code("", tenant_id=_TID) is None
        assert StorePaymentMethodService.get_by_code("   ", tenant_id=_TID) is None

    def test_finds_normalized_code(self, db_session):
        row = _custom(db_session, code="my_gateway")
        found = StorePaymentMethodService.get_by_code("  MY_GATEWAY ", tenant_id=_TID)
        assert found is not None
        assert found.id == row.id


class TestValidateForCheckout:
    def test_missing_raises(self):
        with pytest.raises(ValueError, match="غير متاحة"):
            StorePaymentMethodService.validate_for_checkout("nonexistent_xyz", tenant_id=_TID)

    def test_disabled_raises(self, db_session):
        row = _custom(db_session, is_enabled=False)
        with pytest.raises(ValueError, match="غير متاحة"):
            StorePaymentMethodService.validate_for_checkout(row.code, tenant_id=_TID)

    def test_enabled_returns_method(self, db_session):
        row = _custom(db_session, is_enabled=True)
        assert StorePaymentMethodService.validate_for_checkout(row.code, tenant_id=_TID).id == row.id


class TestToggleEnabled:
    def test_not_found_raises(self):
        with pytest.raises(ValueError, match="غير موجودة"):
            StorePaymentMethodService.toggle_enabled(999999999, True, tenant_id=_TID)

    def test_toggles_and_commits(self, db_session):
        row = _custom(db_session, is_enabled=False)
        updated = StorePaymentMethodService.toggle_enabled(row.id, True, tenant_id=_TID)
        assert updated.is_enabled is True

    def test_commit_failure_raises(self, db_session, mocker):
        row = _custom(db_session)
        mocker.patch.object(db.session, "commit", side_effect=RuntimeError("commit fail"))
        with pytest.raises(RuntimeError, match="commit fail"):
            StorePaymentMethodService.toggle_enabled(row.id, False, tenant_id=_TID)


class TestCreateMethod:
    def test_duplicate_code_raises(self, db_session):
        row = _custom(db_session, code="dup_code")
        with pytest.raises(ValueError, match="مستخدم مسبقاً"):
            StorePaymentMethodService.create_method({"code": row.code, "name_en": "X"}, tenant_id=_TID)

    def test_short_names_raises(self):
        with pytest.raises(ValueError, match="الاسم"):
            StorePaymentMethodService.create_method(
                {"code": "valid_code", "name_ar": "", "name_en": ""}, tenant_id=_TID
            )

    def test_creates_with_config_and_name_fallback(self, db_session):
        method = StorePaymentMethodService.create_method(
            {
                "code": f"new_{uuid.uuid4().hex[:8]}",
                "name_en": "Wire",
                "bank_name": "Test Bank",
                "iban": "AE123",
                "is_enabled": True,
                "sort_order": 55,
            },
            tenant_id=_TID,
        )
        assert method.name_ar == "Wire"
        assert method.name_en == "Wire"
        assert method.get_config()["bank_name"] == "Test Bank"
        assert method.is_builtin is False

    def test_commit_failure_raises(self, mocker):
        mocker.patch.object(db.session, "commit", side_effect=RuntimeError("create fail"))
        with pytest.raises(RuntimeError, match="create fail"):
            StorePaymentMethodService.create_method(
                {
                    "code": f"fail_{uuid.uuid4().hex[:8]}",
                    "name_ar": "اختبار",
                },
                tenant_id=_TID,
            )


class TestUpdateMethod:
    def test_not_found_raises(self):
        with pytest.raises(ValueError, match="غير موجودة"):
            StorePaymentMethodService.update_method(999999999, {"name_ar": "x"}, tenant_id=_TID)

    def test_updates_fields_and_custom_code(self, db_session):
        row = _custom(db_session, code=f"old_{uuid.uuid4().hex[:8]}")
        new_code = f"new_{uuid.uuid4().hex[:8]}"
        updated = StorePaymentMethodService.update_method(
            row.id,
            {
                "name_ar": "جديد",
                "name_en": "New",
                "description_ar": "وصف",
                "icon": "fas fa-star",
                "is_enabled": False,
                "sort_order": 77,
                "code": new_code,
                "providers": "Apple Pay",
                "instructions": "Follow steps",
            },
            tenant_id=_TID,
        )
        assert updated.code == new_code
        assert updated.name_ar == "جديد"
        assert updated.sort_order == 77
        cfg = updated.get_config()
        assert cfg["providers"] == "Apple Pay"
        assert cfg["instructions"] == "Follow steps"

    def test_builtin_ignores_code_change(self, db_session):
        StorePaymentMethodService.ensure_defaults(tenant_id=_TID)
        cod = StorePaymentMethod.query.filter_by(tenant_id=_TID, code="cod").first()
        updated = StorePaymentMethodService.update_method(
            cod.id, {"code": "other_code", "name_ar": "COD"}, tenant_id=_TID
        )
        assert updated.code == "cod"

    def test_code_clash_raises(self, db_session):
        a = _custom(db_session, code="code_a")
        b = _custom(db_session, code="code_b")
        with pytest.raises(ValueError, match="مستخدم مسبقاً"):
            StorePaymentMethodService.update_method(b.id, {"code": a.code}, tenant_id=_TID)

    def test_removes_empty_config_keys(self, db_session):
        row = _custom(db_session, config={"providers": "Old", "instructions": "Keep"})
        updated = StorePaymentMethodService.update_method(
            row.id,
            {
                "providers": "",
                "instructions": "Updated",
            },
            tenant_id=_TID,
        )
        cfg = updated.get_config()
        assert "providers" not in cfg
        assert cfg["instructions"] == "Updated"

    def test_commit_failure_raises(self, db_session, mocker):
        row = _custom(db_session)
        mocker.patch.object(db.session, "commit", side_effect=RuntimeError("update fail"))
        with pytest.raises(RuntimeError, match="update fail"):
            StorePaymentMethodService.update_method(row.id, {"name_ar": "x"}, tenant_id=_TID)


class TestDeleteMethod:
    def test_not_found_raises(self):
        with pytest.raises(ValueError, match="غير موجودة"):
            StorePaymentMethodService.delete_method(999999999, tenant_id=_TID)

    def test_builtin_raises(self, db_session):
        StorePaymentMethodService.ensure_defaults(tenant_id=_TID)
        cod = StorePaymentMethod.query.filter_by(tenant_id=_TID, code="cod").first()
        with pytest.raises(ValueError, match="الأساسية"):
            StorePaymentMethodService.delete_method(cod.id, tenant_id=_TID)

    def test_deletes_custom(self, db_session):
        row = _custom(db_session)
        method_id = row.id
        StorePaymentMethodService.delete_method(method_id, tenant_id=_TID)
        assert db.session.get(StorePaymentMethod, method_id) is None

    def test_commit_failure_raises(self, db_session, mocker):
        row = _custom(db_session)
        mocker.patch.object(db.session, "commit", side_effect=RuntimeError("delete fail"))
        with pytest.raises(RuntimeError, match="delete fail"):
            StorePaymentMethodService.delete_method(row.id, tenant_id=_TID)


class TestFormatCheckoutInstructions:
    def test_bank_transfer_details(self, db_session):
        StorePaymentMethodService.ensure_defaults(tenant_id=_TID)
        row = StorePaymentMethod.query.filter_by(tenant_id=_TID, code="bank_transfer").first()
        row.set_config(
            {
                "bank_name": "Emirates NBD",
                "iban": "AE001",
                "account_name": "Store LLC",
            }
        )
        text = StorePaymentMethodService.format_checkout_instructions(row, lang="en")
        assert "Emirates NBD" in text
        assert "AE001" in text
        assert "Store LLC" in text

    def test_instructions_and_providers(self, db_session):
        row = _custom(db_session, config={"instructions": "Pay via link"})
        assert "Pay via link" in StorePaymentMethodService.format_checkout_instructions(row)

        row2 = _custom(db_session, config={"providers": "Google Pay"})
        assert "Google Pay" in StorePaymentMethodService.format_checkout_instructions(row2)

    def test_description_only(self, db_session):
        row = _custom(db_session, name_ar="AR", name_en="EN")
        row.description_en = "English desc"
        db_session.flush()
        text = StorePaymentMethodService.format_checkout_instructions(row, lang="en")
        assert "English desc" in text
