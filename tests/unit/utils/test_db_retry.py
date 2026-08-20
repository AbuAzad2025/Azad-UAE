"""Tests for utils.db_retry."""

from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.exc import OperationalError

from utils.db_retry import retry_call, retry_on_serialization_error


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
