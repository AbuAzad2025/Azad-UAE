"""i18n catalogue parity + source-encoding gates.

The strict-i18n lint only proves that a string is *wrapped* in a lookup call. It
cannot tell that the key actually exists, so a wrapped-but-unknown key silently
renders as the raw key to the user (e.g. ``AI_Training_Batches`` on the owner
page). This module closes that hole and is the executable form of the
"zero hardcoded strings / 100% bilingual parity" requirement:

1. ``test_every_template_key_exists_in_catalogue`` — every ``t()`` / ``_()`` key
   used in a template must resolve in ``utils.i18n.TRANSLATIONS`` for both Arabic
   and English.
2. ``test_python_gettext_keys_exist`` — same for route/service flash + error text.
3. ``test_catalogue_entries_have_both_languages`` — no half-translated entry.
4. ``test_no_mojibake_in_source`` — UTF-8 round-trip damage (a stored em dash as
   ``â\\x80\\x94``, a stray U+FFFD) is a hard failure, not a cosmetic issue.
5. ``test_no_merged_period_keys`` — a lookup key must not smuggle a sentence
   together with a translated fragment (the ``'/month — for X'`` class of bug).
"""

from __future__ import annotations

import pathlib
import re

import pytest

from utils.i18n import TRANSLATIONS

ROOT = pathlib.Path(__file__).resolve().parents[3]
TEMPLATES = ROOT / "templates"

# t()/_( )/gettext() with a single-quoted literal, tolerant of multi-line calls
_CALL = re.compile(r"\b(?:t|gettext|_)\(\s*'((?:[^'\\]|\\.)*)'\s*(?=[,)])", re.S)
_SCAN_SUFFIXES = {".html"}
_MOJIBAKE = ("â", "Ã©", "Ã¨", "Ã¡", "Â ", "�")


def _iter_call_keys(root: pathlib.Path, suffixes: set[str]):
    for path in sorted(root.rglob("*")):
        if path.suffix.lower() not in suffixes or not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for key in _CALL.findall(text):
            yield path, key.replace("\\'", "'")


def _template_keys():
    seen: dict[str, set[str]] = {}
    for path, key in _iter_call_keys(TEMPLATES, _SCAN_SUFFIXES):
        if len(key) >= 2:
            seen.setdefault(key, set()).add(path.relative_to(ROOT).as_posix())
    return seen


def _python_keys():
    seen: dict[str, set[str]] = {}
    for base in ("routes", "services", "utils", "models"):
        root = ROOT / base
        if not root.exists():
            continue
        for path, key in _iter_call_keys(root, {".py"}):
            if len(key) >= 2:
                seen.setdefault(key, set()).add(path.relative_to(ROOT).as_posix())
    return seen


def _po_msgids() -> set[str]:
    """msgids present in the Babel catalogs.

    The project uses a hybrid scheme: ``utils.i18n.TRANSLATIONS`` maps English
    keys to ar/en, while the ``.po`` catalogs also carry ~2.2k Arabic msgids
    translated into English. A Python ``gettext('...')`` call is therefore valid
    when the key resolves in *either* store, and the gate must not demand a
    refactor of correctly-translated Arabic msgids.

    Parsed with Babel rather than a regex: long msgids are stored across several
    quoted continuation lines and a line-based regex silently misses them.
    """
    from babel.messages.pofile import read_po

    msgids: set[str] = set()
    for lang in ("ar", "en"):
        po = ROOT / "translations" / lang / "LC_MESSAGES" / "messages.po"
        if not po.exists():
            continue
        with po.open("rb") as fh:
            for message in read_po(fh):
                if message.id:
                    msgids.add(message.id)
    return msgids


TEMPLATE_KEYS = _template_keys()
PYTHON_KEYS = _python_keys()
_PO_MSGIDS = _po_msgids()
# `_()` / `t()` resolve through Babel first and fall back to the dict, and
# `gettext()` resolves through Babel only. A key is therefore valid when it
# resolves in either store.
_RESOLVABLE = set(TRANSLATIONS) | _PO_MSGIDS
_MISSING_TEMPLATES = sorted(k for k in TEMPLATE_KEYS if k not in _RESOLVABLE)
_MISSING_PYTHON = sorted(k for k in PYTHON_KEYS if k not in _RESOLVABLE)


def test_extraction_is_not_empty() -> None:
    """Guard against a vacuous pass if the scanner regex ever stops matching."""
    assert len(TEMPLATE_KEYS) > 1000, len(TEMPLATE_KEYS)
    assert len(TRANSLATIONS) > 1000, len(TRANSLATIONS)


def test_catalogue_has_no_missing_keys() -> None:
    assert _MISSING_TEMPLATES == [], (
        f"{len(_MISSING_TEMPLATES)} template key(s) render as the raw key; add ar+en to "
        f"utils/i18n.py: {_MISSING_TEMPLATES[:25]}"
    )


def test_python_keys_exist() -> None:
    assert _MISSING_PYTHON == [], (
        f"{len(_MISSING_PYTHON)} Python gettext key(s) missing from the catalogue: {_MISSING_PYTHON[:25]}"
    )


def test_catalogue_entries_have_both_languages() -> None:
    incomplete = sorted(k for k, v in TRANSLATIONS.items() if not isinstance(v, dict) or not {"ar", "en"} <= set(v))
    assert incomplete == [], f"{len(incomplete)} catalogue entries lack ar/en: {incomplete[:25]}"


@pytest.mark.parametrize("base", ["templates", "routes", "services", "utils", "models", "static/js"])
def test_no_mojibake_in_source(base: str) -> None:
    root = ROOT / base
    if not root.exists():
        pytest.skip(f"{base} not present")
    offenders: list[str] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in {".html", ".py", ".js", ".css", ".json"}:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if any(m in text for m in _MOJIBAKE):
            offenders.append(f"{path.relative_to(ROOT).as_posix()} ({sum(text.count(m) for m in _MOJIBAKE)})")
    assert offenders == [], f"double-encoded UTF-8 found: {offenders[:20]}"


# Fragments that are translated on their own; a key that bolts a sentence onto
# one of them (e.g. "/month — for growing businesses") can never resolve.
_FRAGMENT_PREFIXES = ("/month", "/year", "/mo", "/yr")


def test_no_merged_period_keys() -> None:
    """A lookup key must not merge an already-translated fragment with a sentence."""
    bad = sorted(k for k in TEMPLATE_KEYS if k.lower().startswith(_FRAGMENT_PREFIXES) and len(k) > 12)
    assert bad == [], f"keys merge translated fragments with sentences: {bad[:20]}"
