import pytest
import pathlib

BASE = pathlib.Path(__file__).resolve().parents[2]
TEMPLATES = BASE / "templates"


def test_fontawesome_cdn_v6():
    head = (TEMPLATES / "partials" / "head.html").read_text(encoding="utf-8")
    assert "font-awesome/6." in head


def test_fa_css_links_updated():
    for path in sorted(TEMPLATES.rglob("*.html")):
        text = path.read_text(encoding="utf-8")
        assert "font-awesome/5." not in text, f"{path.relative_to(TEMPLATES)} still references FA 5"
