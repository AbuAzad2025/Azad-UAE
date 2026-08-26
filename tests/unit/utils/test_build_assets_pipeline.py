"""utils/build_assets.py — full pipeline behavior with real temp directories.

Covers the no-minifier fallback (copy + hash naming), the minified path
(content-addressed .min artifacts + gzip), collection rules, and build_all's
aggregation/summary output.
"""

from __future__ import annotations

import gzip
import hashlib
import os
import sys

from utils.build_assets import _collect_files, _gzip_file, _process_file, build_all


def _digest_of(content: bytes) -> str:
    return hashlib.md5(content, usedforsecurity=False).hexdigest()[:12]


def _read(path: str) -> bytes:
    with open(path, "rb") as f:
        return f.read()


class TestProcessFileFallbackCopy:
    """When no minifier is importable the ORIGINAL is copied verbatim."""

    def test_js_fallback_copies_original_and_hashes_content(self, tmp_path, monkeypatch):
        monkeypatch.setitem(sys.modules, "jsmin", None)
        src = tmp_path / "widget.js"
        original = b"var x = 1;\nfunction go() { return x; }\n"
        src.write_bytes(original)

        info = _process_file(str(src))

        assert info is not None
        assert info["file"] == "widget.js"
        assert info["original"] == len(original)
        # No minifier -> "minified" size equals the original byte length.
        assert info["minified"] == len(original)
        expected_digest = _digest_of(original)
        assert info["hash"] == expected_digest

        min_file = tmp_path / "widget.min.js"
        hashed_file = tmp_path / f"widget.{expected_digest}.min.js"
        gz_file = tmp_path / f"widget.{expected_digest}.min.js.gz"
        assert min_file.read_bytes() == original
        assert hashed_file.read_bytes() == original
        assert os.path.getsize(str(gz_file)) == info["gzipped"]
        with gzip.open(str(gz_file), "rb") as gz:
            assert gz.read() == original

    def test_css_fallback_copies_original(self, tmp_path, monkeypatch):
        monkeypatch.setitem(sys.modules, "cssmin", None)
        monkeypatch.setitem(sys.modules, "rcssmin", None)
        src = tmp_path / "theme.css"
        original = b"body { color: red; }\n"
        src.write_bytes(original)

        info = _process_file(str(src))
        digest = _digest_of(original)
        assert info["hash"] == digest
        assert (tmp_path / f"theme.{digest}.min.css").read_bytes() == original


class TestProcessFileMinified:
    def test_js_minified_artifacts_match_minifier_output(self, tmp_path):
        src = tmp_path / "app.js"
        source_text = "var a = 1;\nvar b = 2;\n"
        src.write_text(source_text, encoding="utf-8")

        info = _process_file(str(src))

        import jsmin

        expected = jsmin.jsmin(source_text).encode("utf-8")
        digest = _digest_of(expected)
        assert info["hash"] == digest
        assert info["original"] == len(source_text.encode("utf-8"))
        assert info["minified"] == len(expected)
        hashed_file = tmp_path / f"app.{digest}.min.js"
        assert hashed_file.exists()
        assert hashed_file.read_bytes() == expected
        plain_min = tmp_path / "app.min.js"
        assert plain_min.read_bytes() == expected

    def test_css_minified_artifact(self, tmp_path):
        src = tmp_path / "site.css"
        src.write_text("body {\n  color: hotpink;\n}\n", encoding="utf-8")

        info = _process_file(str(src))
        hashed_files = [p for p in os.listdir(tmp_path) if p.endswith(".min.css.gz")]
        assert hashed_files, "gzipped hashed artifact must exist"
        assert info["gzipped"] > 0


class TestCollectFiles:
    def test_extension_filter_sort_order_and_min_skip(self, tmp_path):
        js_dir = tmp_path / "static" / "js"
        css_dir = tmp_path / "static" / "css"
        js_dir.mkdir(parents=True)
        css_dir.mkdir(parents=True)
        for name in ("zeta.js", "alpha.js", "alpha.min.js", "notes.txt"):
            (js_dir / name).write_text("// x", encoding="utf-8")
        for name in ("beta.css", "beta.min.css"):
            (css_dir / name).write_text("a{}", encoding="utf-8")

        js_files = _collect_files(str(tmp_path), os.path.join("static", "js"), (".js",))
        css_files = _collect_files(str(tmp_path), os.path.join("static", "css"), (".css",))

        assert [os.path.basename(p) for p in js_files] == ["alpha.js", "zeta.js"]
        assert [os.path.basename(p) for p in css_files] == ["beta.css"]

    def test_missing_directory_returns_empty(self, tmp_path):
        assert _collect_files(str(tmp_path), "does_not_exist", (".js",)) == []


class TestGzipFile:
    def test_roundtrip_preserves_bytes(self, tmp_path):
        src = tmp_path / "data.js"
        payload = b"console.log('hello');\n"
        src.write_bytes(payload)

        gz_path = _gzip_file(str(src))

        assert gz_path.endswith(".gz")
        with gzip.open(gz_path, "rb") as gz:
            assert gz.read() == payload


class TestBuildAllEndToEnd:
    def test_processes_js_and_css_and_prints_summary(self, tmp_path, capsys):
        js_dir = tmp_path / "static" / "js"
        css_dir = tmp_path / "static" / "css"
        js_dir.mkdir(parents=True)
        css_dir.mkdir(parents=True)
        js_body = "var one = 1;\nvar two = 2;\nvar three = 3;\n"
        css_body = ".card {\n  border-radius: 4px;\n  color: #333333;\n}\n"
        (js_dir / "bundle.js").write_text(js_body, encoding="utf-8")
        (css_dir / "bundle.css").write_text(css_body, encoding="utf-8")

        results = build_all(str(tmp_path))

        assert [r["file"] for r in results] == ["bundle.js", "bundle.css"]
        total_orig = sum(r["original"] for r in results)
        assert total_orig == len(js_body.encode()) + len(css_body.encode())

        out = capsys.readouterr().out
        assert "Processed 2 files" in out
        assert "JS bundle.js" in out
        assert "CSS bundle.css" in out
        assert "Saved:" in out

    def test_base_without_static_dirs_reports_zero_totals(self, tmp_path, capsys):
        results = build_all(str(tmp_path))
        assert results == []
        out = capsys.readouterr().out
        assert "Processed 0 files" in out
        assert "(0.0%)" in out
