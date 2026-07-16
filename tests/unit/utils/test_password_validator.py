from __future__ import annotations

from unittest.mock import patch

from utils.password_validator import PasswordValidator, validate_password_with_helpful_message


class TestPasswordValidator:
    def test_validate_empty(self):
        ok, errs = PasswordValidator.validate('')
        assert ok is False
        assert 'مطلوبة' in errs[0]

    def test_validate_weak_short(self):
        ok, errs = PasswordValidator.validate('abc')
        assert ok is False
        assert any('10' in e for e in errs)

    def test_validate_common_password(self):
        ok, errs = PasswordValidator.validate('password123')
        assert ok is False
        assert any('شائعة' in e for e in errs)

    def test_validate_sequence_password(self):
        ok, errs = PasswordValidator.validate('Abc123!qwerty')
        assert ok is False
        assert any('تسلسل' in e for e in errs)

    def test_validate_strong_password(self):
        ok, errs = PasswordValidator.validate('Str0ng!Pass99')
        assert ok is True
        assert errs == []

    def test_missing_upper_lower_digit_special(self):
        ok, _ = PasswordValidator.validate('alllower12!')
        assert ok is False
        ok, _ = PasswordValidator.validate('ALLUPPER12!')
        assert ok is False
        ok, _ = PasswordValidator.validate('NoDigits!!aa')
        assert ok is False
        ok, _ = PasswordValidator.validate('NoSpecial99a')
        assert ok is False

    def test_strength_score_empty(self):
        assert PasswordValidator.get_strength_score('') == 0

    def test_strength_score_and_labels(self):
        score = PasswordValidator.get_strength_score('Str0ng!Pass99')
        assert 0 < score <= 100
        assert PasswordValidator.get_strength_label(10)[1] == 'danger'
        assert PasswordValidator.get_strength_label(40)[1] == 'warning'
        assert PasswordValidator.get_strength_label(60)[1] == 'info'
        assert PasswordValidator.get_strength_label(80)[1] == 'primary'
        assert PasswordValidator.get_strength_label(95)[1] == 'success'

    def test_strength_score_repeated_chars_penalty(self):
        low = PasswordValidator.get_strength_score('aaaaaaaaaa1!')
        high = PasswordValidator.get_strength_score('Str0ng!Pass99')
        assert high > low

    def test_generate_suggestion(self):
        pwd = PasswordValidator.generate_suggestion()
        ok, _ = PasswordValidator.validate(pwd)
        assert ok is True
        assert len(pwd) >= 12

    def test_validate_with_helpful_message_success(self):
        ok, msg = validate_password_with_helpful_message('Str0ng!Pass99')
        assert ok is True
        assert '✅' in msg

    def test_validate_with_helpful_message_failure(self):
        with patch.object(PasswordValidator, 'generate_suggestion', return_value='Str0ng!Pass99'):
            ok, msg = validate_password_with_helpful_message('weak')
        assert ok is False
        assert '⚠️' in msg
        assert 'اقتراح' in msg
