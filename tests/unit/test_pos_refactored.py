import os
import pytest

TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "templates")
STATIC_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "static")


def _template_path(*parts):
    return os.path.join(TEMPLATE_DIR, *parts)


def _static_path(*parts):
    return os.path.join(STATIC_DIR, *parts)


def test_no_inline_script_in_pos():
    path = _template_path("pos", "index.html")
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    lines = content.splitlines()
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if "<script>" in stripped and "src=" not in stripped:
            if "window.POS_BASE_CURRENCY" in stripped:
                continue
            if "barcode-scanner.js" in stripped:
                continue
            pytest.fail(f"Inline <script> without src= found at line {i}: {stripped}")


def test_pos_js_exists():
    assert os.path.isfile(
        _static_path("js", "pos", "index.js")
    ), "static/js/pos/index.js not found"


def test_pos_css_exists():
    assert os.path.isfile(
        _static_path("css", "pos-theme.css")
    ), "static/css/pos-theme.css not found"
