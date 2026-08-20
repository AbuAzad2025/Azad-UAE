"""Build static/css/pos-unified.css from pos-layout.css + pos-theme.css + scoped pos_v2.css.

Every rule selector in pos_v2.css is prefixed with `.pos-page--grid ` so the v2
styles only apply on the grid POS page (body carries the pos-page--grid class).
@media wrappers are kept structurally intact; only inner selectors are scoped.
Purgecss ignore markers are left in place around the same rule ranges.
"""
import re

SCOPE = ".pos-page--grid"


def scope_v2(text: str) -> str:
    out = []
    for line in text.split("\r\n"):
        stripped = line.strip()
        if (
            stripped.endswith("{")
            and not stripped.startswith("@")
            and not stripped.startswith("/*")
        ):
            indent = line[: len(line) - len(line.lstrip())]
            selectors = [s.strip() for s in stripped[:-1].split(",")]
            scoped = ", ".join(f"{SCOPE} {s}" for s in selectors if s)
            out.append(f"{indent}{scoped} {{")
        else:
            out.append(line)
    return "\r\n".join(out)


def banner(title: str) -> str:
    return (
        "/* ==========================================================================\r\n"
        f"   {title}\r\n"
        "   ========================================================================== */\r\n"
    )


def main():
    layout = open("static/css/_archive/pos-layout.css", encoding="utf-8", newline="").read()
    theme = open("static/css/_archive/pos-theme.css", encoding="utf-8", newline="").read()
    v2 = open("static/css/_archive/pos_v2.css", encoding="utf-8", newline="").read()

    scoped_v2 = scope_v2(v2)

    unified = (
        "/* Azadexa POS unified stylesheet.\r\n"
        "   Consolidates pos-layout.css + pos-theme.css + pos_v2.css (archived in\r\n"
        "   static/css/_archive/). The v2 section is scoped under .pos-page--grid\r\n"
        "   (body class on the grid terminal page) because pos-theme.css and\r\n"
        "   pos_v2.css style the same class names differently per page. */\r\n"
        "\r\n"
        + banner("Section 1/3: pos-layout (base POS layout, all POS pages)")
        + layout.strip()
        + "\r\n\r\n"
        + banner("Section 2/3: pos-theme (list terminal: pos/index, pos/held_carts)")
        + theme.strip()
        + "\r\n\r\n"
        + banner("Section 3/3: pos_v2 (grid terminal) - scoped under .pos-page--grid")
        + scoped_v2.strip()
        + "\r\n"
    )

    with open("static/css/pos-unified.css", "w", encoding="utf-8", newline="") as f:
        f.write(unified)

    # sanity: brace balance + scope coverage
    body = re.sub(r"/\*.*?\*/", "", unified, flags=re.S)
    print(f"unified braces: open={body.count('{')} close={body.count('}')}")
    v2_scoped_count = scoped_v2.count(SCOPE + " ")
    print(f"v2 rules scoped with '{SCOPE}': {v2_scoped_count}")
    # ensure no unscoped selector lines remain in v2 section
    unscoped = []
    for line in scoped_v2.split("\r\n"):
        s = line.strip()
        if s.endswith("{") and not s.startswith("@") and not s.startswith("/*") and SCOPE not in s:
            unscoped.append(s)
    print(f"unscoped v2 selector lines: {len(unscoped)}")
    for u in unscoped:
        print(f"  !! {u}")


if __name__ == "__main__":
    main()
