from __future__ import annotations

from unittest.mock import MagicMock, patch

from utils.database_optimizer import DatabaseOptimizer


class TestVacuumPostgres:
    def test_vacuums_postgresql_database(self):
        conn = MagicMock()
        ctx = MagicMock()
        ctx.__enter__ = MagicMock(return_value=conn)
        ctx.__exit__ = MagicMock(return_value=False)
        engine = MagicMock()
        engine.url = 'postgresql://localhost/test'
        engine.connect.return_value = ctx
        conn.execution_options.return_value = conn

        mock_db = MagicMock()
        mock_db.engine = engine

        with patch('utils.database_optimizer.db', mock_db), patch(
            'utils.database_optimizer.logger'
        ) as logger:
            result = DatabaseOptimizer.vacuum_postgres()

        assert result == {'success': True, 'message': 'Database optimized'}
        conn.exec_driver_sql.assert_called_once_with('VACUUM (ANALYZE)')
        logger.info.assert_called_once()

    def test_vacuum_failure_returns_error(self):
        engine = MagicMock()
        engine.url = 'postgresql://localhost/test'
        engine.connect.side_effect = RuntimeError('vacuum failed')

        mock_db = MagicMock()
        mock_db.engine = engine
        with patch('utils.database_optimizer.db', mock_db), patch(
            'utils.database_optimizer.logger'
        ):
            result = DatabaseOptimizer.vacuum_postgres()

        assert result['success'] is False
        assert 'vacuum failed' in result['error']

    def test_vacuum_rejects_non_postgresql(self):
        engine = MagicMock()
        engine.url = 'sqlite:///tmp.db'
        mock_db = MagicMock()
        mock_db.engine = engine
        with patch('utils.database_optimizer.db', mock_db):
            result = DatabaseOptimizer.vacuum_postgres()
        assert result == {'success': False, 'message': 'Only PostgreSQL supported'}


class TestAnalyzeTables:
    def test_analyzes_postgresql_tables(self):
        session = MagicMock()
        engine = MagicMock()
        engine.url = 'postgresql://localhost/test'
        mock_db = MagicMock()
        mock_db.session = session
        mock_db.engine = engine
        with patch('utils.database_optimizer.db', mock_db), patch(
            'utils.database_optimizer.logger'
        ) as logger:
            result = DatabaseOptimizer.analyze_tables()
        assert result == {'success': True}
        session.execute.assert_called_once()
        session.commit.assert_called_once()
        logger.info.assert_called_once()

    def test_analyze_skips_sql_for_non_postgresql(self):
        session = MagicMock()
        engine = MagicMock()
        engine.url = 'sqlite:///tmp.db'
        mock_db = MagicMock()
        mock_db.session = session
        mock_db.engine = engine
        with patch('utils.database_optimizer.db', mock_db), patch(
            'utils.database_optimizer.logger'
        ):
            result = DatabaseOptimizer.analyze_tables()
        assert result == {'success': True}
        session.execute.assert_not_called()

    def test_analyze_failure_returns_error(self):
        session = MagicMock()
        session.execute.side_effect = RuntimeError('analyze failed')
        engine = MagicMock()
        engine.url = 'postgresql://localhost/test'
        mock_db = MagicMock()
        mock_db.session = session
        mock_db.engine = engine
        with patch('utils.database_optimizer.db', mock_db), patch(
            'utils.database_optimizer.logger'
        ):
            result = DatabaseOptimizer.analyze_tables()
        assert result['success'] is False


class TestGetTableSizes:
    def test_returns_postgresql_table_estimates(self):
        rows = [('products', 120), ('users', None)]
        result_proxy = MagicMock()
        result_proxy.__iter__ = MagicMock(return_value=iter(rows))
        session = MagicMock()
        session.execute.return_value = result_proxy
        engine = MagicMock()
        engine.url = 'postgresql://localhost/test'

        mock_db = MagicMock()
        mock_db.session = session
        mock_db.engine = engine
        with patch('utils.database_optimizer.db', mock_db):
            result = DatabaseOptimizer.get_table_sizes()

        assert result['success'] is True
        assert result['tables'] == [
            {'table_name': 'products', 'row_count': 120},
            {'table_name': 'users', 'row_count': 0},
        ]

    def test_non_postgresql_returns_message(self):
        engine = MagicMock()
        engine.url = 'sqlite:///tmp.db'
        mock_db = MagicMock()
        mock_db.engine = engine
        with patch('utils.database_optimizer.db', mock_db):
            result = DatabaseOptimizer.get_table_sizes()
        assert result == {'success': False, 'message': 'Only PostgreSQL supported'}

    def test_query_failure_returns_error(self):
        session = MagicMock()
        session.execute.side_effect = RuntimeError('query failed')
        engine = MagicMock()
        engine.url = 'postgresql://localhost/test'
        mock_db = MagicMock()
        mock_db.session = session
        mock_db.engine = engine
        with patch('utils.database_optimizer.db', mock_db):
            result = DatabaseOptimizer.get_table_sizes()
        assert result['success'] is False


class TestOptimizeAll:
    def test_runs_all_optimization_steps(self):
        with patch.object(DatabaseOptimizer, 'vacuum_postgres', return_value={'success': True}), patch.object(
            DatabaseOptimizer, 'analyze_tables', return_value={'success': True}
        ), patch.object(DatabaseOptimizer, 'get_table_sizes', return_value={'success': True, 'tables': []}):
            result = DatabaseOptimizer.optimize_all()
        assert set(result) == {'vacuum', 'analyze', 'sizes'}
