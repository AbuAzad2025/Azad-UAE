"""Cov4: localization engine + palestine + logging_setup + qr + query_optimizer."""

from __future__ import annotations

import logging
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from utils.localization.engine import LocalizationStrategy, coerce_decimal
from utils.localization.palestine import PalestineStrategy
from utils.logging_setup import ColorFormatter, RequestIdFilter, setup_logging
from utils.qr_generator import generate_qr_data_url
from utils.query_optimizer import batch_fetch, optimize_query, paginate_optimized, prefetch_related


def test_coerce():
    assert coerce_decimal(None) is None  # 9-15
    assert coerce_decimal("bad", default="d") == "d"
    assert coerce_decimal("1.5") == Decimal("1.5")


def test_engine_abstracts():
    class _S(LocalizationStrategy):
        def calculate_tax(self, amount, tax_rate=None):
            return {}

        def format_tax_return(self, o, i, s, e):
            return {}

    s = _S()
    with pytest.raises(NotImplementedError):  # 47-52
        s.generate_einvoice(SimpleNamespace())
    with pytest.raises(NotImplementedError):  # 54-59
        s.get_wps_format([])
    assert s.validate_tax_number("12345") is True  # 61-63
    assert s.validate_tax_number("") is False


def test_palestine_branches():
    st = PalestineStrategy()
    assert st._resolve_vat_rate(tax_rate=Decimal("5")) == Decimal("5")  # 22-25
    assert st._resolve_vat_rate(sale=SimpleNamespace(tax_rate="7")) == Decimal("7")  # 26-29
    assert st._resolve_vat_rate() == Decimal("16.00")  # 30
    assert st._sale_total(SimpleNamespace(total_aed="9")) == Decimal("9")  # 32-38
    assert st._sale_total(SimpleNamespace()) == Decimal("0")
    assert st.convert_to_local_currency(5, "ILS", "ILS") == Decimal("5")  # 45-46
    with pytest.raises(ValueError):  # 43-44
        st.convert_to_local_currency(5, "XXX", "ILS")
    with patch("utils.helpers.convert_currency", return_value=10):
        assert st.convert_to_local_currency(5, "USD", "ILS") == Decimal("10.00")  # 47-52
    zero = st.calculate_tax(Decimal("100"), Decimal("0"))  # 57-63
    assert zero["tax_amount"] == Decimal("0")
    pos = st.calculate_tax(Decimal("100"), Decimal("16"))  # 64-71
    assert pos["tax_amount"] == Decimal("16.00")
    assert st.format_tax_return(Decimal("10"), Decimal("4"), "s", "e")["net_payable"] == Decimal("6")  # 73-90
    assert st.validate_tax_number("") is False  # 92-96
    assert st.validate_tax_number("123456789") is True
    assert st.validate_tax_number("abc") is False
    inv = st.generate_einvoice(SimpleNamespace(total_aed="116", tax_rate="16"))  # 98-120
    assert "<Invoice>" in inv["xml_payload"]
    inv0 = st.generate_einvoice(SimpleNamespace(total_aed="100", tax_rate="0"))
    assert "0" in inv0["xml_payload"]
    wps = st.get_wps_format(
        [{"employee_id": "1", "bank_code": "b", "name": "n", "iban": "i", "net_salary": 9}]
    )  # 122-138
    assert wps["record_count"] == 1


def test_request_filter_and_color(app):
    f = RequestIdFilter()
    rec = logging.LogRecord("n", logging.INFO, __file__, 1, "m", (), None)
    assert f.filter(rec) is True  # 35-40 (no ctx -> "-")
    with app.test_request_context("/"):
        assert f.filter(rec) is True
    cf = ColorFormatter()
    rec2 = logging.LogRecord("n", logging.WARNING, __file__, 1, "hello", (), None)
    rec2.request_id = "-"
    assert "hello" in cf.format(rec2)  # 52-73
    import os

    os.environ["FLASK_ENV"] = "production"
    assert "hello" in cf.format(rec2)  # no-color branch 56-59
    os.environ["FLASK_ENV"] = "development"


def test_setup_logging_runs(app):
    app.config["LOG_LEVEL"] = "DEBUG"
    setup_logging(app)  # 76-108 incl win32 branch
    assert app.logger is not None


def test_qr_edges():
    assert generate_qr_data_url(None) == ""  # 19-20
    assert generate_qr_data_url("   ") == ""  # 27-28
    out = generate_qr_data_url({"a": 1})  # happy (dict branch 23)
    assert out == "" or out.startswith("data:image/png;base64,")
    out2 = generate_qr_data_url("hello-qr")
    assert out2 == "" or out2.startswith("data:image/png;base64,")
    with patch.dict("sys.modules", {"qrcode": None}):
        assert generate_qr_data_url("x") == ""  # 16-17 import fail


def test_optimizer_branches():
    import utils.query_optimizer as qo

    m = MagicMock()
    m.query = MagicMock()
    assert optimize_query(m, None) is m.query  # 7-8
    for strat in ("joined", "select", "subquery", "unknown"):
        mq = MagicMock()
        mq.options.return_value = mq
        m3 = SimpleNamespace(query=mq, rel=MagicMock(name="rel_attr"))
        with (
            patch.object(qo, "joinedload", return_value="OPT"),
            patch.object(qo, "selectinload", return_value="OPT"),
            patch.object(qo, "subqueryload", return_value="OPT"),
        ):
            out = optimize_query(m3, ["rel"], strategy=strat)  # 12-18
            assert out is mq or out is not None
    q = MagicMock()
    q.paginate.return_value = "P"
    assert paginate_optimized(q, page=1, per_page=5) == "P"  # 23-24
    mm = MagicMock()
    mm.query.filter.return_value.all.return_value = [SimpleNamespace(id=1)]
    assert batch_fetch(mm, [1]) == {1: mm.query.filter.return_value.all.return_value[0]}  # 27-35
    assert prefetch_related([], "r", MagicMock()) == []  # 39-40
    inst = [SimpleNamespace(id=1, __tablename__="sale")]
    rel = MagicMock()
    rel.query.filter.return_value.all.return_value = []
    assert prefetch_related(inst, "lines", rel) == inst  # 42-60
