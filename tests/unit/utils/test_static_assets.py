"""Tests for utils.static_assets cache-busting helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from utils.static_assets import dist_url, static_hash, static_v


@pytest.fixture
def static_dir(app):
    """Expose the configured static folder for the test app."""
    return app.static_folder


def _write(relative_path: str, content: str, static_dir: str) -> Path:
    path = Path(static_dir) / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def test_static_hash_returns_stable_digest(static_dir):
    _write("js/test_asset.js", "console.log('hello');", static_dir)
    digest = static_hash("js/test_asset.js")
    assert len(digest) == 12
    assert digest == static_hash("js/test_asset.js")


def test_static_hash_missing_file_returns_empty():
    assert static_hash("js/nonexistent_file_xyz.js") == ""


def test_static_v_includes_query_string(app, static_dir):
    _write("css/test_v.css", "body{color:red}", static_dir)
    with app.app_context():
        url = static_v("css/test_v.css")
    assert url.startswith("/static/css/test_v.css")
    assert "?v=" in url


def test_static_v_falls_back_when_missing(app):
    with app.app_context():
        url = static_v("css/missing_xyz.css")
    assert url == "/static/css/missing_xyz.css"


def test_dist_url_prefers_dist_file(app, static_dir):
    _write("js/app.js", "original", static_dir)
    _write("js/dist/app.js", "minified", static_dir)
    with app.app_context():
        url = dist_url("js/app.js")
    assert "/static/js/dist/app.js" in url
    assert "?v=" in url


def test_dist_url_falls_back_when_dist_missing(app, static_dir):
    _write("js/fallback.js", "fallback", static_dir)
    with app.app_context():
        url = dist_url("js/fallback.js")
    assert "/static/js/fallback.js" in url
    assert "js/dist" not in url


def test_dist_url_passes_through_non_js_css_assets(app, static_dir):
    _write("assets/brand/logo.png", "png", static_dir)
    with app.app_context():
        url = dist_url("assets/brand/logo.png")
    assert "/static/assets/brand/logo.png" in url
