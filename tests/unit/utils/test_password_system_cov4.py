"""Cov4: password_validator strength/suggestion + system_init bootstrap paths."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from utils.password_validator import PasswordValidator, validate_password_with_helpful_message


def test_validate_matrix():
    ok, errs = PasswordValidator.validate("")  # 32-33
    assert ok is False
    ok2, errs2 = PasswordValidator.validate("short1A!")
    assert ok2 is False  # length branch 35-36
    ok3, e3 = PasswordValidator.validate("alllowercase123!")
    assert any("كبير" in e for e in e3)  # 38-39
    ok4, e4 = PasswordValidator.validate("ALLUPPERCASE123!")
    assert any("صغير" in e for e in e4)  # 41-42
    ok5, e5 = PasswordValidator.validate("NoDigitsHere!!Aa")
    assert any("رقم" in e for e in e5)  # 44-45
    ok6, e6 = PasswordValidator.validate("NoSpecial123AaBb")
    assert any("رمز" in e for e in e6)  # 47-50
    ok7, e7 = PasswordValidator.validate("password")
    assert any("شائعة" in e or "كبيرة" in e or "صغيرة" in e for e in e7)  # 65-66
    ok8, e8 = PasswordValidator.validate("Abcdefgh12!")
    assert any("تسلسلات" in e for e in e8)  # 68-72
    ok9, _ = PasswordValidator.validate("Str0ng!Passw0rdX")
    assert ok9 is True  # 74


def test_strength_and_labels():
    assert PasswordValidator.get_strength_score("") == 0  # 84-85
    assert PasswordValidator.get_strength_score("aA1!aaaaaaaa") <= 100  # 89-104 incl repeat penalty 101-102
    assert PasswordValidator.get_strength_score("aaaaaaa") < PasswordValidator.get_strength_score("aA1!xY9#qWz")
    assert PasswordValidator.get_strength_label(10) == ("ضعيف جداً", "danger")  # 114-115
    assert PasswordValidator.get_strength_label(40) == ("ضعيف", "warning")  # 116-117
    assert PasswordValidator.get_strength_label(60) == ("متوسط", "info")  # 118-119
    assert PasswordValidator.get_strength_label(80) == ("قوي", "primary")  # 120-121
    assert PasswordValidator.get_strength_label(95) == ("قوي جداً", "success")  # 123
    assert PasswordValidator.generate_suggestion()  # 126-147 loop-until-valid


def test_helper_messages():
    ok, msg = validate_password_with_helpful_message("Str0ng!Passw0rdX")  # 150-162
    assert ok is True and "✅" in msg
    ok2, msg2 = validate_password_with_helpful_message("weak")  # 163-170
    assert ok2 is False and "💡" in msg2


def test_system_init_bootstrap(app):
    import utils.system_init as si

    with (
        patch.object(si.db, "create_all", return_value=None),
        patch.object(si, "_ensure_permissions", return_value=None),
        patch.object(si, "_ensure_owner_role", return_value=MagicMock()),
        patch.object(si, "_ensure_owner_user", return_value=(MagicMock(), True)),
        patch.object(si, "_record_server_activation", return_value=None),
        patch.object(si, "_ensure_super_admin_role", return_value=None),
        patch.object(si, "_ensure_developer_role", return_value=None),
        patch.object(si, "_ensure_functional_roles", return_value=None),
        patch.object(si, "_ensure_platform_reference_data", return_value=None),
    ):
        si.ensure_clean_platform(app)  # 12-27
    with (
        patch.object(si.db, "create_all", return_value=None),
        patch.object(si, "_ensure_permissions", return_value=None),
        patch.object(si, "_ensure_owner_role", return_value=MagicMock()),
        patch.object(si, "_ensure_owner_user", return_value=(MagicMock(), False)),
        patch.object(si, "_record_server_activation", return_value=None),
        patch.object(si, "_ensure_super_admin_role", return_value=None),
        patch.object(si, "_ensure_developer_role", return_value=None),
        patch.object(si, "_ensure_functional_roles", return_value=None),
        patch.object(si, "_ensure_core_data", return_value=None),
        patch.object(si, "_ensure_tenant_gl_trees", side_effect=RuntimeError("gl down")),
    ):
        si.ensure_system_integrity(app)  # 30-92 incl GL exception branch 80-92
