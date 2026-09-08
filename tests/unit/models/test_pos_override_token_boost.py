"""Boost pos_override_token model coverage."""

from models.pos_override_token import PosOverrideToken


def test_pos_override_token_import():
    assert PosOverrideToken is not None
    assert hasattr(PosOverrideToken, "__table__")
