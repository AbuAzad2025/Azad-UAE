"""
Utils Unit Tests
Tests utility functions, validators, tenanting helpers, decorators, and safety wrappers.
"""
import pytest
from decimal import Decimal


class TestValidators:
    """Test input validation utilities."""

    def test_validate_email_valid(self):
        from utils.validators import validate_email
        assert validate_email("test@example.com") == "test@example.com"

    def test_validate_email_invalid(self):
        from utils.validators import validate_email, ValidationError
        with pytest.raises(ValidationError):
            validate_email("not-an-email")

    def test_validate_positive_amount(self):
        from utils.validators import validate_positive_amount, ValidationError
        assert validate_positive_amount("100.50") == Decimal("100.50")
        with pytest.raises(ValidationError):
            validate_positive_amount("-10")

    def test_validate_id(self):
        from utils.validators import validate_id, ValidationError
        assert validate_id("123") == 123
        with pytest.raises(ValidationError):
            validate_id("abc")

    def test_validate_pagination(self):
        from utils.validators import validate_pagination
        page, per_page = validate_pagination(1, 20)
        assert page == 1
        assert per_page == 20
        page, per_page = validate_pagination(0, 200)
        assert page == 1
        assert per_page == 100  # capped


class TestAuthHelpers:
    """Test auth helper functions."""

    def test_role_level_for(self):
        from utils.auth_helpers import role_level_for
        assert role_level_for("owner") >= 100
        assert role_level_for("super_admin") > 0
        assert role_level_for("unknown") == 0

    def test_is_admin_surface_user(self):
        from utils.auth_helpers import is_admin_surface_user
        class FakeUser:
            is_owner = True
        assert is_admin_surface_user(FakeUser()) is True

        class FakeUser2:
            is_owner = False
            role = type("Role", (), {"slug": "super_admin"})()
        assert is_admin_surface_user(FakeUser2()) is True

    def test_is_global_owner_user(self):
        from utils.auth_helpers import is_global_owner_user
        class FakeUser:
            is_owner = True
        assert is_global_owner_user(FakeUser()) is True

        class FakeDev:
            is_owner = False
            role = type("Role", (), {"slug": "developer"})()
        assert is_global_owner_user(FakeDev()) is True

        class FakeNormal:
            is_owner = False
            role = type("Role", (), {"slug": "manager"})()
        assert is_global_owner_user(FakeNormal()) is False

    def test_user_may_have_null_tenant(self):
        from utils.auth_helpers import user_may_have_null_tenant
        assert user_may_have_null_tenant(is_owner=True) is True
        assert user_may_have_null_tenant(
            role=type("Role", (), {"slug": "developer"})()
        ) is True
        assert user_may_have_null_tenant(
            is_owner=False,
            role=type("Role", (), {"slug": "manager"})()
        ) is False


class TestFieldValidators:
    """Test field validation utilities."""

    def test_canonical_payment_type(self):
        from utils.field_validators import canonical_payment_type
        assert canonical_payment_type("sale_payment") == "sale_payment"

    def test_validate_currency_code(self):
        from utils.field_validators import validate_currency_code, FieldValidationError
        assert validate_currency_code("usd") == "USD"
        with pytest.raises(FieldValidationError):
            validate_currency_code("invalid")

    def test_validate_sale_status(self):
        from utils.field_validators import validate_sale_status, FieldValidationError
        assert validate_sale_status("confirmed") == "confirmed"
        with pytest.raises(FieldValidationError):
            validate_sale_status("unknown")


class TestTenantingHelpers:
    """Test tenanting utilities."""

    def test_model_has_tenant(self):
        from utils.tenanting import model_has_tenant
        from models import Product
        assert model_has_tenant(Product) is True

    def test_get_active_tenant_id_unauthenticated(self):
        from utils.tenanting import get_active_tenant_id
        assert get_active_tenant_id() is None

    def test_require_active_tenant_id_raises(self):
        from utils.tenanting import require_active_tenant_id
        from werkzeug.exceptions import Forbidden
        with pytest.raises(Forbidden):
            require_active_tenant_id()

    def test_assert_tenant_record_none(self):
        from utils.tenanting import assert_tenant_record
        from werkzeug.exceptions import NotFound
        with pytest.raises(NotFound):
            assert_tenant_record(None)

    def test_assign_tenant_id_raises_without_tenant(self, db_session, sample_tenant):
        from utils.tenanting import assign_tenant_id
        from werkzeug.exceptions import Forbidden
        from models import Product
        p = Product(name="Test")
        with pytest.raises(Forbidden):
            assign_tenant_id(p, user=None)


class TestDBSafety:
    """Test database safety utilities."""

    def test_atomic_transaction_rolls_back(self, app):
        from utils.db_safety import atomic_transaction
        from extensions import db
        from models import Product

        with app.app_context():
            with pytest.raises(RuntimeError):
                with atomic_transaction("test_fail"):
                    p = Product(name="Rollback Test")
                    db.session.add(p)
                    raise RuntimeError("Intentional failure")

            # Verify product was NOT committed
            result = Product.query.filter_by(name="Rollback Test").first()
            assert result is None

    def test_safe_commit_returns_false_on_error(self, app, monkeypatch):
        from utils.db_safety import safe_commit
        from extensions import db

        def mock_commit():
            raise Exception("DB error")

        monkeypatch.setattr(db.session, "commit", mock_commit)
        result = safe_commit("test")
        assert result is False


class TestGLReferenceTypes:
    """Test GL reference type utilities."""

    def test_gl_ref_constants(self):
        from utils.gl_reference_types import GLRef
        assert GLRef.SALE == "Sale"
        assert GLRef.PURCHASE == "Purchase"


class TestSafeRedirect:
    """Test safe redirect utility."""

    def test_is_safe_redirect_url_allows_internal(self):
        from utils.safe_redirect import is_safe_redirect_url
        assert is_safe_redirect_url("/dashboard") is True

    def test_is_safe_redirect_url_blocks_external(self):
        from utils.safe_redirect import is_safe_redirect_url
        assert is_safe_redirect_url("https://evil.com") is False

    def test_is_safe_redirect_url_blocks_javascript(self):
        from utils.safe_redirect import is_safe_redirect_url
        assert is_safe_redirect_url("javascript:alert(1)") is False


class TestHelpers:
    """Test general helper functions."""

    def test_generate_number_format(self):
        from utils.helpers import generate_number
        from models import Sale
        num = generate_number("SALE", Sale, field_name="sale_number")
        assert num.startswith("SALE-")

    def test_create_audit_log(self, db_session, sample_tenant):
        from utils.helpers import create_audit_log
        from extensions import db
        # This may require app context
        pass


class TestNumberToArabic:
    """Test Arabic number conversion."""

    def test_number_to_arabic_basic(self):
        from utils.number_to_arabic import number_to_arabic_words
        result = number_to_arabic_words(123)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_number_to_arabic_zero(self):
        from utils.number_to_arabic import number_to_arabic_words
        result = number_to_arabic_words(0)
        assert isinstance(result, str)


class TestTaxSettings:
    """Test tax settings utilities."""

    def test_normalize_tax_rate(self):
        from utils.tax_settings import normalize_tax_rate
        assert normalize_tax_rate(5) == Decimal("5")
        assert normalize_tax_rate("5") == Decimal("5")

    def test_should_post_vat_gl(self):
        from utils.tax_settings import should_post_vat_gl
        # Depends on configuration; just verify it runs
        result = should_post_vat_gl()
        assert isinstance(result, bool)

    def test_suggested_rate_for_country(self):
        from utils.tax_settings import suggested_rate_for_country
        rate = suggested_rate_for_country("AE")
        assert isinstance(rate, Decimal)


class TestQueryOptimizer:
    """Test query optimizer utilities."""

    def test_query_optimizer_import(self):
        from utils.query_optimizer import optimize_query
        assert callable(optimize_query)


class TestPasswordValidator:
    """Test password validator utilities."""

    def test_password_validator_class(self):
        from utils.password_validator import PasswordValidator
        pv = PasswordValidator()
        result = pv.validate("StrongPass123!")
        assert isinstance(result, tuple)


class TestConstants:
    """Test constants module."""

    def test_payment_types_exist(self):
        from utils.constants import PAYMENT_TYPES
        assert isinstance(PAYMENT_TYPES, tuple)
        assert len(PAYMENT_TYPES) > 0

    def test_payment_method_codes_exist(self):
        from utils.constants import PAYMENT_METHOD_CODES
        assert isinstance(PAYMENT_METHOD_CODES, tuple)
        assert len(PAYMENT_METHOD_CODES) > 0

    def test_normalize_payment_method_code(self):
        from utils.constants import normalize_payment_method_code
        result = normalize_payment_method_code("Cash")
        assert result == "cash"


# ---------------------------------------------------------------------------
# utils/localization — real behavioural tests (merged from test_localization.py)
# ---------------------------------------------------------------------------
class _FakeSale:
    def __init__(self, id=101, total_aed=Decimal("100.00"), sale_date="2026-06-07"):
        self.id = id
        self.total_aed = total_aed
        self.sale_date = sale_date


class _FakeSaleNoTotal:
    def __init__(self, id=202, amount_aed=Decimal("200.00")):
        self.id = id
        self.amount_aed = amount_aed


class TestLocalizationRegistry:
    def test_get_strategy_palestine(self):
        from utils.localization import get_strategy
        from utils.localization.palestine import PalestineStrategy
        assert isinstance(get_strategy("PS"), PalestineStrategy)

    def test_get_strategy_uae(self):
        from utils.localization import get_strategy
        from utils.localization.uae import UAEStrategy
        assert isinstance(get_strategy("AE"), UAEStrategy)

    def test_get_strategy_ksa(self):
        from utils.localization import get_strategy
        from utils.localization.ksa import KSAStrategy
        assert isinstance(get_strategy("SA"), KSAStrategy)

    def test_get_strategy_unknown_returns_null(self):
        from utils.localization import get_strategy
        from utils.localization.null import NullStrategy
        assert isinstance(get_strategy("ZZ"), NullStrategy)

    def test_get_strategy_none_returns_null(self):
        from utils.localization import get_strategy
        from utils.localization.null import NullStrategy
        assert isinstance(get_strategy(None), NullStrategy)

    def test_get_strategy_trim_and_lower(self):
        from utils.localization import get_strategy
        from utils.localization.palestine import PalestineStrategy
        assert isinstance(get_strategy("  ps  "), PalestineStrategy)

    def test_list_supported_countries(self):
        from utils.localization.registry import list_supported_countries
        assert set(list_supported_countries()) == {"PS", "AE", "SA"}


class TestBaseLocalizationStrategy:
    def test_validate_tax_number_accepted(self):
        from utils.localization.null import NullStrategy
        assert NullStrategy().validate_tax_number("123456789") is True

    def test_validate_tax_number_rejected_short(self):
        from utils.localization.null import NullStrategy
        assert NullStrategy().validate_tax_number("12") is False

    def test_validate_tax_number_rejected_empty(self):
        from utils.localization.null import NullStrategy
        assert NullStrategy().validate_tax_number("") is False

    def test_wps_not_supported_raises(self):
        from utils.localization.uae import UAEStrategy
        with pytest.raises(NotImplementedError):
            UAEStrategy().get_wps_format([])

    def test_cannot_instantiate_abstract(self):
        from utils.localization.engine import LocalizationStrategy
        with pytest.raises(TypeError):
            LocalizationStrategy()


class TestUAEStrategy:
    def test_class_metadata(self):
        s = __import__("utils.localization.uae", fromlist=["UAEStrategy"]).UAEStrategy()
        assert s.country_code == "AE"
        assert s.default_vat_rate == Decimal("5.00")

    def test_calculate_tax_default(self):
        s = __import__("utils.localization.uae", fromlist=["UAEStrategy"]).UAEStrategy()
        r = s.calculate_tax(Decimal("100"))
        assert r["tax_amount"] == Decimal("5.00")
        assert r["total_amount"] == Decimal("105.00")

    def test_calculate_tax_override_rate(self):
        s = __import__("utils.localization.uae", fromlist=["UAEStrategy"]).UAEStrategy()
        r = s.calculate_tax(Decimal("200"), tax_rate=Decimal("10"))
        assert r["tax_amount"] == Decimal("20.00")

    def test_format_tax_return(self):
        s = __import__("utils.localization.uae", fromlist=["UAEStrategy"]).UAEStrategy()
        r = s.format_tax_return(Decimal("500"), Decimal("200"), "2026-01-01", "2026-03-31")
        assert r["net_payable"] == Decimal("300")
        assert r["format"] == "fta_vat201_v1"

    def test_generate_einvoice(self):
        import base64
        s = __import__("utils.localization.uae", fromlist=["UAEStrategy"]).UAEStrategy()
        out = s.generate_einvoice(_FakeSale(id=7, total_aed=Decimal("100")))
        assert "<Invoice" in out["xml_payload"]
        assert "<ID>7</ID>" in out["xml_payload"]
        decoded = base64.b64decode(out["qr_base64"]).decode()
        assert "VAT:5.00" in decoded


class TestPalestineStrategy:
    def test_class_metadata(self):
        s = __import__("utils.localization.palestine", fromlist=["PalestineStrategy"]).PalestineStrategy()
        assert s.country_code == "PS"
        assert s.default_vat_rate == Decimal("16.00")

    def test_calculate_tax_default(self):
        s = __import__("utils.localization.palestine", fromlist=["PalestineStrategy"]).PalestineStrategy()
        r = s.calculate_tax(Decimal("100"))
        assert r["tax_amount"] == Decimal("16.00")
        assert r["total_amount"] == Decimal("116.00")

    def test_wps_format(self):
        s = __import__("utils.localization.palestine", fromlist=["PalestineStrategy"]).PalestineStrategy()
        emps = [
            {"employee_id": "E1", "name": "Ali", "iban": "PS00", "bank_code": "B1", "net_salary": 3000},
        ]
        wps = s.get_wps_format(emps)
        assert wps["format"] == "wps_sif"
        assert len(wps["lines"]) == 2

    def test_wps_empty(self):
        s = __import__("utils.localization.palestine", fromlist=["PalestineStrategy"]).PalestineStrategy()
        wps = s.get_wps_format([])
        assert len(wps["lines"]) == 1


class TestKSAStrategy:
    def test_class_metadata(self):
        s = __import__("utils.localization.ksa", fromlist=["KSAStrategy"]).KSAStrategy()
        assert s.country_code == "SA"
        assert s.zatca_phase == 2

    def test_generate_einvoice_qr(self):
        import base64
        s = __import__("utils.localization.ksa", fromlist=["KSAStrategy"]).KSAStrategy()
        out = s.generate_einvoice(_FakeSale(id=42, total_aed=Decimal("300")))
        decoded = base64.b64decode(out["qr_base64"]).decode()
        assert decoded.startswith("ZATCA|")


class TestNullStrategy:
    def test_tax_is_zero(self):
        s = __import__("utils.localization.null", fromlist=["NullStrategy"]).NullStrategy()
        r = s.calculate_tax(Decimal("100"))
        assert r["tax_amount"] == Decimal("0")
        assert r["total_amount"] == Decimal("100")

    def test_einvoice_empty(self):
        s = __import__("utils.localization.null", fromlist=["NullStrategy"]).NullStrategy()
        out = s.generate_einvoice(_FakeSale())
        assert out["xml_payload"] == "<invoice/>"


# ---------------------------------------------------------------------------
# utils/password_validator.py
# ---------------------------------------------------------------------------
class TestPasswordValidator:
    def test_valid_password(self):
        from utils.password_validator import PasswordValidator
        ok, errs = PasswordValidator.validate("Str0ng!Passphrase")
        assert ok is True and errs == []

    def test_empty_password(self):
        from utils.password_validator import PasswordValidator
        ok, errs = PasswordValidator.validate("")
        assert ok is False and errs == ["\u0643\u0644\u0645\u0629 \u0627\u0644\u0645\u0631\u0648\u0631 \u0645\u0637\u0644\u0648\u0628\u0629"]

    def test_too_short(self):
        from utils.password_validator import PasswordValidator
        ok, errs = PasswordValidator.validate("Ab1!")
        assert ok is False
        assert any("10" in e for e in errs)

    def test_missing_uppercase(self):
        from utils.password_validator import PasswordValidator
        ok, errs = PasswordValidator.validate("longenough1!x")
        assert ok is False
        assert any("\u0643\u0628\u064a\u0631" in e for e in errs)

    def test_missing_lowercase(self):
        from utils.password_validator import PasswordValidator
        ok, errs = PasswordValidator.validate("LONGENOUGH1!X")
        assert ok is False
        assert any("\u0635\u063a\u064a\u0631" in e for e in errs)

    def test_missing_digit(self):
        from utils.password_validator import PasswordValidator
        ok, errs = PasswordValidator.validate("LongEnough!xy")
        assert ok is False
        assert any("\u0631\u0642\u0645" in e for e in errs)

    def test_missing_special(self):
        from utils.password_validator import PasswordValidator
        ok, errs = PasswordValidator.validate("LongEnough1xy")
        assert ok is False
        assert any("\u0631\u0645\u0632 \u062e\u0627\u0635" in e for e in errs)

    def test_common_password_rejected(self):
        from utils.password_validator import PasswordValidator
        ok, errs = PasswordValidator.validate("password123")
        assert ok is False
        assert any("\u0634\u0627\u0626\u0639\u0629" in e for e in errs)

    def test_sequence_rejected(self):
        from utils.password_validator import PasswordValidator
        ok, errs = PasswordValidator.validate("Abc123!xyzZ")
        assert ok is False
        assert any("\u062a\u0633\u0644\u0633\u0644\u0627\u062a" in e for e in errs)

    def test_strength_score(self):
        from utils.password_validator import PasswordValidator
        assert PasswordValidator.get_strength_score("") == 0
        score = PasswordValidator.get_strength_score("V3ry!Long&Uniqu3Passw0rd#X")
        assert 0 <= score <= 100

    def test_strength_labels(self):
        from utils.password_validator import PasswordValidator
        assert PasswordValidator.get_strength_label(10)[1] == "danger"
        assert PasswordValidator.get_strength_label(40)[1] == "warning"
        assert PasswordValidator.get_strength_label(60)[1] == "info"
        assert PasswordValidator.get_strength_label(80)[1] == "primary"
        assert PasswordValidator.get_strength_label(95)[1] == "success"

    def test_generate_suggestion(self):
        from utils.password_validator import PasswordValidator
        suggestion = PasswordValidator.generate_suggestion()
        ok, _ = PasswordValidator.validate(suggestion)
        assert ok is True
        assert len(suggestion) == 12


# ---------------------------------------------------------------------------
# utils/field_validators.py
# ---------------------------------------------------------------------------
class TestFieldValidators:
    def test_currency_code_valid(self):
        from utils.field_validators import validate_currency_code
        assert validate_currency_code("aed") == "AED"

    def test_currency_code_missing_raises(self):
        from utils.field_validators import validate_currency_code, FieldValidationError
        with pytest.raises(FieldValidationError):
            validate_currency_code("  ")

    def test_currency_code_invalid_format(self):
        from utils.field_validators import validate_currency_code, FieldValidationError
        with pytest.raises(FieldValidationError):
            validate_currency_code("DOLLAR")

    def test_phone_none_returns_none(self):
        from utils.field_validators import normalize_phone_optional
        assert normalize_phone_optional(None) is None

    def test_phone_empty_returns_none(self):
        from utils.field_validators import normalize_phone_optional
        assert normalize_phone_optional("   ") is None

    def test_phone_too_long_raises(self):
        from utils.field_validators import normalize_phone_optional, FieldValidationError
        with pytest.raises(FieldValidationError):
            normalize_phone_optional("1" * 51)

    def test_sale_status_valid(self):
        from utils.field_validators import validate_sale_status
        assert validate_sale_status("Confirmed") == "confirmed"

    def test_sale_status_none_not_allowed(self):
        from utils.field_validators import validate_sale_status, FieldValidationError
        with pytest.raises(FieldValidationError):
            validate_sale_status(None)

    def test_sale_status_unsupported(self):
        from utils.field_validators import validate_sale_status, FieldValidationError
        with pytest.raises(FieldValidationError):
            validate_sale_status("archived")

    def test_canonical_payment_type_legacy_sale(self):
        from utils.field_validators import canonical_payment_type, CANONICAL_PAYMENT_TYPE_SALE
        assert canonical_payment_type("sale", for_new=True) == CANONICAL_PAYMENT_TYPE_SALE

    def test_canonical_payment_type_empty_raises(self):
        from utils.field_validators import canonical_payment_type, FieldValidationError
        with pytest.raises(FieldValidationError):
            canonical_payment_type("")

    def test_stock_movement_transfer(self):
        from utils.field_validators import validate_stock_movement_type
        assert validate_stock_movement_type("Transfer") == "transfer"

    def test_stock_movement_unsupported(self):
        from utils.field_validators import validate_stock_movement_type, FieldValidationError
        with pytest.raises(FieldValidationError):
            validate_stock_movement_type("teleport")

    def test_gl_line_sides_debit_only(self):
        from utils.field_validators import validate_gl_line_sides
        validate_gl_line_sides(Decimal("100"), Decimal("0"))

    def test_gl_line_sides_both_zero_raises(self):
        from utils.field_validators import validate_gl_line_sides, FieldValidationError
        with pytest.raises(FieldValidationError):
            validate_gl_line_sides(0, 0)

    def test_gl_line_sides_both_nonzero_raises(self):
        from utils.field_validators import validate_gl_line_sides, FieldValidationError
        with pytest.raises(FieldValidationError):
            validate_gl_line_sides(Decimal("50"), Decimal("50"))


# ---------------------------------------------------------------------------
# utils/sanitizer.py
# ---------------------------------------------------------------------------
class TestInputSanitizer:
    def test_sanitize_html_escapes(self):
        from utils.sanitizer import InputSanitizer
        out = str(InputSanitizer.sanitize_html("<script>alert(1)</script>"))
        assert "<script>" not in out
        assert "&lt;script&gt;" in out

    def test_sanitize_html_empty(self):
        from utils.sanitizer import InputSanitizer
        assert InputSanitizer.sanitize_html("") == ""

    def test_sanitize_text_strips_tags(self):
        from utils.sanitizer import InputSanitizer
        out = str(InputSanitizer.sanitize_text("<b>hello</b> world"))
        assert "<b>" not in out
        assert "hello" in out

    def test_sanitize_text_max_length(self):
        from utils.sanitizer import InputSanitizer
        assert len(InputSanitizer.sanitize_text("abcdefghij", max_length=5)) == 5

    def test_sanitize_email_valid(self):
        from utils.sanitizer import InputSanitizer
        assert InputSanitizer.sanitize_email(" User@Example.COM ") == "user@example.com"

    def test_sanitize_email_invalid(self):
        from utils.sanitizer import InputSanitizer
        assert InputSanitizer.sanitize_email("not-an-email") is None

    def test_sanitize_email_empty(self):
        from utils.sanitizer import InputSanitizer
        assert InputSanitizer.sanitize_email("") is None

    def test_sanitize_phone(self):
        from utils.sanitizer import InputSanitizer
        assert InputSanitizer.sanitize_phone("+971-50-abc-123") == "+971-50--123"

    def test_sanitize_phone_empty(self):
        from utils.sanitizer import InputSanitizer
        assert InputSanitizer.sanitize_phone(None) is None

    def test_sanitize_number_decimal(self):
        from utils.sanitizer import InputSanitizer
        assert InputSanitizer.sanitize_number("3.14") == 3.14

    def test_sanitize_number_int_only(self):
        from utils.sanitizer import InputSanitizer
        assert InputSanitizer.sanitize_number("42", allow_decimal=False) == 42

    def test_sanitize_number_negative_rejected(self):
        from utils.sanitizer import InputSanitizer
        assert InputSanitizer.sanitize_number("-5", allow_negative=False) is None

    def test_sanitize_number_invalid(self):
        from utils.sanitizer import InputSanitizer
        assert InputSanitizer.sanitize_number("abc") is None

    def test_sanitize_sql_input(self):
        from utils.sanitizer import InputSanitizer
        out = InputSanitizer.sanitize_sql_input("1; DROP TABLE users --")
        assert ";" not in out and "--" not in out

    def test_sanitize_form_data_by_rule(self):
        from utils.sanitizer import sanitize_form_data
        cleaned = sanitize_form_data(
            {"email": " A@B.com ", "qty": "10", "name": "<i>John</i>"},
            {"email": {"type": "email"}, "qty": {"type": "number"}}
        )
        assert cleaned["email"] == "a@b.com"
        assert cleaned["qty"] == 10.0
        assert "<i>" not in str(cleaned["name"])


# ---------------------------------------------------------------------------
# utils/api_response.py
# ---------------------------------------------------------------------------
class TestApiResponse:
    def test_success_response(self, app):
        from utils.api_response import success_response
        with app.test_request_context():
            resp, status = success_response(data={"id": 1}, message="ok")
            assert status == 200
            assert resp.get_json()["success"] is True

    def test_error_response(self, app):
        from utils.api_response import error_response
        with app.test_request_context():
            resp, status = error_response("bad", errors=["field required"], status_code=422)
            assert status == 422
            assert resp.get_json()["success"] is False

    def test_error_default_errors(self, app):
        from utils.api_response import error_response
        with app.test_request_context():
            resp, status = error_response("bad")
            assert status == 400
            assert resp.get_json()["errors"] == []

    def test_paginated_response(self, app):
        from utils.api_response import paginated_response
        with app.test_request_context():
            resp, status = paginated_response(items=[1, 2, 3], page=2, per_page=3, total=10)
            assert status == 200
            pag = resp.get_json()["meta"]["pagination"]
            assert pag["page"] == 2
            assert pag["pages"] == 4
            assert pag["has_next"] is True
            assert pag["has_prev"] is True


# ---------------------------------------------------------------------------
# utils/error_messages.py
# ---------------------------------------------------------------------------
class TestErrorMessages:
    def test_user_required_fields(self):
        from utils.error_messages import ErrorMessages
        msg = ErrorMessages.user_required_fields()
        assert "\u0627\u0633\u0645 \u0627\u0644\u0645\u0633\u062a\u062e\u062f\u0645" in msg

    def test_user_exists_message(self):
        from utils.error_messages import ErrorMessages
        msg = ErrorMessages.user_exists("testuser")
        assert "testuser" in msg

    def test_error_helper(self):
        from utils.error_messages import error
        assert error("hello") == "hello"


# ---------------------------------------------------------------------------
# utils/static_asset_paths.py
# ---------------------------------------------------------------------------
class TestStaticAssetPaths:
    def test_logo_constant(self):
        from utils.static_asset_paths import AZAD_LOGO
        assert "logo" in AZAD_LOGO.lower()

    def test_tenant_asset_base(self):
        from utils.static_asset_paths import tenant_asset_base
        assert "tenants" in tenant_asset_base("test")

    def test_tenant_upload_dir(self):
        from utils.static_asset_paths import tenant_upload_dir
        p = tenant_upload_dir(1, "products")
        assert "uploads" in p


# ---------------------------------------------------------------------------
# utils/tax_settings.py
# ---------------------------------------------------------------------------
class TestTaxSettings:
    def test_default_vat(self):
        from utils.tax_settings import default_tax_rate
        assert isinstance(default_tax_rate(), Decimal)

    def test_default_vat_uae(self):
        from utils.tax_settings import suggested_rate_for_country
        r = suggested_rate_for_country("AE")
        assert r == Decimal("5.00")

    def test_tax_enabled(self):
        from utils.tax_settings import is_tax_enabled
        assert is_tax_enabled() in (True, False)

    def test_should_post_vat_gl(self):
        from utils.tax_settings import should_post_vat_gl
        assert should_post_vat_gl() in (True, False)

    def test_normalize_tax_rate(self):
        from utils.tax_settings import normalize_tax_rate
        r = normalize_tax_rate(Decimal("5"))
        assert isinstance(r, Decimal)


# ---------------------------------------------------------------------------
# utils/number_to_arabic.py
# ---------------------------------------------------------------------------
class TestNumberToArabic:
    def test_integer(self):
        from utils.number_to_arabic import number_to_arabic_words
        out = number_to_arabic_words(123)
        assert "\u0645\u0626\u0629" in out or "\u0645\u0627\u0626\u0629" in out

    def test_decimal(self):
        from utils.number_to_arabic import number_to_arabic_words
        out = number_to_arabic_words(Decimal("0.5"))
        assert "\u0641\u0644\u0633" in out

    def test_zero(self):
        from utils.number_to_arabic import number_to_arabic_words
        out = number_to_arabic_words(0)
        assert "\u0635\u0641\u0631" in out

    def test_currency_format(self):
        from utils.number_to_arabic import number_to_arabic_words
        out = number_to_arabic_words(Decimal("2500.50"), currency="AED")
        assert "\u062f\u0631\u0627\u0647\u0645" in out or "\u0623\u0644\u0641" in out

    def test_negative_returns_empty(self):
        from utils.number_to_arabic import number_to_arabic_words
        assert number_to_arabic_words(-5) == ""

    def test_string_number(self):
        from utils.number_to_arabic import number_to_arabic_words
        out = number_to_arabic_words("45")
        assert out != ""

    def test_currency_fallback(self):
        from utils.number_to_arabic import number_to_arabic_words
        out = number_to_arabic_words(Decimal("100"), currency="UNKNOWN")
        assert "\u0645\u0627\u0626\u0629" in out


# ---------------------------------------------------------------------------
# utils/query_optimizer.py
# ---------------------------------------------------------------------------
class TestQueryOptimizer:
    def test_optimize_query_no_relationships(self, app):
        from utils.query_optimizer import optimize_query
        from models import Tenant
        with app.app_context():
            q = optimize_query(Tenant)
            assert q is not None

    def test_paginate_optimized_import(self):
        from utils.query_optimizer import paginate_optimized
        assert callable(paginate_optimized)

    def test_batch_fetch_import(self):
        from utils.query_optimizer import batch_fetch
        assert callable(batch_fetch)

    def test_prefetch_related_import(self):
        from utils.query_optimizer import prefetch_related
        assert callable(prefetch_related)


