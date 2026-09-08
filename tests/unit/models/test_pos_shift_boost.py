"""Boost pos_shift model coverage."""

from models.pos_shift import PosShift


def test_pos_shift_import_and_class():
    assert PosShift is not None
    assert hasattr(PosShift, "__table__")
