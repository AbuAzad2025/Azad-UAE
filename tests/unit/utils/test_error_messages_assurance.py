from __future__ import annotations

import pytest

from utils.error_messages import ErrorMessages, error, warning, hint, success


class TestUserMessages:
    def test_user_required_fields(self):
        assert "اسم المستخدم" in ErrorMessages.user_required_fields()

    def test_user_exists(self):
        msg = ErrorMessages.user_exists("ahmed")
        assert "ahmed" in msg
        assert "ahmed_admin" in msg

    def test_weak_password(self):
        msg = ErrorMessages.weak_password(["too short", "no digit"])
        assert "too short" in msg

    def test_password_mismatch(self):
        assert "غير متطابقتين" in ErrorMessages.password_mismatch()

    def test_user_update_failed(self):
        assert "db fail" in ErrorMessages.user_update_failed("db fail")

    def test_user_delete_self(self):
        assert "حسابك الخاص" in ErrorMessages.user_delete_self()

    def test_user_delete_owner(self):
        assert "المالك" in ErrorMessages.user_delete_owner()


class TestCustomerMessages:
    def test_customer_required_fields(self):
        assert "الاسم" in ErrorMessages.customer_required_fields()

    def test_customer_phone_invalid(self):
        assert "0501234567" in ErrorMessages.customer_phone_invalid()

    def test_customer_email_invalid(self):
        assert "@" in ErrorMessages.customer_email_invalid()

    def test_customer_has_transactions(self):
        assert "Acme" in ErrorMessages.customer_has_transactions("Acme")


class TestProductMessages:
    def test_product_required_fields(self):
        assert "المنتج" in ErrorMessages.product_required_fields()

    def test_product_sku_exists(self):
        assert "SKU-1" in ErrorMessages.product_sku_exists("SKU-1")

    def test_product_negative_stock(self):
        assert "سالباً" in ErrorMessages.product_negative_stock()

    def test_product_low_stock(self):
        msg = ErrorMessages.product_low_stock("Widget", 2, 10)
        assert "Widget" in msg
        assert "2" in msg

    def test_product_out_of_stock(self):
        assert "Widget" in ErrorMessages.product_out_of_stock("Widget")


class TestSaleMessages:
    def test_sale_no_lines(self):
        assert "منتج" in ErrorMessages.sale_no_lines()

    def test_sale_no_customer(self):
        assert "عميل" in ErrorMessages.sale_no_customer()

    def test_sale_insufficient_stock(self):
        msg = ErrorMessages.sale_insufficient_stock("X", 1, 5)
        assert "X" in msg

    def test_sale_invalid_quantity(self):
        assert "صفر" in ErrorMessages.sale_invalid_quantity()

    def test_sale_invalid_price(self):
        assert "صفر" in ErrorMessages.sale_invalid_price()


class TestPaymentMessages:
    def test_payment_amount_zero(self):
        assert "صفر" in ErrorMessages.payment_amount_zero()

    def test_payment_exceeds_due(self):
        msg = ErrorMessages.payment_exceeds_due(200.0, 100.0)
        assert "200.00" in msg

    def test_payment_method_required(self):
        assert "طريقة الدفع" in ErrorMessages.payment_method_required()

    def test_cheque_number_required(self):
        assert "الشيك" in ErrorMessages.cheque_number_required()

    def test_reference_required(self):
        assert "المرجعي" in ErrorMessages.reference_required()


class TestWarehouseMessages:
    def test_warehouse_not_found(self):
        assert "المستودع" in ErrorMessages.warehouse_not_found()

    def test_stock_adjustment_invalid(self):
        assert "التعديل" in ErrorMessages.stock_adjustment_invalid()


class TestPermissionMessages:
    def test_permission_denied(self):
        assert "delete" in ErrorMessages.permission_denied("delete")

    def test_owner_only_message(self):
        assert "للمالك" in ErrorMessages.owner_only_message()

    def test_admin_only(self):
        assert "للمديرين" in ErrorMessages.admin_only()


class TestFileMessages:
    def test_file_type_not_allowed(self):
        msg = ErrorMessages.file_type_not_allowed(["pdf", "png"])
        assert "pdf" in msg

    def test_file_too_large(self):
        assert "10MB" in ErrorMessages.file_too_large(10)

    def test_file_upload_failed(self):
        assert "disk" in ErrorMessages.file_upload_failed("disk")


class TestDatabaseMessages:
    def test_database_error(self):
        assert "قاعدة البيانات" in ErrorMessages.database_error()

    def test_unexpected_error(self):
        assert "غير متوقع" in ErrorMessages.unexpected_error()

    @pytest.mark.parametrize(
        "entity",
        [
            "customer",
            "product",
            "sale",
            "user",
            "supplier",
            "warehouse",
            "cheque",
            "ledger",
            "unknown",
        ],
    )
    def test_create_failed(self, entity):
        assert ErrorMessages.create_failed(entity)

    @pytest.mark.parametrize(
        "entity",
        [
            "customer",
            "product",
            "sale",
            "user",
            "supplier",
            "warehouse",
            "cheque",
            "ledger",
            "unknown",
        ],
    )
    def test_update_failed(self, entity):
        assert ErrorMessages.update_failed(entity)

    @pytest.mark.parametrize(
        "entity",
        [
            "customer",
            "product",
            "sale",
            "user",
            "supplier",
            "warehouse",
            "cheque",
            "ledger",
            "unknown",
        ],
    )
    def test_delete_failed(self, entity):
        assert ErrorMessages.delete_failed(entity)

    def test_action_failed(self):
        assert "import" in ErrorMessages.action_failed("import")

    def test_whatsapp_failed(self):
        assert "WhatsApp" in ErrorMessages.whatsapp_failed()

    @pytest.mark.parametrize(
        "entity", ["customer", "product", "sale", "user", "unknown"]
    )
    def test_record_not_found(self, entity):
        assert ErrorMessages.record_not_found(entity)

    def test_duplicate_entry(self):
        msg = ErrorMessages.duplicate_entry("email", "a@b.com")
        assert "a@b.com" in msg


class TestValidationMessages:
    def test_invalid_email(self):
        assert "@" in ErrorMessages.invalid_email()

    def test_invalid_phone(self):
        assert "0501234567" in ErrorMessages.invalid_phone()

    def test_invalid_number(self):
        assert "qty" in ErrorMessages.invalid_number("qty")

    def test_invalid_date(self):
        assert "YYYY-MM-DD" in ErrorMessages.invalid_date()

    def test_invalid_currency(self):
        assert "AED" in ErrorMessages.invalid_currency()


class TestBackupMessages:
    def test_backup_wrong_password(self):
        assert "كلمة المرور" in ErrorMessages.backup_wrong_password()

    def test_backup_corrupted(self):
        assert "تالفة" in ErrorMessages.backup_corrupted()

    def test_backup_not_found(self):
        assert "غير موجودة" in ErrorMessages.backup_not_found()

    def test_backup_failed(self):
        assert "disk" in ErrorMessages.backup_failed("disk")


class TestSecurityMessages:
    def test_rate_limit_exceeded(self):
        assert "الحد" in ErrorMessages.rate_limit_exceeded()

    def test_session_expired(self):
        assert "الجلسة" in ErrorMessages.session_expired()

    def test_csrf_error(self):
        assert "CSRF" in ErrorMessages.csrf_error()

    def test_unexpected_error_with_id(self):
        assert "ERR-1" in ErrorMessages.unexpected_error("ERR-1")

    def test_required_field(self):
        assert "name" in ErrorMessages.required_field("name")

    def test_invalid_format(self):
        assert "2025-01-01" in ErrorMessages.invalid_format("date", "2025-01-01")


class TestSuccessMessages:
    @pytest.mark.parametrize(
        "entity",
        ["customer", "product", "sale", "user", "payment", "expense", "unknown"],
    )
    def test_success_create(self, entity):
        assert ErrorMessages.success_create(entity)

    @pytest.mark.parametrize(
        "entity", ["customer", "product", "sale", "user", "unknown"]
    )
    def test_success_update(self, entity):
        assert ErrorMessages.success_update(entity)

    @pytest.mark.parametrize("entity", ["customer", "product", "user", "unknown"])
    def test_success_delete(self, entity):
        assert ErrorMessages.success_delete(entity)


class TestHelperWrappers:
    def test_error_wrapper(self):
        assert error("msg") == "msg"

    def test_warning_wrapper(self):
        assert warning("warn") == "warn"

    def test_hint_wrapper(self):
        assert hint("tip") == "tip"

    def test_success_wrapper(self):
        assert success("ok") == "ok"
