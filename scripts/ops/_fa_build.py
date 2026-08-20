"""Build FontAwesome subset: subset fonts + regenerate all.min.css.

Inputs:  scripts/ops/_fa_used.json (from _fa_scan.py)
Outputs: overwrites static/adminlte/plugins/fontawesome/webfonts/* and css/all.min.css
         (originals already backed up in _original/)
"""

import json
import os
import re
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
FA_DIR = os.path.join(ROOT, "static", "adminlte", "plugins", "fontawesome")
ORIG_CSS = os.path.join(FA_DIR, "_original", "css", "all.min.css")
ORIG_FONTS = os.path.join(FA_DIR, "_original", "webfonts")
OUT_CSS = os.path.join(FA_DIR, "css", "all.min.css")
OUT_FONTS = os.path.join(FA_DIR, "webfonts")

# Extra icons: resolved from dynamic Jinja (fa-chevron-{{...}}) and a safety
# set for the free-text StorePaymentMethod.icon DB field (payment/brand icons).
EXTRA_ICONS = [
    "fa-chevron-left",
    "fa-chevron-right",
    "fa-cc-amex",
    "fa-cc-paypal",
    "fa-cc-stripe",
    "fa-cc-apple-pay",
    "fa-apple-pay",
    "fa-google-pay",
    "fa-money-bill-transfer",
    "fa-building-columns",
    "fa-mobile-screen",
    "fa-bank",
]

FAMILIES = {
    "fa-solid-900": ["fa-solid-900.ttf", "fa-solid-900.woff2"],
    "fa-regular-400": ["fa-regular-400.ttf", "fa-regular-400.woff2"],
    "fa-brands-400": ["fa-brands-400.ttf", "fa-brands-400.woff2"],
}

ICON_BLOCK_RE = re.compile(r"((?:\.fa-[a-z0-9-]+:before\s*,?\s*)+)\{\s*content:\s*\"\\[0-9a-f]{2,4}\";\s*\}")
SEL_RE = re.compile(r"\.(fa-[a-z0-9-]+):before")
CONTENT_RE = re.compile(r'content:\s*"\\([0-9a-f]{2,4})"')


def parse_icon_blocks(css_text):
    """Yield (full_match, [class names], codepoint) for each icon rule block."""
    for m in ICON_BLOCK_RE.finditer(css_text):
        names = SEL_RE.findall(m.group(1))
        code = CONTENT_RE.search(m.group(0)).group(1)
        yield m.group(0), names, code


def main():
    with open(os.path.join(ROOT, "scripts", "ops", "_fa_used.json")) as f:
        report = json.load(f)
    used = set(report["used_icons"])

    with open(ORIG_CSS, encoding="utf-8") as f:
        css_text = f.read()
    defined = {}
    for _block, names, code in parse_icon_blocks(css_text):
        for n in names:
            defined[n] = code

    extras = [n for n in EXTRA_ICONS if n in defined and n not in used]
    keep = sorted(used | set(extras))
    print(f"used: {len(used)}  extras added: {len(extras)}  total kept: {len(keep)}")

    # Map kept class -> codepoint; collect codepoints
    keep_set = set(keep)
    codepoints = sorted({defined[n] for n in keep}, key=lambda c: int(c, 16))
    print(f"unique codepoints: {len(codepoints)}")

    # --- determine family coverage via font cmaps ---
    from fontTools.ttLib import TTFont

    family_cps = {}
    for fam, files in FAMILIES.items():
        font = TTFont(os.path.join(ORIG_FONTS, files[0]))
        cmap = font.getBestCmap()
        font.close()
        cps = [cp for cp in codepoints if int(cp, 16) in cmap]
        family_cps[fam] = cps
        print(f"{fam}: {len(cps)} codepoints")

    uncovered = [cp for cp in codepoints if not any(cp in family_cps[f] for f in FAMILIES)]
    if uncovered:
        names = [n for n in keep if defined[n] in uncovered]
        print(f"WARNING codepoints not in any free font cmap: {uncovered} ({names})")

    # --- subset fonts ---
    for fam, files in FAMILIES.items():
        cps = family_cps[fam]
        if not cps:
            print(f"{fam}: no used icons, keeping original font files")
            continue
        unicodes = ",".join(f"U+{int(cp, 16):04X}" for cp in cps)
        src = os.path.join(ORIG_FONTS, files[0])
        for out_name in files:
            out_path = os.path.join(OUT_FONTS, out_name)
            # In-process equivalent of pyftsubset (fontTools.subset CLI) —
            # avoids spawning a subprocess (repo policy: subprocess only via
            # utils/secure_subprocess.py).
            from fontTools import subset as ft_subset

            argv = [
                src,
                f"--output-file={out_path}",
                f"--unicodes={unicodes}",
                "--layout-features=*",
                "--glyph-names",
                "--recommended-glyphs",
            ]
            if out_name.endswith(".woff2"):
                argv.append("--flavor=woff2")
            # fontTools.subset.main returns None on success and raises on
            # failure — verify via the output file instead of a return code.
            ft_subset.main(argv)
            if not os.path.exists(out_path):
                raise RuntimeError(f"fontTools subset produced no output for {out_name}")
            print(f"wrote {out_name} ({os.path.getsize(out_path)} bytes)")

    # --- regenerate css: keep everything except unused icon rules ---
    def replace_block(m):
        names = SEL_RE.findall(m.group(1))
        kept_names = [n for n in names if n in keep_set]
        if not kept_names:
            return ""
        if len(kept_names) == len(names):
            return m.group(0)
        sels = ",\n".join(f".{n}:before" for n in kept_names)
        code = CONTENT_RE.search(m.group(0)).group(1)
        return f'{sels} {{\n\tcontent: "\\{code}";\n}}'

    new_css = ICON_BLOCK_RE.sub(replace_block, css_text)
    header = (
        "/* FontAwesome subset generated 2026-08: "
        f"{len(keep)} icon classes kept (of {len(defined)} defined). "
        "Originals in _original/. */\n"
    )
    # insert after the leading license comment
    end_license = new_css.find("*/") + 2
    new_css = new_css[:end_license] + "\n" + header + new_css[end_license:].lstrip("\n")
    with open(OUT_CSS, "w", encoding="utf-8", newline="\n") as f:
        f.write(new_css)
    print(f"wrote {OUT_CSS} ({os.path.getsize(OUT_CSS)} bytes)")

    # --- verification ---
    errors = []
    if new_css.count("{") != new_css.count("}"):
        errors.append(f"brace imbalance: {{={new_css.count('{')} }}={new_css.count('}')}")
    new_defined = set(re.findall(r"\.(fa-[a-z0-9-]+):before", new_css))
    missing_icons = [n for n in keep if n not in new_defined]
    if missing_icons:
        errors.append(f"kept icons missing from new css: {missing_icons}")

    for fam, files in FAMILIES.items():
        cps = family_cps[fam]
        if not cps:
            continue
        for out_name in files:
            font = TTFont(os.path.join(OUT_FONTS, out_name))
            cmap = font.getBestCmap()
            font.close()
            missing_cp = [cp for cp in cps if int(cp, 16) not in cmap]
            if missing_cp:
                errors.append(f"{out_name} missing codepoints: {missing_cp}")

    if errors:
        print("VERIFICATION FAILED:")
        for e in errors:
            print(" -", e)
        sys.exit(1)
    print("VERIFICATION OK: css braces balanced, all kept icons present, all codepoints present in subset fonts.")


if __name__ == "__main__":
    main()
