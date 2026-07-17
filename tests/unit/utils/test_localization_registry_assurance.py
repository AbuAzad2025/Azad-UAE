from __future__ import annotations

import pytest

from utils.localization.null import NullStrategy
from utils.localization.palestine import PalestineStrategy
from utils.localization.uae import UAEStrategy
from utils.localization.ksa import KSAStrategy
from utils.localization.registry import get_strategy, list_supported_countries


class TestLocalizationRegistry:
    @pytest.mark.parametrize(
        "code,expected_cls",
        [
            ("PS", PalestineStrategy),
            ("AE", UAEStrategy),
            ("SA", KSAStrategy),
            ("ps", PalestineStrategy),
            (" ae ", UAEStrategy),
        ],
    )
    def test_get_strategy_known_countries(self, code, expected_cls):
        strategy = get_strategy(code)
        assert isinstance(strategy, expected_cls)

    def test_get_strategy_unknown_returns_null(self):
        strategy = get_strategy("US")
        assert isinstance(strategy, NullStrategy)

    def test_get_strategy_empty_returns_null(self):
        strategy = get_strategy("")
        assert isinstance(strategy, NullStrategy)

    def test_get_strategy_none_returns_null(self):
        strategy = get_strategy(None)
        assert isinstance(strategy, NullStrategy)

    def test_list_supported_countries(self):
        countries = list_supported_countries()
        assert set(countries) == {"PS", "AE", "SA"}
