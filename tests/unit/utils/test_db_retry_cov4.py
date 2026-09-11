"""Cov4: db_retry uncovered arcs — delay cap, DBAPI sqlstate, custom exceptions."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.exc import DBAPIError, OperationalError

from utils.db_retry import _is_serialization_error, _retry_callable, retry_call


def _orig(pgcode=None, sqlstate=None):
    m = MagicMock()
    m.pgcode = pgcode
    m.sqlstate = sqlstate
    return m


def test_operational_orig_none_message_fallback():
    exc = OperationalError("stmt", None, _orig(pgcode=None, sqlstate=None))
    assert _is_serialization_error(exc) is False  # lines 28-33 fallthrough
    exc2 = OperationalError("40001 oops", None, _orig(pgcode=None, sqlstate=None))
    assert _is_serialization_error(exc2) is True  # line 41-42


def test_dbapi_sqlstate_branch():
    exc = DBAPIError("s", None, _orig(pgcode=None, sqlstate="40001"))
    assert _is_serialization_error(exc) is True  # lines 34-39


def test_dbapi_orig_none():
    exc = DBAPIError("plain", None, None)
    assert _is_serialization_error(exc) is False


def test_delay_capped_at_max_delay():
    calls = {"n": 0}
    err = OperationalError("x", None, _orig(pgcode="40001"))

    def _fn():
        calls["n"] += 1
        if calls["n"] < 3:
            raise err
        return "ok"

    with patch("utils.db_retry.time.sleep") as slp:
        out = _retry_callable(_fn, max_retries=3, base_delay=10.0, max_delay=2.0)
    assert out == "ok"  # line 64 cap branch
    assert slp.call_count == 2


def test_non_serialization_reraises_immediately():
    err = OperationalError("dead", None, _orig(pgcode="40P01"))

    def _fn():
        raise err

    with pytest.raises(OperationalError):  # line 62-63 not-serialization arc
        _retry_callable(_fn, max_retries=5, base_delay=0.001)


def test_exhaust_reraises_last():
    err = OperationalError("x", None, _orig(pgcode="40001"))

    def _fn():
        raise err

    with patch("utils.db_retry.time.sleep"), pytest.raises(OperationalError):  # 62 attempt>=max arc
        _retry_callable(_fn, max_retries=1, base_delay=0.001)


def test_custom_exceptions_tuple_string_match():
    def _fn():
        raise RuntimeError("pg 40001 deadlock")

    with patch("utils.db_retry.time.sleep"):
        with pytest.raises(RuntimeError):
            retry_call(_fn, max_retries=0, exceptions=(RuntimeError,))  # attempt>=max arc
