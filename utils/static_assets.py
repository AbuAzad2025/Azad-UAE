"""Static asset helpers with content-hash cache busting."""

from __future__ import annotations

import hashlib
from pathlib import Path

from flask import current_app, url_for


def _asset_path(filename: str) -> Path:
    return Path(current_app.static_folder or "static") / filename


def static_hash(filename: str) -> str:
    """Return a short SHA-256 hash of a static file for cache-busting."""
    try:
        data = _asset_path(filename).read_bytes()
        return hashlib.sha256(data).hexdigest()[:12]
    except Exception:
        return ""


def static_v(filename: str) -> str:
    """Return a static URL with a content-hash query string."""
    digest = static_hash(filename)
    if digest:
        return url_for("static", filename=filename, v=digest)
    return url_for("static", filename=filename)


def dist_url(filename: str) -> str:
    """Resolve project assets through the minified ``dist/`` directory with a hash.

    ``js/app.js`` → ``js/dist/app.js?v=<hash>``
    ``css/erp-theme-unified.css`` → ``css/dist/erp-theme-unified.css?v=<hash>``

    Falls back to the original path if the dist file is missing.
    """
    if filename.startswith(("js/", "css/")):
        parts = filename.split("/", 1)
        dist_filename = f"{parts[0]}/dist/{parts[1]}"
        dist_path = _asset_path(dist_filename)
        if dist_path.exists():
            return static_v(dist_filename)
    return static_v(filename)
