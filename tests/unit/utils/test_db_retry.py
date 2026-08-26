"""Tests for utils.db_retry."""

from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.exc import DBAPIError, OperationalError

from utils.db_retry import _is_serialization_error, retry_call, retry_on_serialization_error


class TestRetryOnSerializationError:
    def test_succeeds_without_error(self):
        call_count = 0

        @retry_on_serialization_error(max_retries=2)
        def fn():
            nonlocal call_count
            call_count += 1
            return "ok"

        assert fn() == "ok"
        assert call_count == 1

    def test_retries_on_40001_then_succeeds(self):
        call_count = 0
        err = OperationalError("serialization failure", None, None)
        err.orig = MagicMock(pgcode="40001")

        @retry_on_serialization_error(max_retries=3, base_delay=0.01)
        def fn():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise err
            return "ok"

        with patch("utils.db_retry.time.sleep"):
            assert fn() == "ok"
        assert call_count == 3

    def test_does_not_retry_non_serialization_error(self):
        call_count = 0

        @retry_on_serialization_error(max_retries=3)
        def fn():
            nonlocal call_count
            call_count += 1
            raise ValueError("boom")

        with pytest.raises(ValueError, match="boom"):
            fn()
        assert call_count == 1

    def test_raises_after_max_retries(self):
        call_count = 0
        err = OperationalError("serialization failure", None, None)
        err.orig = MagicMock(pgcode="40001")

        @retry_on_serialization_error(max_retries=2, base_delay=0.01)
        def fn():
            nonlocal call_count
            call_count += 1
            raise err

        with patch("utils.db_retry.time.sleep"):
            with pytest.raises(OperationalError):
                fn()
        assert call_count == 3  # initial + 2 retries


class TestRetryCall:
    def test_retry_call_succeeds_without_error(self):
        call_count = 0

        def fn():
            nonlocal call_count
            call_count += 1
            return "ok"

        assert retry_call(fn) == "ok"
        assert call_count == 1

    def test_retry_call_retries_on_40001_then_succeeds(self):
        call_count = 0
        err = OperationalError("serialization failure", None, None)
        err.orig = MagicMock(pgcode="40001")

        def fn():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise err
            return "ok"

        with patch("utils.db_retry.time.sleep"):
            assert retry_call(fn, max_retries=3, base_delay=0.01) == "ok"
        assert call_count == 3

    def test_retry_call_does_not_retry_non_serialization_error(self):
        call_count = 0

        def fn():
            nonlocal call_count
            call_count += 1
            raise ValueError("boom")

        with pytest.raises(ValueError, match="boom"):
            retry_call(fn, max_retries=3)
        assert call_count == 1

    def test_retry_call_passes_args_and_kwargs(self):
        def fn(a, b, c=None):
            return (a, b, c)

        assert retry_call(fn, 1, 2, c=3) == (1, 2, 3)


class TestIsSerializationErrorBranches:
    @staticmethod
    def _orig(pgcode=None, sqlstate=None):
        orig = MagicMock()
        orig.pgcode = pgcode
        orig.sqlstate = sqlstate
        return orig

    def test_dbapierror_with_40001_pgcode_is_retried(self):
        calls = 0
        err = DBAPIError("select 1", None, self._orig(pgcode="40001"))

        def fn():
            nonlocal calls
            calls += 1
            if calls == 1:
                raise err
            return "ok"

        with patch("utils.db_retry.time.sleep"):
            assert retry_call(fn, max_retries=2, base_delay=0.01) == "ok"
        assert calls == 2

    def test_sqlstate_attribute_fallback_is_detected(self):
        """Drivers exposing `sqlstate` instead of `pgcode` must still be retried."""
        calls = 0
        err = OperationalError("select 1", None, self._orig(sqlstate="40001"))

        def fn():
            nonlocal calls
            calls += 1
            if calls == 1:
                raise err
            return "recovered"

        with patch("utils.db_retry.time.sleep"):
            assert retry_call(fn, max_retries=2, base_delay=0.01) == "recovered"
        assert calls == 2

    def test_sqlstate_in_message_string_is_retried(self):
        """Fallback detection: the SQLSTATE literal in the message text."""
        attempts = []

        def fn():
            attempts.append(1)
            if len(attempts) == 1:
                raise ValueError("could not serialize access due to 40001")
            return "second try"

        with patch("utils.db_retry.time.sleep"):
            assert retry_call(fn, exceptions=(ValueError,), max_retries=2, base_delay=0.01) == "second try"
        assert len(attempts) == 2

    def test_different_pgcode_is_not_retried(self):
        calls = 0
        err = OperationalError("deadlock", None, self._orig(pgcode="40P01"))

        def fn():
            nonlocal calls
            calls += 1
            raise err

        with pytest.raises(OperationalError):
            retry_call(fn, max_retries=3)
        assert calls == 1

    def test_predicate_false_for_plain_exception(self):
        assert _is_serialization_error(ValueError("boom")) is False

    def test_predicate_true_for_message_literal(self):
        assert _is_serialization_error(ValueError("SQLSTATE 40001 triggered")) is True

    def test_predicate_handles_missing_orig(self):
        exc = OperationalError("connection lost", None, None)
        assert _is_serialization_error(exc) is False
