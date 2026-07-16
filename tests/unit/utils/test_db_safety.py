from unittest.mock import patch

import pytest

from utils.db_safety import atomic_transaction, safe_commit


class TestAtomicTransaction:
    def test_commits_on_success(self):
        with patch('utils.db_safety.db') as mock_db:
            with atomic_transaction('sale_creation'):
                pass
            mock_db.session.commit.assert_called_once()
            mock_db.session.rollback.assert_not_called()

    def test_rolls_back_and_reraises_on_error(self):
        with patch('utils.db_safety.db') as mock_db:
            with pytest.raises(RuntimeError, match='boom'):
                with atomic_transaction('fail_op'):
                    raise RuntimeError('boom')
            mock_db.session.rollback.assert_called_once()
            mock_db.session.commit.assert_not_called()


class TestSafeCommit:
    def test_returns_true_on_success(self):
        with patch('utils.db_safety.db') as mock_db:
            assert safe_commit('ok') is True
            mock_db.session.commit.assert_called_once()

    def test_returns_false_on_failure(self):
        with patch('utils.db_safety.db') as mock_db:
            mock_db.session.commit.side_effect = Exception('db down')
            assert safe_commit('bad') is False
            mock_db.session.rollback.assert_called_once()
