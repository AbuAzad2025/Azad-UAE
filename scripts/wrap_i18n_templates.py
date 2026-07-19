#!/usr/bin/env python3
"""Wrap bare Arabic text and user-facing attributes in templates with {{ _('...') }}.

Phase-safe. Structural (html.parser-based) tokenizer that emits the ORIGINAL
source verbatim except for precisely the spans it wraps -- so diffs stay minimal
and HTML/Jinja structure is never corrupted.

Rules:
  - Skip everything inside <script> and <style> (verbatim passthrough).
  - Skip text already containing Jinja ({{...}} / {%...%} / {#...#}).
  - Wrap pure-Arabic text segments -> {{ _('...') }}.
  - Wrap placeholder/title/alt attribute values containing Arabic ->
    placeholder="{{ _('...') }}".
  - Never touch already-wrapped content.
"""

import argparse
import os
import re
from html.parser import HTMLParser

REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))

RTL_SEQ = re.compile(
    r"[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]{2,}"
)
JINJA = re.compile(r"\{[{%#].*?[}%#]\}")
# Attributes that are NEVER user-facing text -> never wrapped even if Arabic.
ATTR_DENYLIST = {
    "id",
    "class",
    "name",
    "type",
    "value",
    "href",
    "src",
    "action",
    "method",
    "rel",
    "target",
    "style",
    "onclick",
    "onchange",
    "oninput",
    "onfocus",
    "onblur",
    "onsubmit",
    "for",
    "method",
    "enctype",
    "step",
    "min",
    "max",
    "minlength",
    "maxlength",
    "pattern",
    "required",
    "readonly",
    "disabled",
    "checked",
    "selected",
    "multiple",
    "autocomplete",
    "novalidate",
    "form",
    "colspan",
    "rowspan",
    "scope",
    "lang",
    "dir",
    "width",
    "height",
    "viewbox",
    "fill",
    "stroke",
    "d",
    "xmlns",
    "data",
    "aria-hidden",
    "role",
}
SKIP_TAGS = {"script", "style"}

WRAP_OPEN = "{{ _('"
WRAP_CLOSE = "') }}"

# split a text node into (literal, is_arabic) segments, preserving order
_token_re = re.compile(
    r"([\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF][^\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]*[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]|[^\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]+)"
)


def _already_wrapped(s):
    return bool(re.search(r"\{\{?\s*_\s*\(", s)) or "{{ t(" in s or "{{ gettext" in s


def _escape(s):
    # inside single-quoted Jinja string
    return s.replace("\\", "\\\\").replace("'", "\\'")


# Split a text node into segments; wrap only the non-Jinja segments that
# contain Arabic. Jinja expressions ({{...}} / {%...%} / {#...#}) are left
# untouched and act as boundaries.
def wrap_text(text):
    if not text or not RTL_SEQ.search(text):
        return text
    if _already_wrapped(text):
        return text
    # Safety: never touch a text node that contains any Jinja markup
    # ({{ }}, {% %}, {# #}). Wrapping such a node would nest translation
    # calls inside Jinja expressions and corrupt the template. Leave those
    # for manual handling; the linter already skips {{ }} expression spans.
    if JINJA.search(text):
        return text
    return _wrap_segment(text)


def _wrap_segment(seg):
    """Wrap a pure-text segment (no Jinja) if it contains Arabic."""
    if not seg or not RTL_SEQ.search(seg):
        return seg
    lead = seg[: len(seg) - len(seg.lstrip())]
    trail = seg[len(seg.rstrip()) :]
    inner = seg.strip()
    if not inner:
        return seg
    return f"{lead}{WRAP_OPEN}{_escape(inner)}{WRAP_CLOSE}{trail}"


class Wrapper(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.out = []
        self.skip_depth = 0  # >0 when inside script/style
        self.skip_tag = None
        self.in_jinja_block = False  # inside {% set %} / {% macro %} / etc.

    def _jinja_block_state(self, data):
        """Update multi-line {% set %}/{% macro %}/{% call %}/{% filter %}
        block tracking based on ``data``. Returns True if ``data`` lies inside
        such a block and must be left untouched."""
        # open
        m = re.search(r"\{\%\s*(set|macro|call|filter)\b", data)
        if m and not re.search(r"\{\%\s*end" + m.group(1) + r"\b", data):
            self.in_jinja_block = True
        elif re.search(r"\{\%\s*end(set|macro|call|filter)\b", data):
            self.in_jinja_block = False
        return self.in_jinja_block

    def handle_starttag(self, tag, attrs):
        if tag in SKIP_TAGS:
            self.skip_depth += 1
            self.skip_tag = tag
        if self.skip_depth:
            self.out.append(self.get_starttag_text())
            return
        self.out.append(self._rewrite_attrs(self.get_starttag_text(), attrs, False))

    def handle_startendtag(self, tag, attrs):
        if tag in SKIP_TAGS:
            self.out.append(self.get_starttag_text())
            return
        self.out.append(self._rewrite_attrs(self.get_starttag_text(), attrs, True))

    def handle_endtag(self, tag):
        if self.skip_depth and tag == self.skip_tag:
            self.skip_depth -= 1
            if self.skip_depth == 0:
                self.skip_tag = None
        self.out.append(f"</{tag}>")

    def handle_data(self, data):
        if self.skip_depth:
            self.out.append(data)
            return
        # Track {% set %} / {% macro %} etc. blocks and leave their bodies
        # (code/data definitions with escaped-quote literals) untouched.
        if self._jinja_block_state(data):
            self.out.append(data)
            return
        self.out.append(wrap_text(data))

    def handle_entityref(self, name):
        self.out.append(f"&{name};")

    def handle_charref(self, name):
        self.out.append(f"&#{name};")

    def handle_comment(self, data):
        self.out.append(f"<!--{data}-->")

    def handle_decl(self, decl):
        self.out.append(f"<!{decl}>")

    def handle_pi(self, data):
        self.out.append(f"<?{data}>")

    def unknown_decl(self, data):
        self.out.append(f"<![{data}]>")

    # ---- tag reconstruction (surgical, preserves original formatting) ----
    def _rewrite_attrs(self, raw_tag, attrs, self_closing):
        result = raw_tag
        # attrs come in document order; rewrite each user-facing attr in the raw tag
        for k, v in attrs:
            if k.lower() in ATTR_DENYLIST:
                continue
            if v and RTL_SEQ.search(v) and not _already_wrapped(v):
                # match the exact attribute occurrence in the raw tag text
                pat = re.compile(
                    r"(\s" + re.escape(k) + r'\s*=\s*)(["\'])(.*?)(\2)', re.DOTALL
                )

                def _sub(m):
                    return f"{m.group(1)}\"{{{{ _('{_escape(v)}') }}}}\""

                result = pat.sub(_sub, result, count=1)
        return result


def transform(path):
    with open(path, "r", encoding="utf-8") as f:
        raw = f.read()
    p = Wrapper()
    p.feed(raw)
    return "".join(p.out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--files", nargs="*")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    if args.files:
        targets = [
            f if os.path.isabs(f) else os.path.join(REPO_ROOT, f) for f in args.files
        ]
    else:
        targets = []
        for root, dirs, files in os.walk(os.path.join(REPO_ROOT, "templates")):
            dirs[:] = [d for d in dirs if d not in {".venv", "node_modules", "static"}]
            for fn in files:
                if fn.endswith(".html"):
                    targets.append(os.path.join(root, fn))

    n = 0
    for p in targets:
        original = open(p, encoding="utf-8").read()
        new = transform(p)
        if new != original:
            n += 1
            rel = os.path.relpath(p, REPO_ROOT)
            if args.apply:
                with open(p, "w", encoding="utf-8") as f:
                    f.write(new)
                print(f"WROTE {rel}")
            else:
                print(f"DRY   {rel}")
    print(f"\n{n} file(s) changed.")


if __name__ == "__main__":
    main()
