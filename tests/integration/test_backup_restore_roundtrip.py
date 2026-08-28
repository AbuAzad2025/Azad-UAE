"""Encrypted backup/restore round-trip integration test (M5)."""

from __future__ import annotations

import os
import uuid
from urllib.parse import urlparse, urlunparse

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool

from services.backup_service import BackupService
from utils.db_safety import atomic_transaction


@pytest.fixture(scope="class")
def backup_key():
    """32-byte encryption key for backup round-trip tests."""
    return "backup-test-key-32-chars-long!!"


class TestBackupRestoreRoundtrip:
    def _admin_database_url(self, url: str) -> str:
        parsed = urlparse(url)
        return urlunparse(parsed._replace(path="/postgres"))

    def _create_temp_database(self, admin_url: str, db_name: str) -> None:
        engine = create_engine(admin_url, isolation_level="AUTOCOMMIT", poolclass=NullPool)
        try:
            with engine.connect() as conn:
                conn.execute(text(f'CREATE DATABASE "{db_name}"'))
        finally:
            engine.dispose()

    def _drop_temp_database(self, admin_url: str, db_name: str) -> None:
        engine = create_engine(admin_url, isolation_level="AUTOCOMMIT", poolclass=NullPool)
        try:
            with engine.connect() as conn:
                conn.execute(
                    text(
                        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                        "WHERE datname = :name AND pid <> pg_backend_pid()"
                    ),
                    {"name": db_name},
                )
                conn.execute(text(f'DROP DATABASE IF EXISTS "{db_name}"'))
        finally:
            engine.dispose()

    def test_encrypted_backup_restore_roundtrip(
        self,
        app,
        db_session,
        demo_tenant,
        demo_product,
        backup_key,
    ):
        """Daily auto-backup encrypts the archive; restore to temp DB preserves data."""
        pg_tools = BackupService.pg_tools_status()
        if not pg_tools.get("available"):
            pytest.skip("pg_dump/pg_restore not available")

        original_key = app.config.get("BACKUP_ENCRYPTION_KEY")
        original_env_key = os.environ.get("BACKUP_ENCRYPTION_KEY")

        try:
            app.config["BACKUP_ENCRYPTION_KEY"] = backup_key
            os.environ["BACKUP_ENCRYPTION_KEY"] = backup_key
            BackupService._crypto_instance = None

            # Seed a distinct product for verification
            demo_product.name = f"Backup Test Product {uuid.uuid4().hex[:8]}"
            db_session.commit()
            seeded_tenant_name = demo_tenant.name
            seeded_product_name = demo_product.name

            with atomic_transaction("backup_roundtrip_seed"):
                result = BackupService.create_backup(
                    manual=True,
                    description="Integration test system backup",
                    scope="system",
                )

            assert result is not None, "Backup creation returned None"
            archive_path = result.get("path")
            assert archive_path is not None
            assert archive_path.endswith(".enc")
            assert os.path.isfile(archive_path)

            unencrypted_path = archive_path[: -len(".enc")]
            assert not os.path.exists(unencrypted_path), "Plaintext archive was not removed"

            # Build target DB URL
            base_url = os.environ.get("DATABASE_URL") or app.config.get("SQLALCHEMY_DATABASE_URI")
            parsed = urlparse(base_url)
            temp_db_name = f"azad_backup_restore_test_{uuid.uuid4().hex[:8]}"
            target_url = urlunparse(parsed._replace(path=f"/{temp_db_name}"))
            admin_url = self._admin_database_url(base_url)

            self._create_temp_database(admin_url, temp_db_name)
            try:
                restore_result = BackupService.restore_backup_to_target_db(
                    os.path.basename(archive_path),
                    target_url,
                    confirmation="RESTORE CONFIRM",
                )
                assert restore_result.get("ok") is True, restore_result.get("errors")

                target_engine = create_engine(target_url, poolclass=NullPool)
                try:
                    with target_engine.connect() as conn:
                        tenant_row = conn.execute(
                            text("SELECT name FROM tenants WHERE name = :name"),
                            {"name": seeded_tenant_name},
                        ).fetchone()
                        assert tenant_row is not None, "Tenant not restored"

                        product_row = conn.execute(
                            text("SELECT name FROM products WHERE name = :name"),
                            {"name": seeded_product_name},
                        ).fetchone()
                        assert product_row is not None, "Product not restored"
                finally:
                    target_engine.dispose()
            finally:
                self._drop_temp_database(admin_url, temp_db_name)

            # Cleanup archive and sidecar
            BackupService.delete_backup(os.path.basename(archive_path))
        finally:
            app.config["BACKUP_ENCRYPTION_KEY"] = original_key
            if original_env_key is not None:
                os.environ["BACKUP_ENCRYPTION_KEY"] = original_env_key
            else:
                os.environ.pop("BACKUP_ENCRYPTION_KEY", None)
            BackupService._crypto_instance = None
