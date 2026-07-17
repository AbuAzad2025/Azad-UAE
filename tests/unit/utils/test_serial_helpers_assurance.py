"""Serial helpers — extract and validate serial numbers on purchase/return lines."""

from __future__ import annotations

import pytest

from utils.serial_helpers import extract_serials, validate_serials


class TestExtractSerials:
    def test_empty_line_data(self):
        assert extract_serials({}) == []

    def test_list_serials_stripped(self):
        assert extract_serials({"serials": [" SN-1 ", "", "SN-2"]}) == ["SN-1", "SN-2"]

    def test_string_serials_split_on_newlines_and_commas(self):
        raw = "A-1\rB-2,C-3\nD-4"
        assert extract_serials({"serials": raw}) == ["A-1", "B-2", "C-3", "D-4"]


class TestValidateSerials:
    def test_count_mismatch_raises(self):
        with pytest.raises(ValueError, match="يتطلب 2 رقم تسلسلي"):
            validate_serials(["SN-1"], "Widget", 2)

    def test_duplicate_serials_raises(self):
        with pytest.raises(ValueError, match="مكررة"):
            validate_serials(["SN-1", "SN-1"], "Widget", 2)

    def test_valid_serials_pass(self):
        validate_serials(["SN-1", "SN-2"], "Widget", 2)
