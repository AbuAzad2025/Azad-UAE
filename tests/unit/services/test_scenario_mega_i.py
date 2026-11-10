"""Scenario mega-grid I — 10,000+ conversion cases (pure function).

Amounts x rates cartesian. Every expectation: amount * rate, HALF_UP 3dp.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

import pytest

from utils.currency_utils import convert_and_quantize_aed

AMOUNTS = [
    str(v)
    for v in list(range(1, 101))
    + [
        111,
        333,
        777,
        1111,
        3333,
        7777,
        9999,
        12345,
        54321,
        99999,
        100001,
        123456,
        500000,
        999999,
        1000000,
        2500000,
        9999999,
        10000000,
        12345678,
        99999999,
        100000000,
        77777777,
        31337,
        27182,
        16180,
        14142,
        17320,
        9999,
        8888,
        6666,
        4444,
        2222,
        1111,
        1000,
        500,
        250,
        100,
        50,
        25,
        10,
        5,
        2,
        1,
    ]
]
RATES = [
    str(v)
    for v in (
        "0.0027",
        "0.0037",
        "0.036",
        "0.08",
        "0.10",
        "0.22",
        "0.25",
        "0.27",
        "0.5",
        "0.75",
        "0.9",
        "0.95",
        "0.98",
        "0.99",
        "1",
        "1.02",
        "1.05",
        "1.5",
        "2",
        "2.5",
        "3",
        "3.65",
        "3.6725",
        "3.75",
        "3.98",
        "4",
        "4.05",
        "4.5",
        "4.65",
        "5",
        "5.25",
        "5.5",
        "6",
        "6.25",
        "7",
        "7.75",
        "8.5",
        "9.99",
        "10",
        "11.95",
        "12.5",
        "0.1234",
        "1.2345",
        "3.14159",
        "2.71828",
        "0.7071",
        "1.4142",
        "6.022",
        "9.8",
        "2.2046",
        "0.4536",
        "3.7854",
        "0.2642",
        "0.6214",
        "1.6093",
        "0.3048",
        "0.9144",
        "2.54",
        "100",
        "1000",
        "0.001",
        "0.0001",
        "123.456",
        "987.654",
        "555.555",
        "333.333",
        "77.777",
        "9.999",
        "0.999",
        "0.111",
        "0.333",
        "0.777",
        "1.111",
        "2.222",
        "3.333",
        "4.444",
        "5.555",
        "6.666",
        "7.777",
        "8.888",
        "9.999",
    )
]


class TestConversionTensOfThousands:
    @pytest.mark.parametrize("amount,rate", [(a, r) for a in AMOUNTS for r in RATES])
    def test_grid(self, amount, rate):
        assert convert_and_quantize_aed(Decimal(amount), "USD", Decimal(rate), base_currency="AED") == (
            Decimal(amount) * Decimal(rate)
        ).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
