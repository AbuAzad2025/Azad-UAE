"""Tests for utils/build_assets.py uncovered lines."""

import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest


def test_minify_js_import_error():
    """Test _minify_js when jsmin is not installed."""
    from utils.build_assets import _minify_js

    with patch.dict("sys.modules", {"jsmin": None}):
        result = _minify_js("var x = 1;")
        assert result is None


def test_minify_css_import_error():
    """Test _minify_css when cssmin and rcssmin are not installed."""
    from utils.build_assets import _minify_css

    with patch.dict("sys.modules", {"cssmin": None, "rcssmin": None}):
        result = _minify_css("body { color: red; }")
        assert result is None


def test_minify_css_rcssmin_fallback():
    """Test _minify_css falls back to rcssmin."""
    from utils.build_assets import _minify_css

    mock_rcssmin = MagicMock()
    mock_rcssmin.cssmin.return_value = "body{color:red}"

    with patch.dict("sys.modules", {"cssmin": None, "rcssmin": mock_rcssmin}):
        result = _minify_css("body { color: red; }")
        assert result == "body{color:red}"


def test_minify_js_calls_jsmin():
    """Test _minify_js calls jsmin."""
    from utils.build_assets import _minify_js

    mock_jsmin = MagicMock()
    mock_jsmin.jsmin.return_value = "var x=1"

    with patch.dict("sys.modules", {"jsmin": mock_jsmin}):
        result = _minify_js("var x = 1;")
        assert result == "var x=1"


def test_minify_dispatcher_js():
    """Test _minify dispatcher for JS."""
    from utils.build_assets import _minify

    with patch("utils.build_assets._minify_js", return_value="minified") as mock_js:
        result = _minify("code", ".js")
        assert result == "minified"
        mock_js.assert_called_once()


def test_minify_dispatcher_css():
    """Test _minify dispatcher for CSS."""
    from utils.build_assets import _minify

    with patch("utils.build_assets._minify_css", return_value="minified") as mock_css:
        result = _minify("code", ".css")
        assert result == "minified"
        mock_css.assert_called_once()


def test_gzip_file():
    """Test _gzip_file creates a .gz file."""
    from utils.build_assets import _gzip_file

    with tempfile.NamedTemporaryFile(mode="w", suffix=".js", delete=False) as f:
        f.write("var x = 1;")
        src_path = f.name

    try:
        gz_path = _gzip_file(src_path)
        assert gz_path.endswith(".gz")
        assert os.path.exists(gz_path)
        assert os.path.getsize(gz_path) > 0
    finally:
        os.unlink(src_path)
        if os.path.exists(gz_path):
            os.unlink(gz_path)


def test_process_file_js():
    """Test _process_file with a JS file."""
    from utils.build_assets import _process_file

    with tempfile.NamedTemporaryFile(mode="w", suffix=".js", delete=False, encoding="utf-8") as f:
        f.write("var x = 1;")
        src_path = f.name

    try:
        result = _process_file(src_path)
        assert result is not None
        assert result["file"].endswith(".js")
        assert result["original"] > 0
        assert result["hash"] is not None
    finally:
        os.unlink(src_path)
        dir_name = os.path.dirname(src_path)
        for fn in os.listdir(dir_name):
            if fn.endswith(".min.js") or fn.endswith(".gz"):
                os.unlink(os.path.join(dir_name, fn))


def test_process_file_css():
    """Test _process_file with a CSS file."""
    from utils.build_assets import _process_file

    with tempfile.NamedTemporaryFile(mode="w", suffix=".css", delete=False, encoding="utf-8") as f:
        f.write("body { color: red; }")
        src_path = f.name

    try:
        result = _process_file(src_path)
        assert result is not None
        assert result["file"].endswith(".css")
        assert result["original"] > 0
    finally:
        os.unlink(src_path)
        dir_name = os.path.dirname(src_path)
        for fn in os.listdir(dir_name):
            if fn.endswith(".min.css") or fn.endswith(".gz"):
                os.unlink(os.path.join(dir_name, fn))


def test_process_file_unsupported_ext():
    """Test _process_file with unsupported extension."""
    from utils.build_assets import _process_file

    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write("hello")
        src_path = f.name

    try:
        result = _process_file(src_path)
        assert result is None
    finally:
        os.unlink(src_path)


def test_collect_files_nonexistent_dir():
    """Test _collect_files with non-existent directory."""
    from utils.build_assets import _collect_files

    result = _collect_files("/nonexistent", "static/js", (".js",))
    assert result == []


def test_collect_files_filters_minified():
    """Test _collect_files filters out already minified files."""
    from utils.build_assets import _collect_files

    with tempfile.TemporaryDirectory() as tmpdir:
        sub_dir = os.path.join(tmpdir, "static", "js")
        os.makedirs(sub_dir)

        with open(os.path.join(sub_dir, "app.js"), "w") as f:
            f.write("var x = 1;")
        with open(os.path.join(sub_dir, "app.min.js"), "w") as f:
            f.write("var x=1;")

        result = _collect_files(tmpdir, "static/js", (".js",))
        assert len(result) == 1
        assert result[0].endswith("app.js")


def test_build_all_nonexistent_base():
    """Test build_all with non-existent base directory."""
    from utils.build_assets import build_all

    result = build_all("/nonexistent/path")
    assert result == []


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
