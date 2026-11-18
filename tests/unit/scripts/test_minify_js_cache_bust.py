"""The JS build must cache-bust every relative module import, not just entrypoints.

``dist_url()`` hashes only the top-level script (``js/dist/pos/index.js``). A
browser caches each ES module by its own URL, so an unhashed ``./cart.js``
import kept serving the pre-fix cart forever: the POS totals stayed at 0.00
after a deployment even though the source was corrected.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
BUILD_SCRIPT = REPO / "scripts" / "build" / "minify-js.js"


def test_relative_module_imports_carry_a_content_hash(tmp_path: Path) -> None:
    build_dir = tmp_path / "scripts" / "build"
    build_dir.mkdir(parents=True)
    shutil.copy(BUILD_SCRIPT, build_dir / "minify-js.js")

    src_dir = tmp_path / "static" / "js" / "pos"
    src_dir.mkdir(parents=True)
    (src_dir / "dep.js").write_text("export const v = 1;\n", encoding="utf-8")
    (src_dir / "main.js").write_text('import { v } from "./dep.js"; console.log(v);\n', encoding="utf-8")

    env = os.environ.copy()
    env["NODE_PATH"] = str(REPO / "node_modules")
    subprocess.run(["node", str(build_dir / "minify-js.js")], check=True, env=env, capture_output=True)

    dist_dir = tmp_path / "static" / "js" / "dist" / "pos"
    dep = (dist_dir / "dep.js").read_bytes()
    main = (dist_dir / "main.js").read_text(encoding="utf-8")
    digest = hashlib.sha256(dep).hexdigest()[:12]
    assert f"dep.js?v={digest}" in main


def test_hash_changes_when_a_dependency_changes(tmp_path: Path) -> None:
    build_dir = tmp_path / "scripts" / "build"
    build_dir.mkdir(parents=True)
    shutil.copy(BUILD_SCRIPT, build_dir / "minify-js.js")
    src_dir = tmp_path / "static" / "js" / "pos"
    src_dir.mkdir(parents=True)
    (src_dir / "dep.js").write_text("export const v = 1;\n", encoding="utf-8")
    (src_dir / "main.js").write_text('import { v } from "./dep.js"; console.log(v);\n', encoding="utf-8")

    env = os.environ.copy()
    env["NODE_PATH"] = str(REPO / "node_modules")

    def build() -> str:
        subprocess.run(["node", str(build_dir / "minify-js.js")], check=True, env=env, capture_output=True)
        return (tmp_path / "static" / "js" / "dist" / "pos" / "main.js").read_text(encoding="utf-8")

    first = build()
    (src_dir / "dep.js").write_text("export const v = 2;\n", encoding="utf-8")
    second = build()
    assert first != second
