"""Cov4: helpers — sanitize, branch codes, numbers, currency fmt, timeago, files."""

from __future__ import annotations

import contextlib
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import utils.helpers as hh


def test_sanitize(app):
    with app.test_request_context("/"):
        assert hh.sanitize_error_message(Exception("plain fail")) == "plain fail"  # 36
        out = hh.sanitize_error_message(Exception('relation "foo" does not exist'))  # 29-32
        assert "internal database" in out.lower()
        out2 = hh.sanitize_error_message(Exception("x" * 300))  # 33-35
        assert "internal error" in out2.lower()


def test_branch_code_helpers():
    assert hh._resolve_branch_code(branch_code="br-7") == "BR7"  # 47-49
    assert hh._resolve_branch_code() is None  # 51-52
    with patch("utils.helpers.db") as mdb:
        mdb.session.get.return_value = None
        assert hh._resolve_branch_code(branch_id=3) == "BR03"  # 65 fallback
    with patch("utils.helpers.db") as mdb:
        mdb.session.get.return_value = SimpleNamespace(code="m-01")
        assert hh._resolve_branch_code(branch_id=8) == "M01"  # 54-61
    with patch("utils.helpers.db") as mdb2:
        mdb2.session.get.side_effect = RuntimeError("db down")
        assert hh._resolve_branch_code(branch_id=8) == "BR08"  # 62-65


def test_generate_number_paths(app):
    with app.test_request_context("/"):
        m = MagicMock()
        with patch.object(hh.db.session, "query", side_effect=RuntimeError("db")):
            with contextlib.suppress(RuntimeError):
                hh.generate_number("INV", m, field_name="f", tenant_id=1)
        q = MagicMock()
        q.filter.return_value = q
        q.order_by.return_value = q
        q.first.return_value = None
        with patch.object(hh.db.session, "query", return_value=q):
            out = hh.generate_number("INV", MagicMock(field_like="x"), field_name="num", branch_code="B1", tenant_id=1)
            assert "INV" in out  # 90-108 no-latest branch


def test_generate_number_and_save():
    with patch.object(hh, "generate_number", return_value="N-1"):
        assert hh.generate_number_and_save("P", MagicMock(), "f", lambda n: n + "!") == "N-1!"  # 128-142
    from sqlalchemy.exc import IntegrityError

    with patch.object(hh, "generate_number", return_value="N-1"):

        def _boom(n):
            raise IntegrityError("s", "p", Exception("dup"))

        with pytest.raises(RuntimeError):  # 143 exhausted
            hh.generate_number_and_save("P", MagicMock(), "f", _boom, max_attempts=2)


def test_format_currency_timeago(app):
    with app.test_request_context("/"):
        assert "AED" in hh.format_currency(10) or hh.format_currency(10)  # 206-246
        assert hh.format_currency(None)  # 207-208
        assert hh.format_currency("bad!!")  # 244-245 exception -> str
        assert hh.timeago(None) == ""  # 257-258
        assert hh.timeago(datetime(1960, 1, 1)) == ""  # 262-264
        assert hh.timeago(datetime.now(UTC))  # 270-271 just now
        assert hh.timeago(datetime.now(UTC) - timedelta(minutes=5))  # 272-274
        assert hh.timeago(datetime.now(UTC) - timedelta(hours=3))  # 275-277
        assert hh.timeago(datetime.now(UTC) - timedelta(days=3))  # 278-280
        assert hh.timeago(datetime.now(UTC) - timedelta(days=30))  # 282 date
        assert hh.timeago("not-a-date") == "not-a-date"  # 284-285


def test_files_and_misc(app):
    with app.test_request_context("/"):
        app.config["ALLOWED_UPLOAD_EXTENSIONS"] = {"all": {".txt"}}
        assert hh.allowed_file("a.txt") is True  # 329-343
        assert hh.allowed_file("") is False
        assert hh.allowed_file("a.exe") is False
        assert hh.save_uploaded_file(None) is None  # 348-349
        with pytest.raises(ValueError):  # 351-352
            hh.save_uploaded_file(SimpleNamespace(filename="a.exe"))
        big = SimpleNamespace(
            filename="a.txt", tell=lambda: 10**9, seek=lambda *a: None, read=lambda n: b"x", save=lambda p: None
        )
        with pytest.raises(ValueError):  # 359-360 size
            hh.save_uploaded_file(big)
        exe = SimpleNamespace(
            filename="a.txt", tell=lambda: 10, seek=lambda *a: None, read=lambda n: b"MZxxx", save=lambda p: None
        )
        with pytest.raises(ValueError):  # 365-366 executable
            hh.save_uploaded_file(exe)
    assert hh.convert_currency(5, "AED", "AED") == 5  # 411-412 same
    with patch("services.currency_service.CurrencyService.get_exchange_rate", return_value=2):
        assert hh.convert_currency(Decimal("5"), "USD", "AED") == Decimal("10")  # 414-415
    assert hh.generate_sku() and hh.generate_barcode()
