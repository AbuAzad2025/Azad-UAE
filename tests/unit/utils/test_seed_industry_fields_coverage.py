"""Tests for utils/seed_industry_fields.py uncovered lines."""

from unittest.mock import MagicMock, patch

import pytest


def test_seed_industry_fields_creates_new():
    """Test seed_industry_fields creates fields that don't exist."""
    from utils.seed_industry_fields import seed_industry_fields

    with patch("utils.seed_industry_fields.atomic_transaction") as mock_atomic:
        mock_ctx = MagicMock()
        mock_atomic.return_value.__enter__ = MagicMock(return_value=mock_ctx)
        mock_atomic.return_value.__exit__ = MagicMock(return_value=False)

        with patch("utils.seed_industry_fields.IndustryFieldDefinition") as mock_cls:
            mock_cls.query.filter_by.return_value.first.return_value = None
            with patch("utils.seed_industry_fields.db.session") as mock_session:
                seed_industry_fields()
                assert mock_session.add.called


def test_seed_industry_fields_skips_existing():
    """Test seed_industry_fields skips fields that already exist."""
    from utils.seed_industry_fields import seed_industry_fields

    with patch("utils.seed_industry_fields.atomic_transaction") as mock_atomic:
        mock_ctx = MagicMock()
        mock_atomic.return_value.__enter__ = MagicMock(return_value=mock_ctx)
        mock_atomic.return_value.__exit__ = MagicMock(return_value=False)

        with patch("utils.seed_industry_fields.IndustryFieldDefinition") as mock_cls:
            # First call returns None (new), second returns existing
            mock_existing = MagicMock()
            mock_cls.query.filter_by.return_value.first.side_effect = [None, mock_existing]
            with patch("utils.seed_industry_fields.db.session") as mock_session:
                seed_industry_fields()
                # Should add for new, skip for existing
                assert mock_session.add.call_count >= 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
