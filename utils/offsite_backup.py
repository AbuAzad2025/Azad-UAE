"""
Offsite backup transfer — provider-agnostic S3-compatible client (boto3).

Uploads the newest local backup artifact to offsite storage after every
successful local backup and downloads artifacts back for restore drills.
Works with AWS S3 or any S3-compatible endpoint (MinIO, Wasabi, R2).

Configuration (environment variables only — never hardcode credentials):

    OFFSITE_BACKUP_ENABLED    "1"/"true"/"yes"/"on" to activate
    OFFSITE_BACKUP_BUCKET     target bucket name
    OFFSITE_BACKUP_PREFIX     key prefix inside the bucket (default "backups/")
    OFFSITE_BACKUP_ENDPOINT   optional custom endpoint URL (e.g. MinIO)

AWS credentials are read by boto3 from the standard environment names:
AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY / AWS_SESSION_TOKEN /
AWS_DEFAULT_REGION (or any other credential-chain source).  This module
never reads, stores, or logs secret values.

boto3 lives in requirements-optional.txt; it is imported lazily here so the
app runs unchanged when offsite backup is not installed/configured.

Failure policy: upload/download helpers NEVER raise — they return a status
dict so a broken offsite target can never crash the local backup path.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any

logger = logging.getLogger(__name__)

_TRUTHY = frozenset({"1", "true", "yes", "on"})
DEFAULT_PREFIX = "backups/"
MAX_ATTEMPTS = 3
_ARTIFACT_SUFFIXES = (".tar.gz", ".tar.gz.enc")


def _env(name: str) -> str:
    return (os.environ.get(name) or "").strip()


def is_enabled() -> bool:
    return _env("OFFSITE_BACKUP_ENABLED").lower() in _TRUTHY


def bucket_name() -> str:
    return _env("OFFSITE_BACKUP_BUCKET")


def key_prefix() -> str:
    prefix = _env("OFFSITE_BACKUP_PREFIX") or DEFAULT_PREFIX
    return prefix if prefix.endswith("/") else prefix + "/"


def endpoint_url() -> str | None:
    return _env("OFFSITE_BACKUP_ENDPOINT") or None


def is_configured() -> bool:
    """True when offsite upload should run (enabled AND bucket set)."""
    return is_enabled() and bool(bucket_name())


def status_summary() -> dict[str, Any]:
    """Non-secret configuration summary for diagnostics/UI."""
    return {
        "enabled": is_enabled(),
        "configured": is_configured(),
        "bucket": bucket_name() or None,
        "prefix": key_prefix(),
        "endpoint": endpoint_url(),
        "max_attempts": MAX_ATTEMPTS,
    }


def get_s3_client():
    """Create the boto3 S3 client. Lazy import: boto3 only needed when called."""
    import boto3

    return boto3.client("s3", endpoint_url=endpoint_url())


def object_key_for(archive_path: str) -> str:
    return key_prefix() + os.path.basename(archive_path)


def _is_artifact_key(key: str) -> bool:
    lowered = key.lower()
    return lowered.endswith(_ARTIFACT_SUFFIXES)


def upload_backup_archive(
    archive_path: str,
    *,
    max_attempts: int = MAX_ATTEMPTS,
    retry_delay: float = 1.0,
    s3_client: Any | None = None,
) -> dict[str, Any]:
    """Stream one archive to offsite storage with retries. Never raises.

    Uses boto3's managed transfer (``upload_fileobj``), which streams from
    the file handle in parts and switches to multipart upload automatically
    for large archives.
    """
    result: dict[str, Any] = {
        "ok": False,
        "key": None,
        "bucket": bucket_name() or None,
        "attempts": 0,
        "error": None,
    }
    if not is_configured():
        result["error"] = "offsite backup not configured"
        return result
    if not archive_path or not os.path.isfile(archive_path):
        result["error"] = f"archive not found: {os.path.basename(str(archive_path))}"
        return result

    key = object_key_for(archive_path)
    result["key"] = key
    client = s3_client
    for attempt in range(1, max(1, max_attempts) + 1):
        result["attempts"] = attempt
        try:
            if client is None:
                client = get_s3_client()
            # Streamed handle per attempt; managed transfer handles multipart.
            with open(archive_path, "rb") as fh:
                client.upload_fileobj(fh, bucket_name(), key)
            result["ok"] = True
            result["error"] = None
            logger.info("Offsite upload OK: %s (attempt %d)", key, attempt)
            return result
        except Exception as exc:
            result["error"] = f"{type(exc).__name__}: {exc}"[:300]
            logger.warning("Offsite upload attempt %d/%d failed for %s", attempt, max_attempts, key)
            if attempt < max_attempts:
                time.sleep(retry_delay * attempt)
    logger.error("Offsite upload failed after %d attempts for %s", result["attempts"], key)
    return result


def latest_remote_artifact(*, s3_client: Any | None = None) -> dict[str, Any]:
    """Find the newest backup artifact under the configured prefix. Never raises."""
    out: dict[str, Any] = {"ok": False, "key": None, "last_modified": None, "size": None, "error": None}
    if not is_configured():
        out["error"] = "offsite backup not configured"
        return out
    try:
        client = s3_client or get_s3_client()
        paginator = client.get_paginator("list_objects_v2")
        newest: dict[str, Any] | None = None
        for page in paginator.paginate(Bucket=bucket_name(), Prefix=key_prefix()):
            for obj in page.get("Contents", []):
                if not _is_artifact_key(obj.get("key", "")):
                    continue
                if newest is None or obj["LastModified"] > newest["LastModified"]:
                    newest = obj
        if newest is None:
            out["error"] = "no backup artifact found under prefix"
            return out
        out.update(ok=True, key=newest["key"], last_modified=newest["LastModified"], size=newest.get("Size"))
        return out
    except Exception as exc:
        out["error"] = f"{type(exc).__name__}: {exc}"[:300]
        return out


def download_artifact(
    key: str,
    dest_dir: str,
    *,
    max_attempts: int = MAX_ATTEMPTS,
    retry_delay: float = 1.0,
    s3_client: Any | None = None,
) -> dict[str, Any]:
    """Stream one artifact from offsite storage to ``dest_dir``. Never raises."""
    result: dict[str, Any] = {"ok": False, "path": None, "key": key, "attempts": 0, "error": None}
    if not is_configured():
        result["error"] = "offsite backup not configured"
        return result
    safe_base = os.path.basename(key.replace("\\", "/"))
    if not safe_base or safe_base.startswith("."):
        result["error"] = "invalid object key"
        return result
    dest_path = os.path.join(dest_dir, safe_base)
    result["path"] = dest_path
    client = s3_client
    for attempt in range(1, max(1, max_attempts) + 1):
        result["attempts"] = attempt
        try:
            if client is None:
                client = get_s3_client()
            os.makedirs(dest_dir, exist_ok=True)
            with open(dest_path, "wb") as fh:
                # Managed transfer streams multipart downloads to disk.
                client.download_fileobj(bucket_name(), key, fh)
            if os.path.getsize(dest_path) == 0:
                raise OSError("downloaded artifact is empty")
            result["ok"] = True
            result["error"] = None
            logger.info("Offsite download OK: %s (attempt %d)", key, attempt)
            return result
        except Exception as exc:
            result["error"] = f"{type(exc).__name__}: {exc}"[:300]
            logger.warning("Offsite download attempt %d/%d failed for %s", attempt, max_attempts, key)
            if attempt < max_attempts:
                time.sleep(retry_delay * attempt)
    return result


def download_latest_offsite_artifact(
    dest_dir: str,
    *,
    max_attempts: int = MAX_ATTEMPTS,
    retry_delay: float = 1.0,
    s3_client: Any | None = None,
) -> dict[str, Any]:
    """Download the newest offsite artifact into ``dest_dir``. Never raises."""
    found = latest_remote_artifact(s3_client=s3_client)
    if not found.get("ok"):
        return {"ok": False, "path": None, "key": None, "attempts": 0, "error": found.get("error")}
    return download_artifact(
        found["key"],
        dest_dir,
        max_attempts=max_attempts,
        retry_delay=retry_delay,
        s3_client=s3_client,
    )
