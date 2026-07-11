"""Scoped backup restore — bundle extraction, remap, tenant partition guards."""
from __future__ import annotations

import json
import os
import tarfile
from unittest.mock import MagicMock

import pytest

from services.backup_scope_config import SCOPE_BRANCH, SCOPE_TENANT


class TestConfirmationGuards:
    """restore_scoped_backup — typed confirmation and target DB lock."""

    def test_wrong_confirmation_rejected(self, mocker):
        mock_cls = MagicMock()
        from services.backup_scoped_restore import restore_scoped_backup

        result = restore_scoped_backup(
            mock_cls, 'backup.tar.gz', 'postgresql://localhost/newdb',
            confirmation='WRONG',
        )
        assert result['ok'] is False
        assert 'RESTORE CONFIRM' in result['errors'][0]
        mock_cls.verify_backup.assert_not_called()

    def test_remap_requires_remap_confirm(self, mocker):
        mock_cls = MagicMock()
        from services.backup_scoped_restore import restore_scoped_backup

        result = restore_scoped_backup(
            mock_cls, 'b.tar.gz', 'postgresql://localhost/newdb',
            confirmation='RESTORE CONFIRM', remap=True,
        )
        assert result['ok'] is False
        assert 'REMAP CONFIRM' in result['errors'][0]

    def test_blocks_restore_to_current_database(self, mocker):
        mock_cls = MagicMock()
        mock_cls._urls_same_database.return_value = True
        mocker.patch.dict(os.environ, {'DATABASE_URL': 'postgresql://localhost/live'})

        from services.backup_scoped_restore import restore_scoped_backup

        result = restore_scoped_backup(
            mock_cls, 'b.tar.gz', 'postgresql://localhost/live',
            confirmation='RESTORE CONFIRM',
        )
        assert result['ok'] is False
        assert 'same as current' in result['errors'][0]

    def test_corrupted_backup_verification_fails(self, mocker):
        mock_cls = MagicMock()
        mock_cls._urls_same_database.return_value = False
        mock_cls.verify_backup.return_value = {'valid': False, 'error': 'checksum mismatch'}

        from services.backup_scoped_restore import restore_scoped_backup

        result = restore_scoped_backup(
            mock_cls, 'bad.tar.gz', 'postgresql://localhost/restore_db',
            confirmation='RESTORE CONFIRM',
        )
        assert result['ok'] is False
        assert 'verification failed' in result['errors'][0]


class TestBundleExtraction:
    """extract_scoped_bundle — manifest, data dir, legacy export."""

    def _write_bundle(self, path, members):
        with tarfile.open(path, 'w:gz') as tar:
            for name, content in members.items():
                if isinstance(content, bytes):
                    data = content
                else:
                    data = content.encode('utf-8')
                import io
                info = tarfile.TarInfo(name=name)
                info.size = len(data)
                tar.addfile(info, io.BytesIO(data))

    def test_extract_modern_data_directory(self, tmp_path):
        manifest = {'backup_scope': SCOPE_TENANT, 'tenant_id': 7, 'row_counts_per_table': {'products': 2}}
        products = [{'id': 1, 'tenant_id': 7, 'name': 'A'}, {'id': 2, 'tenant_id': 7, 'name': 'B'}]
        data_dir = tmp_path / 'bundle_data'
        data_dir.mkdir()
        (data_dir / 'schema_meta.json').write_text('{}', encoding='utf-8')
        (data_dir / 'products.jsonl').write_text(
            '\n'.join(json.dumps(r) for r in products), encoding='utf-8'
        )

        archive = tmp_path / 'scoped.tar.gz'
        with tarfile.open(archive, 'w:gz') as tar:
            tar.add(data_dir, arcname='data')
            manifest_path = tmp_path / 'manifest.json'
            manifest_path.write_text(json.dumps(manifest), encoding='utf-8')
            tar.add(manifest_path, arcname='manifest.json')

        work = tmp_path / 'work'
        work.mkdir()
        from services.backup_scoped_restore import extract_scoped_bundle

        bundle = extract_scoped_bundle(str(archive), str(work))
        assert bundle['manifest']['tenant_id'] == 7
        assert len(bundle['tables']['products']) == 2

    def test_missing_manifest_raises(self, tmp_path):
        archive = tmp_path / 'empty.tar.gz'
        with tarfile.open(archive, 'w:gz'):
            pass
        from services.backup_scoped_restore import extract_scoped_bundle

        with pytest.raises(RuntimeError, match='missing manifest'):
            extract_scoped_bundle(str(archive), str(tmp_path / 'w'))

    def test_legacy_tenant_export_fallback(self, tmp_path):
        legacy = {'tables': {'tenants': [{'id': 3, 'slug': 'legacy'}]}}
        archive = tmp_path / 'legacy.tar.gz'
        self._write_bundle(archive, {
            'manifest.json': json.dumps({'backup_scope': SCOPE_TENANT, 'tenant_id': 3}),
            'tenant_export.json': json.dumps(legacy),
        })
        work = tmp_path / 'work2'
        work.mkdir()
        from services.backup_scoped_restore import extract_scoped_bundle

        bundle = extract_scoped_bundle(str(archive), str(work))
        assert bundle['tables']['tenants'][0]['slug'] == 'legacy'


class TestIdRemap:
    """_build_id_remap / _apply_row_remap — tenant partition isolation."""

    def test_remap_assigns_new_tenant_and_synthetic_ids(self):
        tables = {
            'tenants': [{'id': 1, 'slug': 'acme'}],
            'branches': [{'id': 5, 'tenant_id': 1}],
            'products': [{'id': 10, 'tenant_id': 1, 'branch_id': 5}],
        }
        from services.backup_scoped_restore import _apply_row_remap, _build_id_remap

        id_maps = _build_id_remap(tables, new_tenant_id=99, new_branch_id=500)
        assert id_maps['tenants'][1] == 99
        assert id_maps['branches'][5] == 500

        row = _apply_row_remap(
            tables['products'][0], 'products', id_maps,
            new_tenant_id=99, old_tenant_id=1, scope=SCOPE_TENANT, remap=True,
            new_branch_id=500,
        )
        assert row['tenant_id'] == 99
        assert row['id'] != 10
        assert row['branch_id'] == 500

    def test_branch_scope_forces_branch_id(self):
        from services.backup_scoped_restore import _apply_row_remap

        row = _apply_row_remap(
            {'id': 1, 'tenant_id': 1, 'branch_id': 9},
            'sales', {}, new_tenant_id=1, old_tenant_id=1,
            scope=SCOPE_BRANCH, new_branch_id=42,
        )
        assert row['branch_id'] == 42

    def test_remap_slug_suffix_on_tenant(self):
        from services.backup_scoped_restore import _apply_row_remap

        row = _apply_row_remap(
            {'id': 1, 'slug': 'shop', 'tenant_id': 1},
            'tenants', {'tenants': {1: 200}},
            new_tenant_id=200, old_tenant_id=1, scope=SCOPE_TENANT, remap=True,
        )
        assert row['slug'].endswith('_r200')


class TestImportScopedTables:
    """import_scoped_tables — insert loop, rollback on row errors, fatal table guard."""

    def _mock_engine(self, mocker):
        conn = MagicMock()
        nested = MagicMock()
        conn.begin_nested.return_value.__enter__ = MagicMock(return_value=None)
        conn.begin_nested.return_value.__exit__ = MagicMock(return_value=False)
        conn.execute.return_value = MagicMock()

        engine = MagicMock()
        engine.begin.return_value.__enter__ = MagicMock(return_value=conn)
        engine.begin.return_value.__exit__ = MagicMock(return_value=False)

        mocker.patch('sqlalchemy.create_engine', return_value=engine)
        mocker.patch(
            'services.backup_scoped_restore._delete_tenant_scoped_data',
        )
        return conn

    def test_successful_insert_counts_rows(self, mocker):
        self._mock_engine(mocker)
        tables = {
            'tenants': [{'id': 1, 'slug': 't'}],
            'roles': [{'id': 1, 'name': 'admin'}],
            'branches': [{'id': 2, 'tenant_id': 1}],
            'products': [{'id': 10, 'tenant_id': 1, 'name': 'P'}],
        }
        from services.backup_scoped_restore import import_scoped_tables

        result = import_scoped_tables(
            'postgresql://localhost/target', tables,
            scope=SCOPE_TENANT, source_tenant_id=1,
        )
        assert result['ok'] is True
        assert result['inserted']['products'] == 1
        assert result['products_inserted'] == 1

    def test_partial_product_failure_marks_not_ok(self, mocker):
        conn = self._mock_engine(mocker)
        call_count = {'n': 0}

        def execute_side_effect(*args, **kwargs):
            sql = str(args[0]) if args else ''
            if 'INSERT INTO "products"' in sql:
                call_count['n'] += 1
                if call_count['n'] >= 2:
                    raise RuntimeError('constraint violation')
            return MagicMock()

        conn.execute.side_effect = execute_side_effect
        tables = {
            'tenants': [{'id': 1}],
            'roles': [{'id': 1}],
            'branches': [{'id': 2, 'tenant_id': 1}],
            'products': [
                {'id': 10, 'tenant_id': 1},
                {'id': 11, 'tenant_id': 1},
            ],
        }
        from services.backup_scoped_restore import import_scoped_tables

        result = import_scoped_tables(
            'postgresql://localhost/target', tables,
            scope=SCOPE_TENANT, source_tenant_id=1,
        )
        assert result['ok'] is False
        assert result['rows_skipped'] >= 1
        assert any('products' in e for e in result['errors'])


class TestVerifyScopedRestore:
    """verify_scoped_restore — row counts and orphan FK detection."""

    def test_core_table_shortfall_fails_verify(self, mocker):
        conn = MagicMock()
        conn.begin_nested.return_value.__enter__ = MagicMock(return_value=None)
        conn.begin_nested.return_value.__exit__ = MagicMock(return_value=False)
        conn.execute.return_value.scalar.side_effect = [1, 0, 0]

        engine = MagicMock()
        engine.connect.return_value.__enter__ = MagicMock(return_value=conn)
        engine.connect.return_value.__exit__ = MagicMock(return_value=False)
        mocker.patch('sqlalchemy.create_engine', return_value=engine)
        mocker.patch('services.backup_scope_config.table_exists', return_value=True)
        mocker.patch('services.backup_scoped_restore._table_has_column', return_value=True)

        from services.backup_scoped_restore import verify_scoped_restore

        out = verify_scoped_restore(
            'postgresql://localhost/target',
            {'row_counts_per_table': {'tenants': 1, 'products': 5}},
            expected_tenant_id=1, scope=SCOPE_TENANT,
        )
        assert out['ok'] is False
        assert any('products' in e for e in out['errors'])
