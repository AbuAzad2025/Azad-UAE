"""Tests for utils.offsite_backup — boto3 is fully mocked, never imported for real."""

from __future__ import annotations

import os
import sys
import types
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from utils import offsite_backup


@pytest.fixture
def offsite_env(monkeypatch):
    monkeypatch.setenv("OFFSITE_BACKUP_ENABLED", "1")
    monkeypatch.setenv("OFFSITE_BACKUP_BUCKET", "azad-backups-test")
    monkeypatch.delenv("OFFSITE_BACKUP_PREFIX", raising=False)
    monkeypatch.delenv("OFFSITE_BACKUP_ENDPOINT", raising=False)
    monkeypatch.delenv("AWS_ACCESS_KEY_ID", raising=False)
    return None


@pytest.fixture
def fake_boto3():
    """Inject a fake boto3 module so no network client can ever be created."""
    client = MagicMock(name="s3_client")
    module = types.ModuleType("boto3")
    module.client = MagicMock(return_value=client)
    with patch.dict(sys.modules, {"boto3": module}):
        yield module, client


class TestConfiguration:
    def test_disabled_by_default(self, monkeypatch):
        monkeypatch.delenv("OFFSITE_BACKUP_ENABLED", raising=False)
        monkeypatch.delenv("OFFSITE_BACKUP_BUCKET", raising=False)
        assert offsite_backup.is_enabled() is False
        assert offsite_backup.is_configured() is False

    def test_enabled_without_bucket_is_unconfigured(self, monkeypatch):
        monkeypatch.setenv("OFFSITE_BACKUP_ENABLED", "1")
        monkeypatch.delenv("OFFSITE_BACKUP_BUCKET", raising=False)
        assert offsite_backup.is_configured() is False

    def test_configured_when_enabled_and_bucket(self, offsite_env):
        assert offsite_backup.is_configured() is True

    @pytest.mark.parametrize("value", ["0", "false", "", "no"])
    def test_disabled_values(self, monkeypatch, value):
        monkeypatch.setenv("OFFSITE_BACKUP_ENABLED", value)
        monkeypatch.setenv("OFFSITE_BACKUP_BUCKET", "bucket")
        assert offsite_backup.is_configured() is False

    def test_prefix_gets_trailing_slash(self, monkeypatch):
        monkeypatch.setenv("OFFSITE_BACKUP_PREFIX", "prod/nightly")
        assert offsite_backup.key_prefix() == "prod/nightly/"

    def test_default_prefix(self, monkeypatch):
        monkeypatch.delenv("OFFSITE_BACKUP_PREFIX", raising=False)
        assert offsite_backup.key_prefix() == "backups/"

    def test_status_summary_has_no_secrets(self, monkeypatch, offsite_env):
        monkeypatch.setenv("AWS_ACCESS_KEY_ID", "AKIASECRETVALUE")
        monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "SUPERSECRET")
        summary = offsite_backup.status_summary()
        serialized = str(summary)
        assert "AKIASECRETVALUE" not in serialized
        assert "SUPERSECRET" not in serialized
        assert set(summary) == {"enabled", "configured", "bucket", "prefix", "endpoint", "max_attempts"}


class TestUpload:
    def test_noop_when_not_configured(self, monkeypatch, tmp_path):
        monkeypatch.delenv("OFFSITE_BACKUP_ENABLED", raising=False)
        result = offsite_backup.upload_backup_archive(str(tmp_path / "x.tar.gz"))
        assert result["ok"] is False
        assert result["attempts"] == 0

    def test_missing_archive_never_calls_boto3(self, offsite_env, tmp_path):
        result = offsite_backup.upload_backup_archive(str(tmp_path / "missing.tar.gz"))
        assert result["ok"] is False
        assert result["attempts"] == 0
        assert "not found" in result["error"]

    def test_upload_success_streams_fileobj(self, offsite_env, fake_boto3, tmp_path):
        _, client = fake_boto3
        archive = tmp_path / "azad_backup_system_20260101_000000_abc.tar.gz"
        archive.write_bytes(b"archive-bytes")
        captured: dict = {}

        def record(handle, bucket, key):
            captured["data"] = handle.read()
            captured["bucket"] = bucket
            captured["key"] = key

        client.upload_fileobj.side_effect = record

        result = offsite_backup.upload_backup_archive(str(archive))

        assert result == {
            "ok": True,
            "key": "backups/azad_backup_system_20260101_000000_abc.tar.gz",
            "bucket": "azad-backups-test",
            "attempts": 1,
            "error": None,
        }
        assert captured == {
            "data": b"archive-bytes",
            "bucket": "azad-backups-test",
            "key": "backups/azad_backup_system_20260101_000000_abc.tar.gz",
        }

    def test_retry_then_success(self, offsite_env, fake_boto3, tmp_path):
        _, client = fake_boto3
        archive = tmp_path / "backup.tar.gz"
        archive.write_bytes(b"data")
        client.upload_fileobj.side_effect = [OSError("boom"), None]

        with patch.object(offsite_backup.time, "sleep") as sleeper:
            result = offsite_backup.upload_backup_archive(str(archive))

        assert result["ok"] is True
        assert result["attempts"] == 2
        assert client.upload_fileobj.call_count == 2
        sleeper.assert_called_once_with(1.0)

    def test_retries_exhausted_returns_failure_without_raising(self, offsite_env, fake_boto3, tmp_path):
        _, client = fake_boto3
        archive = tmp_path / "backup.tar.gz"
        archive.write_bytes(b"data")
        client.upload_fileobj.side_effect = OSError("endpoint down")

        with patch.object(offsite_backup.time, "sleep") as sleeper:
            result = offsite_backup.upload_backup_archive(str(archive), retry_delay=2.0)

        assert result["ok"] is False
        assert result["attempts"] == 3
        assert "endpoint down" in result["error"]
        assert sleeper.call_count == 2

    def test_endpoint_forwarded_to_client(self, offsite_env, monkeypatch, fake_boto3):
        module, _ = fake_boto3
        monkeypatch.setenv("OFFSITE_BACKUP_ENDPOINT", "http://minio.local:9000")
        offsite_backup.get_s3_client()
        _, kwargs = module.client.call_args
        assert kwargs == {"endpoint_url": "http://minio.local:9000"}


class TestDownloadLatest:
    def _paginator(self, client, objects):
        paginator = MagicMock()
        paginator.paginate.return_value = [{"Contents": objects}]
        client.get_paginator.return_value = paginator

    def test_picks_newest_artifact(self, offsite_env, fake_boto3, tmp_path):
        _, client = fake_boto3
        old = datetime(2026, 1, 1, tzinfo=UTC)
        new = old + timedelta(days=1)
        self._paginator(
            client,
            [
                {"key": "backups/old.tar.gz", "LastModified": old, "Size": 10},
                {"key": "backups/new.tar.gz.enc", "LastModified": new, "Size": 20},
                {"key": "backups/not-an-artifact.json", "LastModified": new + timedelta(days=9), "Size": 5},
            ],
        )

        found = offsite_backup.latest_remote_artifact()

        assert found["ok"] is True
        assert found["key"] == "backups/new.tar.gz.enc"
        assert found["size"] == 20

    def test_download_streams_and_reports_path(self, offsite_env, fake_boto3, tmp_path):
        _, client = fake_boto3

        def write_payload(bucket, key, handle):
            handle.write(b"restored-bytes")

        client.download_fileobj.side_effect = write_payload
        result = offsite_backup.download_artifact("backups/new.tar.gz", str(tmp_path))

        assert result["ok"] is True
        assert result["path"].endswith("new.tar.gz")
        assert open(result["path"], "rb").read() == b"restored-bytes"
        args, _ = client.download_fileobj.call_args
        assert args == ("azad-backups-test", "backups/new.tar.gz", args[2])

    def test_download_latest_combines_listing_and_download(self, offsite_env, fake_boto3, tmp_path):
        _, client = fake_boto3
        newest = datetime(2026, 6, 1, tzinfo=UTC)
        self._paginator(client, [{"key": "backups/latest.tar.gz", "LastModified": newest, "Size": 7}])

        def write_payload(bucket, key, handle):
            handle.write(b"x" * 7)

        client.download_fileobj.side_effect = write_payload
        result = offsite_backup.download_latest_offsite_artifact(str(tmp_path))

        assert result["ok"] is True
        assert result["key"] == "backups/latest.tar.gz"

    def test_no_artifact_found(self, offsite_env, fake_boto3):
        _, client = fake_boto3
        self._paginator(client, [])
        found = offsite_backup.latest_remote_artifact()
        assert found["ok"] is False
        assert "no backup artifact" in found["error"]

    def test_download_flattens_key_inside_dest_dir(self, offsite_env, fake_boto3, tmp_path):
        _, client = fake_boto3
        client.download_fileobj.side_effect = lambda bucket, key, handle: handle.write(b"d")
        result = offsite_backup.download_artifact("../escape/evil.tar.gz", str(tmp_path))
        assert result["ok"] is True
        assert os.path.dirname(result["path"]) == str(tmp_path)

    def test_empty_download_treated_as_failure(self, offsite_env, fake_boto3, tmp_path):
        _, client = fake_boto3
        client.download_fileobj.return_value = None
        with patch.object(offsite_backup.time, "sleep"):
            result = offsite_backup.download_artifact("backups/x.tar.gz", str(tmp_path))
        assert result["ok"] is False
        assert result["attempts"] == 3
