import os
import re

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def test_json_ld_partial_exists():
    path = os.path.join(BASE_DIR, "templates", "partials", "seo-landing.html")
    assert os.path.isfile(path), "seo-landing.html partial not found"


def test_landing_includes_json_ld():
    path = os.path.join(BASE_DIR, "templates", "public", "landing.html")
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    assert "partials/seo-landing.html" in content, "landing.html does not include seo-landing partial"


def test_no_dupe_integrity():
    path = os.path.join(BASE_DIR, "templates", "public", "landing.html")
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    matches = re.findall(r'integrity=.*?integrity=', content)
    assert len(matches) == 0, f"Found double integrity attributes: {matches}"


def test_fa6_loaded():
    path = os.path.join(BASE_DIR, "templates", "public", "landing.html")
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    assert "font-awesome/6." in content, "landing.html does not reference Font Awesome 6"

def test_landing_uses_external_css_for_inline_styles():
    path = os.path.join(BASE_DIR, "templates", "public", "landing.html")
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    assert "landing-page-en.css" in content, "landing.html should link landing-page-en.css"
    assert "landing-page-ar.css" in content, "landing.html should link landing-page-ar.css"
    assert "<style>" not in content, "landing.html should not contain inline <style> blocks"
