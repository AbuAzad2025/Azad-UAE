"""Parse pos-theme.css and pos_v2.css for top-level selectors and report conflicts."""

import re
import sys


def strip_comments(text: str) -> str:
    return re.sub(r"/\*.*?\*/", "", text, flags=re.S)


def parse_rules(path: str):
    """Return dict: selector-string -> list of normalized rule bodies.

    Handles @media blocks by tracking context; nested rules are flattened
    with their media context prefixed.
    """
    with open(path, encoding="utf-8") as f:
        text = strip_comments(f.read())
    rules: dict[tuple[tuple[str, ...], str], list[str]] = {}
    n = len(text)

    def read_block(pos):
        """pos points at '{'. Return (content, newpos after matching '}')."""
        depth = 0
        start = pos
        while pos < n:
            c = text[pos]
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    return text[start + 1 : pos], pos + 1
            pos += 1
        raise ValueError(f"unbalanced braces in {path}")

    def process(pos, context):
        """Parse a chunk; return position where this level ends."""
        while pos < n:
            # read up to next { or }
            m = re.search(r"[{}]", text[pos:])
            if not m:
                return n
            j = pos + m.start()
            prelude = text[pos:j].strip()
            if text[j] == "}":
                return j + 1
            # it's '{'
            body, endpos = read_block(j)
            if prelude.startswith("@"):
                # at-rule: recurse into body with context
                inner_end = process_at(body, context + [prelude], f"{path}@{j}")
                _ = inner_end
            else:
                for sel in split_selectors(prelude):
                    norm_body = normalize_body(body)
                    key = (tuple(context), sel)
                    rules.setdefault(key, []).append(norm_body)
            pos = endpos
        return pos

    def process_at(body, context, tag):
        # parse the body string as its own mini-document
        return _process_body(body, context)

    def _process_body(body, context):
        pos = 0
        bn = len(body)
        while pos < bn:
            m = re.search(r"[{}]", body[pos:])
            if not m:
                return bn
            j = pos + m.start()
            prelude = body[pos:j].strip()
            if body[j] == "}":
                return j + 1
            # find matching brace within body
            depth = 0
            k = j
            while k < bn:
                if body[k] == "{":
                    depth += 1
                elif body[k] == "}":
                    depth -= 1
                    if depth == 0:
                        break
                k += 1
            inner = body[j + 1 : k]
            if prelude.startswith("@"):
                _process_body(inner, context + [prelude])
            elif prelude:
                for sel in split_selectors(prelude):
                    rules.setdefault((tuple(context), sel), []).append(normalize_body(inner))
            pos = k + 1
        return pos

    _process_body(text, [])
    return rules


def split_selectors(prelude: str):
    # drop trailing/leading junk; split on commas not inside parens
    parts = []
    depth = 0
    cur = ""
    for ch in prelude:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append(cur.strip())
            cur = ""
        else:
            cur += ch
    if cur.strip():
        parts.append(cur.strip())
    return [re.sub(r"\s+", " ", p) for p in parts if p]


def normalize_body(body: str) -> str:
    # strip whitespace and sort declarations for order-insensitive compare
    decls = [d.strip() for d in body.split(";") if d.strip()]
    decls = [re.sub(r"\s+", " ", d) for d in decls]
    return "\n".join(sorted(decls))


def main():
    theme = parse_rules("static/css/_archive/pos-theme.css")
    v2 = parse_rules("static/css/_archive/pos_v2.css")

    theme_sels = {sel for (_ctx, sel) in theme}
    v2_sels = {sel for (_ctx, sel) in v2}
    shared = theme_sels & v2_sels

    print(f"pos-theme.css: {len(theme_sels)} unique selectors, {len(theme)} rules")
    print(f"pos_v2.css:    {len(v2_sels)} unique selectors, {len(v2)} rules")
    print(f"shared selectors: {len(shared)}")
    print()

    conflicts = []
    identical = []
    for sel in sorted(shared):
        # compare across ALL contexts where the selector appears
        theme_bodies = sorted({b for (ctx, s), bodies in theme.items() if s == sel for b in bodies})
        v2_bodies = sorted({b for (ctx, s), bodies in v2.items() if s == sel for b in bodies})
        if theme_bodies == v2_bodies:
            identical.append(sel)
        else:
            conflicts.append((sel, theme_bodies, v2_bodies))

    print(f"identical shared: {len(identical)}")
    for s in identical:
        print(f"  == {s}")
    print()
    print(f"CONFLICTING shared: {len(conflicts)}")
    for sel, tb, vb in conflicts:
        print(f"\n### {sel}")
        print("  pos-theme.css:")
        for b in tb:
            for line in b.split("\n"):
                print(f"    {line}")
        print("  pos_v2.css:")
        for b in vb:
            for line in b.split("\n"):
                print(f"    {line}")

    # brace balance sanity
    for path in (
        "static/css/_archive/pos-theme.css",
        "static/css/_archive/pos_v2.css",
        "static/css/_archive/pos-layout.css",
    ):
        raw = strip_comments(open(path, encoding="utf-8").read())
        print(f"\n{path}: open={raw.count('{')} close={raw.count('}')}")


if __name__ == "__main__":
    sys.exit(main())
