import pytest

from utils.exceptions import SecurityBoundaryViolation


class TestSecurityBoundaryViolation:
    def test_default_message(self):
        err = SecurityBoundaryViolation()
        assert str(err) == "Cross-tenant security boundary violated"

    def test_custom_message(self):
        err = SecurityBoundaryViolation("tenant mismatch")
        assert str(err) == "tenant mismatch"

    def test_is_exception(self):
        with pytest.raises(SecurityBoundaryViolation):
            raise SecurityBoundaryViolation()
