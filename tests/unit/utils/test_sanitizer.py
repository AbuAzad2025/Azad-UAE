from __future__ import annotations

from unittest.mock import MagicMock, patch

from markupsafe import Markup

from utils import sanitizer as sanitizer_module
from utils.sanitizer import InputSanitizer, sanitize_form_data


class TestSanitizeHtml:
    def test_resolve_bleach_success(self):
        import sys
        from utils.sanitizer import _resolve_bleach

        stub = MagicMock(name="bleach_module")
        saved = sys.modules.get("bleach")
        sys.modules["bleach"] = stub
        try:
            mod, available = _resolve_bleach()
            assert available is True
            assert mod is stub
        finally:
            if saved is None:
                sys.modules.pop("bleach", None)
            else:
                sys.modules["bleach"] = saved

    def test_empty_returns_empty_string(self):
        assert InputSanitizer.sanitize_html("") == ""
        assert InputSanitizer.sanitize_html(None) == ""

    def test_escapes_without_allowed_tags(self):
        result = InputSanitizer.sanitize_html("<script>alert(1)</script>")
        assert isinstance(result, Markup)
        assert "&lt;script&gt;" in str(result)

    def test_allow_tags_uses_bleach_when_available(self):
        bleach_mock = MagicMock()
        bleach_mock.clean.return_value = "<b>safe</b>"
        with (
            patch.object(sanitizer_module, "_BLEACH_AVAILABLE", True),
            patch.object(sanitizer_module, "bleach", bleach_mock),
        ):
            result = InputSanitizer.sanitize_html("<b>safe</b><script>x</script>", allow_tags=True)

        bleach_mock.clean.assert_called_once_with(
            "<b>safe</b><script>x</script>",
            tags=InputSanitizer.ALLOWED_TAGS,
            attributes=InputSanitizer.ALLOWED_ATTRS,
            strip=True,
        )
        assert result == "<b>safe</b>"

    def test_allow_tags_falls_back_to_escape_without_bleach(self):
        with patch.object(sanitizer_module, "_BLEACH_AVAILABLE", False):
            result = InputSanitizer.sanitize_html("<i>x</i>", allow_tags=True)
        assert "&lt;i&gt;" in str(result)

    def test_bleach_import_error_sets_unavailable_flag(self):
        from utils.sanitizer import _resolve_bleach

        import builtins

        real_import = builtins.__import__

        def blocked_import(name, globals_dict=None, locals_dict=None, fromlist=(), level=0):
            if name == "bleach":
                raise ImportError("blocked for test")
            return real_import(name, globals_dict, locals_dict, fromlist, level)

        with patch.object(builtins, "__import__", side_effect=blocked_import):
            mod, available = _resolve_bleach()
        assert available is False
        assert mod is None

    def test_bleach_import_error_legacy_reload(self):
        import importlib
        import sys

        mod_name = "utils.sanitizer"
        saved = sys.modules.pop(mod_name, None)
        try:
            import builtins

            real_import = builtins.__import__

            def blocked_import(name, globals_dict=None, locals_dict=None, fromlist=(), level=0):
                if name == "bleach":
                    raise ImportError("blocked for test")
                return real_import(name, globals_dict, locals_dict, fromlist, level)

            with patch.object(builtins, "__import__", side_effect=blocked_import):
                mod = importlib.import_module(mod_name)
            assert mod._BLEACH_AVAILABLE is False
            assert mod.bleach is None
        finally:
            if saved is not None:
                sys.modules[mod_name] = saved
            importlib.import_module(mod_name)


class TestSanitizeText:
    def test_empty_returns_empty_string(self):
        assert InputSanitizer.sanitize_text(None) == ""

    def test_strips_tags_escapes_and_trims(self):
        result = InputSanitizer.sanitize_text("  <b>hi</b> & you  ")
        assert "<b>" not in str(result)
        assert "&amp;" in str(result)
        assert str(result).startswith("hi")

    def test_truncates_to_max_length(self):
        result = InputSanitizer.sanitize_text("abcdef", max_length=3)
        assert str(result) == "abc"


class TestSanitizeEmail:
    def test_empty_returns_none(self):
        assert InputSanitizer.sanitize_email("") is None
        assert InputSanitizer.sanitize_email(None) is None

    def test_valid_email_normalized(self):
        assert InputSanitizer.sanitize_email("  User@Mail.Example  ") == "user@mail.example"

    def test_invalid_email_returns_none(self):
        assert InputSanitizer.sanitize_email("not-email") is None


class TestSanitizePhone:
    def test_empty_returns_none(self):
        assert InputSanitizer.sanitize_phone(None) is None

    def test_keeps_allowed_characters(self):
        assert InputSanitizer.sanitize_phone("  +971 (50) 123-4567!  ") == "+971 (50) 123-4567"


class TestSanitizeNumber:
    def test_empty_returns_none(self):
        assert InputSanitizer.sanitize_number(None) is None
        assert InputSanitizer.sanitize_number("") is None

    def test_parses_decimal_and_integer_modes(self):
        assert InputSanitizer.sanitize_number("12.5") == 12.5
        assert InputSanitizer.sanitize_number("9", allow_decimal=False) == 9

    def test_rejects_negative_when_disallowed(self):
        assert InputSanitizer.sanitize_number(-3, allow_negative=False) is None

    def test_invalid_input_returns_none(self):
        assert InputSanitizer.sanitize_number("abc") is None
        assert InputSanitizer.sanitize_number("1.5", allow_decimal=False) is None


class TestSanitizeSqlInput:
    def test_empty_returns_empty_string(self):
        assert InputSanitizer.sanitize_sql_input("") == ""

    def test_strips_dangerous_tokens(self):
        raw = "admin'; DROP TABLE users; -- /*xp_*/ exec execute sp_cmd"
        cleaned = InputSanitizer.sanitize_sql_input(raw)
        for token in (";", "--", "/*", "*/", "xp_", "sp_", "exec", "execute"):
            assert token not in cleaned
        assert "admin" in cleaned


class TestSanitizeFormData:
    def test_applies_per_field_rules(self):
        with (
            patch.object(InputSanitizer, "sanitize_email", return_value="a@b.co") as email_fn,
            patch.object(InputSanitizer, "sanitize_phone", return_value="+971501234567"),
            patch.object(InputSanitizer, "sanitize_number", return_value=10),
            patch.object(InputSanitizer, "sanitize_html", return_value=Markup("<b>x</b>")) as html_fn,
            patch.object(InputSanitizer, "sanitize_text", return_value="plain") as text_fn,
        ):
            form_data = {
                "email": "a@b.co",
                "phone": "+971",
                "qty": "10",
                "body": "<b>x</b>",
                "name": "plain",
            }
            rules = {
                "email": {"type": "email"},
                "phone": {"type": "phone"},
                "qty": {"type": "number"},
                "body": {"type": "html"},
                "name": {"type": "text", "max_length": 50},
            }
            cleaned = sanitize_form_data(form_data, rules)

        assert cleaned["email"] == "a@b.co"
        assert cleaned["phone"] == "+971501234567"
        assert cleaned["qty"] == 10
        assert cleaned["body"] == Markup("<b>x</b>")
        assert cleaned["name"] == "plain"
        html_fn.assert_called_once_with("<b>x</b>", allow_tags=True)
        text_fn.assert_called_once_with("plain", 50)
        email_fn.assert_called_once()

    def test_default_text_rule_without_rules_dict(self):
        cleaned = sanitize_form_data({"note": "  hello  "})
        assert "note" in cleaned
        assert str(cleaned["note"]) == "hello"
