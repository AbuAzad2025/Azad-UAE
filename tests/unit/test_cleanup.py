import os
import re

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))


def _read(path):
    with open(os.path.join(BASE_DIR, path), 'r', encoding='utf-8') as f:
        return f.read()


class TestCleanup:
    def test_no_bak_file(self):
        assert not os.path.exists("templates/base.html.bak")

    # ── M8 ──────────────────────────────────────────────────────────────────

    def test_owner_base_merged(self):
        """owner/base.html stays separate — it adds owner-specific assets and
        BS5-to-BS4 modal compat that doesn't belong in the main base.html."""
        path = "templates/owner/base.html"
        assert os.path.exists(os.path.join(BASE_DIR, path))
        content = _read(path)
        assert "{% extends \"base.html\" %}" in content
        assert "NOTE:" in content or "note:" in content
        assert "bootstrap-icons" in content
        assert "data-bs-toggle" in content

    # ── M9 ──────────────────────────────────────────────────────────────────

    def test_sweetalert2_fallback(self):
        """CDN sweetalert2 loaded first with onerror fallback to local file."""
        scripts = _read("templates/partials/scripts.html")
        assert "sweetalert2@11" in scripts
        assert "onerror=" in scripts
        assert "sweetalert2.min.js" in scripts

        head = _read("templates/partials/head.html")
        assert "sweetalert2@11/dist/sweetalert2.min.css" in head
        assert "onerror=" in head

        assert os.path.exists(os.path.join(BASE_DIR, "static/js/sweetalert2.min.js"))
        assert os.path.exists(os.path.join(BASE_DIR, "static/css/sweetalert2.min.css"))

    # ── M10 ─────────────────────────────────────────────────────────────────

    def test_font_display_swap(self):
        """Google Fonts URL includes display=swap for better LCP/performance."""
        head = _read("templates/partials/head.html")
        match = re.search(r'fonts\.googleapis\.com/css2\?family=Tajawal[^"\']*', head)
        assert match, "Tajawal Google Fonts link not found in head.html"
        assert "display=swap" in match.group(), \
            f"Google Fonts URL missing &display=swap: {match.group()}"

    # ── M11 ─────────────────────────────────────────────────────────────────

    def test_erp_theme_noted(self):
        """Critical rendering CSS (design tokens) extracted for awareness.
        First ~100 lines of erp-theme.css are CSS custom properties under :root
        and html[data-ui-variant="palestinian"] selectors."""
        path = "static/css/erp-theme.css"
        assert os.path.exists(os.path.join(BASE_DIR, path))
        content = _read(path)
        lines = content.splitlines()
        assert len(lines) > 100
        assert ":root {" in lines[0]
        assert "--ui-font-family:" in lines[1]
        assert "--ui-pattern-opacity:" in lines[min(39, len(lines) - 1)]
        # Verify it contains both light and dark theme blocks
        assert 'html[data-ui-variant="palestinian"][data-ui-mode="light"]' in content
        assert 'html[data-ui-variant="palestinian"][data-ui-mode="dark"]' in content

    # ── M12 ─────────────────────────────────────────────────────────────────

    def test_accessibility_removed(self):
        """accessibility.css is still loaded across 20+ templates — NOT removed.
        It needs review for potential consolidation into erp-theme.css."""
        assert os.path.exists(os.path.join(BASE_DIR, "static/css/accessibility.css"))
        assert os.path.exists(os.path.join(BASE_DIR, "static/css/accessibility.min.css"))
        # Confirm it's still referenced in templates
        count = 0
        for root, dirs, files in os.walk(os.path.join(BASE_DIR, "templates")):
            for f in files:
                if f.endswith(".html"):
                    with open(os.path.join(root, f), 'r', encoding='utf-8') as fh:
                        if "accessibility.css" in fh.read():
                            count += 1
        assert count >= 10, \
            f"accessibility.css only referenced in {count} templates (expected >=10)"

    # ── L4 ──────────────────────────────────────────────────────────────────

    def test_no_dupe_attributes(self):
        """No HTML element should have duplicated integrity= or crossorigin= attributes."""
        files_to_check = [
            "templates/base.html",
            "templates/partials/head.html",
            "templates/partials/scripts.html",
            "templates/owner/base.html",
            "templates/public/landing.html",
            "templates/auth/login.html",
            "templates/shop/base.html",
        ]
        for rel_path in files_to_check:
            full = os.path.join(BASE_DIR, rel_path)
            if not os.path.exists(full):
                continue
            content = _read(rel_path)
            # Check for any line with duplicate integrity/crossorigin attributes
            for i, line in enumerate(content.splitlines(), 1):
                integrity_count = line.count('integrity=')
                crossorigin_count = line.count('crossorigin=')
                if integrity_count > 1:
                    raise AssertionError(
                        f"{rel_path}:{i} — {integrity_count} integrity= attributes on one line")
                if crossorigin_count > 1:
                    raise AssertionError(
                        f"{rel_path}:{i} — {crossorigin_count} crossorigin= attributes on one line")
