from __future__ import annotations

import json
import os
import tarfile
from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest

from services.backup_scope_config import SCOPE_BRANCH, SCOPE_STORE, SCOPE_TENANT
from services.backup_scoped_restore import (
    REMAP_CONFIRM,
    RESTORE_CONFIRM,
    _apply_row_remap,
    _build_id_remap,
    _delete_tenant_scoped_data,
    _required_confirmation,
    _table_has_column,
    extract_scoped_bundle,
    import_scoped_tables,
    restore_scoped_backup,
    verify_scoped_restore,
)


class TestRequiredConfirmation:
    def test_restore_confirm(self):
        assert _required_confirmation(False) == RESTORE_CONFIRM

    def test_remap_confirm(self):
        assert _required_confirmation(True) == REMAP_CONFIRM


class TestBuildIdRemapExtended:
    def test_skips_rows_without_id(self):
        tables = {'products': [{'name': 'no-id'}, {'id': 10, 'tenant_id': 1}]}
        id_maps = _build_id_remap(tables, new_tenant_id=99)
        assert 10 in id_maps['products']

    def test_remaps_tenant_stores_when_new_store_id(self):
        tables = {
            'tenants': [{'id': 1}],
            'tenant_stores': [{'id': 7, 'tenant_id': 1, 'store_slug': 'shop'}],
        }
        id_maps = _build_id_remap(tables, new_tenant_id=50, new_store_id=700)
        assert id_maps['tenant_stores'][7] == 700

    def test_store_slug_remap_suffix(self):
        row = _apply_row_remap(
            {'id': 7, 'store_slug': 'myshop', 'tenant_id': 1},
            'tenant_stores',
            {'tenant_stores': {7: 800}},
            new_tenant_id=50,
            old_tenant_id=1,
            scope=SCOPE_TENANT,
            remap=True,
            new_store_id=800,
        )
        assert row['store_slug'].endswith('_r800')


class TestDeleteTenantScopedData:
    def test_deletes_tenant_and_branch_scoped_rows(self):
        conn = MagicMock()
        nested = MagicMock()
        conn.begin_nested.return_value.__enter__ = MagicMock(return_value=None)
        conn.begin_nested.return_value.__exit__ = MagicMock(return_value=False)

        def execute_side_effect(stmt, params=None):
            sql = str(stmt)
            result = MagicMock()
            if 'information_schema' in sql:
                if 'tenant_id' in sql or params and params.get('t') == 'sales':
                    result.__iter__ = lambda self: iter([('tenant_id',), ('branch_id',)])
                else:
                    result.__iter__ = lambda self: iter([('id',)])
            else:
                result.rowcount = 1
            return result

        conn.execute.side_effect = execute_side_effect

        with patch('services.backup_scope_config.table_exists', return_value=True):
            _delete_tenant_scoped_data(conn, tenant_id=5, branch_id=9)

        assert conn.execute.call_count >= 2

    def test_skips_missing_tables_and_logs_errors(self):
        conn = MagicMock()
        conn.begin_nested.return_value.__enter__ = MagicMock(return_value=None)
        conn.begin_nested.return_value.__exit__ = MagicMock(return_value=False)

        def execute_side_effect(stmt, params=None):
            sql = str(stmt)
            if 'information_schema' in sql:
                result = MagicMock()
                result.__iter__ = lambda self: iter([('tenant_id',)])
                return result
            raise RuntimeError('delete failed')

        conn.execute.side_effect = execute_side_effect

        with patch('services.backup_scope_config.table_exists', return_value=True):
            _delete_tenant_scoped_data(conn, tenant_id=1)


class TestImportScopedTablesExtended:
    def _mock_engine(self, mocker, conn=None):
        if conn is None:
            conn = MagicMock()
            conn.begin_nested.return_value.__enter__ = MagicMock(return_value=None)
            conn.begin_nested.return_value.__exit__ = MagicMock(return_value=False)
            conn.execute.return_value = MagicMock()
        engine = MagicMock()
        engine.begin.return_value.__enter__ = MagicMock(return_value=conn)
        engine.begin.return_value.__exit__ = MagicMock(return_value=False)
        mocker.patch('sqlalchemy.create_engine', return_value=engine)
        mocker.patch('services.backup_scoped_restore._delete_tenant_scoped_data')
        return conn

    def test_remap_skips_delete(self, mocker):
        self._mock_engine(mocker)
        tables = {
            'tenants': [{'id': 1, 'slug': 't'}],
            'roles': [{'id': 1, 'name': 'admin'}],
            'branches': [{'id': 2, 'tenant_id': 1}],
            'extra_table': [{'id': 99, 'tenant_id': 1}],
        }
        result = import_scoped_tables(
            'postgresql://localhost/target', tables,
            scope=SCOPE_TENANT, source_tenant_id=1,
            remap=True, target_tenant_id=50, new_branch_id=200, new_store_id=300,
        )
        assert result['ok'] is True
        assert 'extra_table' in result['inserted']

    def test_empty_table_rows_skipped(self, mocker):
        self._mock_engine(mocker)
        tables = {
            'tenants': [{'id': 1}],
            'roles': [{'id': 1}],
            'branches': [{'id': 2, 'tenant_id': 1}],
            'products': [],
        }
        result = import_scoped_tables(
            'postgresql://localhost/target', tables,
            scope=SCOPE_TENANT, source_tenant_id=1,
        )
        assert result['inserted'].get('products', 0) == 0

    def test_fatal_table_missing_marks_not_ok(self, mocker):
        conn = MagicMock()
        conn.begin_nested.return_value.__enter__ = MagicMock(return_value=None)
        conn.begin_nested.return_value.__exit__ = MagicMock(return_value=False)
        conn.execute.side_effect = RuntimeError('fail')
        self._mock_engine(mocker, conn)
        mocker.patch('services.backup_scoped_restore.normalize_row_to_target', side_effect=lambda c, t, r: r)
        tables = {
            'tenants': [{'id': 1}],
            'roles': [{'id': 1}],
            'branches': [{'id': 2, 'tenant_id': 1}],
        }
        result = import_scoped_tables(
            'postgresql://localhost/target', tables,
            scope=SCOPE_TENANT, source_tenant_id=1,
        )
        assert result['ok'] is False

    def test_partial_errors_still_ok_if_some_inserted(self, mocker):
        conn = MagicMock()
        conn.begin_nested.return_value.__enter__ = MagicMock(return_value=None)
        conn.begin_nested.return_value.__exit__ = MagicMock(return_value=False)
        call_n = {'n': 0}

        def execute_side_effect(*args, **kwargs):
            call_n['n'] += 1
            if call_n['n'] == 5:
                raise RuntimeError('row fail')
            return MagicMock()

        conn.execute.side_effect = execute_side_effect
        self._mock_engine(mocker, conn)
        mocker.patch('services.backup_scoped_restore.normalize_row_to_target', side_effect=lambda c, t, r: r)
        tables = {
            'tenants': [{'id': 1}],
            'roles': [{'id': 1}],
            'branches': [{'id': 2, 'tenant_id': 1}],
            'customers': [{'id': 3, 'tenant_id': 1}, {'id': 4, 'tenant_id': 1}],
        }
        result = import_scoped_tables(
            'postgresql://localhost/target', tables,
            scope=SCOPE_TENANT, source_tenant_id=1,
        )
        assert result['errors']
        assert result['ok'] is True


class TestVerifyScopedRestoreExtended:
    def _mock_conn_engine(self, mocker, scalar_values):
        conn = MagicMock()
        conn.begin_nested.return_value.__enter__ = MagicMock(return_value=None)
        conn.begin_nested.return_value.__exit__ = MagicMock(return_value=False)
        conn.execute.return_value.scalar.side_effect = scalar_values
        engine = MagicMock()
        engine.connect.return_value.__enter__ = MagicMock(return_value=conn)
        engine.connect.return_value.__exit__ = MagicMock(return_value=False)
        mocker.patch('sqlalchemy.create_engine', return_value=engine)
        return conn

    def test_skips_zero_expected_or_missing_table(self, mocker):
        self._mock_conn_engine(mocker, [0])
        mocker.patch('services.backup_scope_config.table_exists', side_effect=lambda c, t: t == 'tenants')
        mocker.patch('services.backup_scoped_restore._table_has_column', return_value=True)
        out = verify_scoped_restore(
            'postgresql://localhost/target',
            {'row_counts_per_table': {'tenants': 0, 'missing_tbl': 5}},
            expected_tenant_id=1, scope=SCOPE_TENANT,
        )
        assert out['ok'] is True

    def test_warning_on_non_core_shortfall(self, mocker):
        self._mock_conn_engine(mocker, [1, 0, 0])
        mocker.patch('services.backup_scope_config.table_exists', return_value=True)
        mocker.patch('services.backup_scoped_restore._table_has_column', return_value=True)
        out = verify_scoped_restore(
            'postgresql://localhost/target',
            {'row_counts_per_table': {'tenants': 1, 'warehouses': 10}},
            expected_tenant_id=1, scope=SCOPE_TENANT,
        )
        assert any('warehouses' in w for w in out['warnings'])

    def test_orphan_tenant_fk_on_sales(self, mocker):
        self._mock_conn_engine(mocker, [1, 3])
        mocker.patch('services.backup_scope_config.table_exists', return_value=True)
        mocker.patch('services.backup_scoped_restore._table_has_column', return_value=True)
        out = verify_scoped_restore(
            'postgresql://localhost/target',
            {'row_counts_per_table': {'tenants': 1}},
            expected_tenant_id=1, scope=SCOPE_TENANT,
        )
        assert out['ok'] is False
        assert any('orphan tenant FK' in e for e in out['errors'])

    def test_orphan_merchant_customer_on_products(self, mocker):
        conn = MagicMock()
        conn.begin_nested.return_value.__enter__ = MagicMock(return_value=None)
        conn.begin_nested.return_value.__exit__ = MagicMock(return_value=False)
        conn.execute.return_value.scalar.side_effect = [1, 0, 2]
        engine = MagicMock()
        engine.connect.return_value.__enter__ = MagicMock(return_value=conn)
        engine.connect.return_value.__exit__ = MagicMock(return_value=False)
        mocker.patch('sqlalchemy.create_engine', return_value=engine)
        mocker.patch('services.backup_scope_config.table_exists', return_value=True)
        mocker.patch('services.backup_scoped_restore._table_has_column', return_value=True)
        out = verify_scoped_restore(
            'postgresql://localhost/target',
            {'row_counts_per_table': {'tenants': 1}},
            expected_tenant_id=1, scope=SCOPE_TENANT,
        )
        assert any('merchant_customer_id' in e for e in out['errors'])

    def test_verify_count_exception_logged(self, mocker):
        conn = MagicMock()
        conn.begin_nested.return_value.__enter__ = MagicMock(return_value=None)
        conn.begin_nested.return_value.__exit__ = MagicMock(return_value=False)
        conn.execute.side_effect = RuntimeError('count fail')
        engine = MagicMock()
        engine.connect.return_value.__enter__ = MagicMock(return_value=conn)
        engine.connect.return_value.__exit__ = MagicMock(return_value=False)
        mocker.patch('sqlalchemy.create_engine', return_value=engine)
        mocker.patch('services.backup_scope_config.table_exists', return_value=True)
        out = verify_scoped_restore(
            'postgresql://localhost/target',
            {'row_counts_per_table': {'tenants': 1}},
            expected_tenant_id=1, scope=SCOPE_TENANT,
        )
        assert out['ok'] is True

    def test_table_has_column(self, mocker):
        conn = MagicMock()
        conn.execute.return_value.scalar.return_value = 1
        assert _table_has_column(conn, 'products', 'tenant_id') is True


class TestRestoreScopedBackupFlow:
    def _write_minimal_bundle(self, tmp_path, include_uploads=False):
        manifest = {
            'backup_scope': SCOPE_TENANT,
            'tenant_id': 7,
            'row_counts_per_table': {'tenants': 1, 'products': 1},
        }
        data_dir = tmp_path / 'data'
        data_dir.mkdir()
        (data_dir / 'schema_meta.json').write_text('{}', encoding='utf-8')
        (data_dir / 'tenants.jsonl').write_text(
            json.dumps({'id': 7, 'slug': 't7'}), encoding='utf-8',
        )
        (data_dir / 'products.jsonl').write_text(
            json.dumps({'id': 10, 'tenant_id': 7, 'name': 'P'}), encoding='utf-8',
        )
        archive = tmp_path / 'bundle.tar.gz'
        manifest_path = tmp_path / 'manifest.json'
        manifest_path.write_text(json.dumps(manifest), encoding='utf-8')
        uploads = None
        if include_uploads:
            uploads = tmp_path / 'uploads.tar.gz'
            with tarfile.open(uploads, 'w:gz') as utar:
                data = b'file-content'
                info = tarfile.TarInfo(name='tenant_7/logo.png')
                info.size = len(data)
                utar.addfile(info, BytesIO(data))
        with tarfile.open(archive, 'w:gz') as tar:
            tar.add(manifest_path, arcname='manifest.json')
            tar.add(data_dir, arcname='data')
            if uploads is not None:
                tar.add(uploads, arcname='uploads.tar.gz')
        return str(archive)

    def test_system_scope_rejected(self):
        mock_cls = MagicMock()
        mock_cls._urls_same_database.return_value = False
        mock_cls.verify_backup.return_value = {
            'valid': True,
            'manifest': {'backup_scope': 'system', 'tenant_id': 1},
        }
        result = restore_scoped_backup(
            mock_cls, 'sys.tar.gz', 'postgresql://localhost/newdb',
            confirmation=RESTORE_CONFIRM,
        )
        assert result['ok'] is False
        assert 'system scope' in result['errors'][0]

    def test_invalid_filename_rejected(self):
        mock_cls = MagicMock()
        mock_cls._urls_same_database.return_value = False
        mock_cls.verify_backup.return_value = {
            'valid': True,
            'manifest': {'backup_scope': SCOPE_TENANT, 'tenant_id': 1},
        }
        mock_cls._backup_path.return_value = None
        result = restore_scoped_backup(
            mock_cls, '../evil.tar.gz', 'postgresql://localhost/newdb',
            confirmation=RESTORE_CONFIRM,
        )
        assert 'invalid filename' in result['errors'][0]

    def test_schema_upgrade_failure(self, mocker, tmp_path):
        mock_cls = MagicMock()
        mock_cls._urls_same_database.return_value = False
        mock_cls.verify_backup.return_value = {
            'valid': True,
            'manifest': {'backup_scope': SCOPE_TENANT, 'tenant_id': 7},
        }
        archive = self._write_minimal_bundle(tmp_path)
        mock_cls._backup_path.return_value = archive
        mocker.patch(
            'services.backup_scoped_engine.ensure_target_schema',
            return_value=(False, 'migration failed'),
        )
        result = restore_scoped_backup(
            mock_cls, 'bundle.tar.gz', 'postgresql://localhost/newdb',
            confirmation=RESTORE_CONFIRM,
        )
        assert 'schema upgrade' in result['errors'][0]

    def test_successful_restore_with_uploads(self, mocker, tmp_path):
        mock_cls = MagicMock()
        mock_cls._urls_same_database.return_value = False
        mock_cls._BASEDIR = str(tmp_path / 'uploads_root')
        mock_cls.verify_backup.return_value = {
            'valid': True,
            'manifest': {
                'backup_scope': SCOPE_TENANT,
                'tenant_id': 7,
                'row_counts_per_table': {'tenants': 1, 'products': 1},
            },
        }
        archive = self._write_minimal_bundle(tmp_path, include_uploads=True)
        mock_cls._backup_path.return_value = archive
        mocker.patch(
            'services.backup_scoped_engine.ensure_target_schema',
            return_value=(True, None),
        )
        import_result = {
            'ok': True, 'inserted': {'tenants': 1, 'products': 1},
            'products_expected': 1, 'products_inserted': 1, 'rows_skipped': 0, 'errors': [],
        }
        mocker.patch('services.backup_scoped_restore.import_scoped_tables', return_value=import_result)
        mocker.patch(
            'services.backup_scoped_restore.verify_scoped_restore',
            return_value={'ok': True, 'errors': [], 'warnings': ['minor']},
        )
        dest = tmp_path / 'dest'
        dest.mkdir()
        result = restore_scoped_backup(
            mock_cls, 'bundle.tar.gz', 'postgresql://localhost/newdb',
            confirmation=RESTORE_CONFIRM,
            restore_uploads=True,
            uploads_dest_root=str(dest),
        )
        assert result['ok'] is True
        assert result['target_tenant_id'] == 7
        assert any('uploads' in w for w in result['warnings'])

    def test_import_failure_stops_restore(self, mocker, tmp_path):
        mock_cls = MagicMock()
        mock_cls._urls_same_database.return_value = False
        mock_cls.verify_backup.return_value = {
            'valid': True,
            'manifest': {'backup_scope': SCOPE_TENANT, 'tenant_id': 7},
        }
        mock_cls._backup_path.return_value = self._write_minimal_bundle(tmp_path)
        mocker.patch(
            'services.backup_scoped_engine.ensure_target_schema',
            return_value=(True, None),
        )
        mocker.patch(
            'services.backup_scoped_restore.import_scoped_tables',
            return_value={'ok': False, 'errors': ['tenants: fail'], 'inserted': {}},
        )
        result = restore_scoped_backup(
            mock_cls, 'bundle.tar.gz', 'postgresql://localhost/newdb',
            confirmation=RESTORE_CONFIRM,
        )
        assert result['ok'] is False

    def test_remap_auto_assigns_tenant_id(self, mocker, tmp_path):
        mock_cls = MagicMock()
        mock_cls._urls_same_database.return_value = False
        mock_cls.verify_backup.return_value = {
            'valid': True,
            'manifest': {'backup_scope': SCOPE_TENANT, 'tenant_id': 7},
        }
        mock_cls._backup_path.return_value = self._write_minimal_bundle(tmp_path)
        mocker.patch(
            'services.backup_scoped_engine.ensure_target_schema',
            return_value=(True, None),
        )
        conn = MagicMock()
        conn.execute.return_value.scalar.return_value = 10
        engine = MagicMock()
        engine.connect.return_value.__enter__ = MagicMock(return_value=conn)
        engine.connect.return_value.__exit__ = MagicMock(return_value=False)
        mocker.patch('sqlalchemy.create_engine', return_value=engine)
        import_mock = mocker.patch(
            'services.backup_scoped_restore.import_scoped_tables',
            return_value={
                'ok': True, 'inserted': {'tenants': 1},
                'products_expected': 0, 'products_inserted': 0, 'rows_skipped': 0, 'errors': [],
            },
        )
        mocker.patch(
            'services.backup_scoped_restore.verify_scoped_restore',
            return_value={'ok': True, 'errors': [], 'warnings': []},
        )
        result = restore_scoped_backup(
            mock_cls, 'bundle.tar.gz', 'postgresql://localhost/newdb',
            confirmation=REMAP_CONFIRM, remap=True,
        )
        assert result['ok'] is True
        assert import_mock.call_args.kwargs['target_tenant_id'] == 11

    def test_extract_bundle_with_checksums(self, tmp_path):
        manifest = {'backup_scope': SCOPE_STORE, 'tenant_id': 3}
        archive = tmp_path / 'full.tar.gz'
        with tarfile.open(archive, 'w:gz') as tar:
            for name, content in {
                'manifest.json': json.dumps(manifest),
                'checksums.sha256': 'abc123',
            }.items():
                data = content.encode('utf-8')
                info = tarfile.TarInfo(name=name)
                info.size = len(data)
                tar.addfile(info, BytesIO(data))
        work = tmp_path / 'work'
        work.mkdir()
        bundle = extract_scoped_bundle(str(archive), str(work))
        assert bundle['manifest']['tenant_id'] == 3
        assert 'checksums.sha256' in bundle

    def test_delete_skips_nonexistent_tables(self):
        conn = MagicMock()
        with patch('services.backup_scope_config.table_exists', return_value=False):
            _delete_tenant_scoped_data(conn, tenant_id=1)
        conn.execute.assert_not_called()

    def test_verify_skips_tables_without_tenant_id(self, mocker):
        conn = MagicMock()
        conn.begin_nested.return_value.__enter__ = MagicMock(return_value=None)
        conn.begin_nested.return_value.__exit__ = MagicMock(return_value=False)
        conn.execute.return_value.scalar.side_effect = [0, 0]
        engine = MagicMock()
        engine.connect.return_value.__enter__ = MagicMock(return_value=conn)
        engine.connect.return_value.__exit__ = MagicMock(return_value=False)
        mocker.patch('sqlalchemy.create_engine', return_value=engine)
        mocker.patch('services.backup_scope_config.table_exists', return_value=True)
        mocker.patch('services.backup_scoped_restore._table_has_column', return_value=False)
        out = verify_scoped_restore(
            'postgresql://localhost/target',
            {'row_counts_per_table': {'roles': 5}},
            expected_tenant_id=1, scope=SCOPE_TENANT,
        )
        assert out['ok'] is True

    def test_restore_verify_failure_extends_errors(self, mocker, tmp_path):
        mock_cls = MagicMock()
        mock_cls._urls_same_database.return_value = False
        mock_cls.verify_backup.return_value = {
            'valid': True,
            'manifest': {
                'backup_scope': SCOPE_TENANT,
                'tenant_id': 7,
                'row_counts_per_table': {'tenants': 1, 'products': 1},
            },
        }
        mock_cls._backup_path.return_value = TestRestoreScopedBackupFlow()._write_minimal_bundle(tmp_path)
        mocker.patch('services.backup_scoped_engine.ensure_target_schema', return_value=(True, None))
        mocker.patch(
            'services.backup_scoped_restore.import_scoped_tables',
            return_value={
                'ok': True, 'inserted': {'tenants': 1, 'products': 1},
                'products_expected': 1, 'products_inserted': 1, 'rows_skipped': 0, 'errors': [],
            },
        )
        mocker.patch(
            'services.backup_scoped_restore.verify_scoped_restore',
            return_value={'ok': False, 'errors': ['products: expected>=1 got 0'], 'warnings': []},
        )
        result = restore_scoped_backup(
            mock_cls, 'bundle.tar.gz', 'postgresql://localhost/newdb',
            confirmation=RESTORE_CONFIRM,
        )
        assert result['ok'] is False
        assert any('products' in e for e in result['errors'])
