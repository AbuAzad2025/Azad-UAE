from __future__ import annotations

import ast
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestSeedTranslations:
    """Tests for scripts/seed_translations.py — the Babel catalog seeder."""

    def test_extract_translations_dict(self):
        sys.path.insert(0, os.path.join(ROOT, "scripts"))
        from seed_translations import extract_translations_dict

        d = extract_translations_dict()
        assert isinstance(d, dict)
        assert len(d) > 100
        for key, val in d.items():
            assert isinstance(key, str)
            assert isinstance(val, dict)
            assert "ar" in val
            assert "en" in val

    def test_escape_po_handles_special_chars(self):
        sys.path.insert(0, os.path.join(ROOT, "scripts"))
        from seed_translations import escape_po

        assert escape_po('hello "world"') == r'hello \"world\"'
        assert escape_po("line1\nline2") == 'line1\\n"\n"line2'
        assert escape_po("back\\slash") == "back\\\\slash"

    def test_write_po_creates_valid_file(self, tmp_path):
        sys.path.insert(0, os.path.join(ROOT, "scripts"))
        from seed_translations import write_po

        translations = {
            "Hello": {"ar": "!مرحبا", "en": "Hello"},
            "Back": {"ar": "رجوع", "en": "Back"},
        }
        po_file = tmp_path / "messages.po"
        write_po(str(po_file), "en", translations)
        content = po_file.read_text(encoding="utf-8")
        assert "Language: en" in content
        assert 'msgid "Hello"' in content
        assert 'msgstr "Hello"' in content
        assert 'msgid "Back"' in content
        assert 'msgstr "Back"' in content

    def test_i18n_py_has_translations_dict(self):
        i18n_path = os.path.join(ROOT, "utils", "i18n.py")
        with open(i18n_path, "r", encoding="utf-8") as f:
            source = f.read()
        tree = ast.parse(source)
        found = False
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "TRANSLATIONS":
                        found = True
                        break
        assert found, "TRANSLATIONS dict must exist in utils/i18n.py"

    def test_babel_cfg_exists(self):
        assert os.path.isfile(os.path.join(ROOT, "babel.cfg"))

    def test_translations_dirs_exist(self):
        ar_po = os.path.join(ROOT, "translations", "ar", "LC_MESSAGES", "messages.po")
        en_po = os.path.join(ROOT, "translations", "en", "LC_MESSAGES", "messages.po")
        assert os.path.isfile(ar_po), f"Missing: {ar_po}"
        assert os.path.isfile(en_po), f"Missing: {en_po}"

    def test_mo_files_exist(self):
        ar_mo = os.path.join(ROOT, "translations", "ar", "LC_MESSAGES", "messages.mo")
        en_mo = os.path.join(ROOT, "translations", "en", "LC_MESSAGES", "messages.mo")
        assert os.path.isfile(ar_mo), f"Missing: {ar_mo}"
        assert os.path.isfile(en_mo), f"Missing: {en_mo}"
