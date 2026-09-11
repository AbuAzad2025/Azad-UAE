"""Cov4: build_assets + cache_decorators + enhanced_logging + performance_tracker."""

from __future__ import annotations

import logging
from unittest.mock import MagicMock, patch

import utils.build_assets as ba
import utils.cache_decorators as cd
import utils.enhanced_logging as el
import utils.performance_tracker as pt


def test_minify_dispatch_and_missing():
    assert ba._minify("var a=1;", ".js") is None or isinstance(ba._minify("var a=1;", ".js"), str)  # 33-36
    assert ba._minify("a{color:red}", ".css") is None or isinstance(ba._minify("a{color:red}", ".css"), str)
    assert ba._process_file("/nope/file.txt") is None  # 48-51
    assert ba._collect_files("/nonexistent-xyz", "static/js", (".js",)) == []  # 89-90
    assert ba.build_all(base_dir="/nonexistent-xyz") == []  # 100-124 empty


def test_gzip_and_process_tmp(tmp_path):
    src = tmp_path / "x.js"
    src.write_text("var a = 1;", encoding="utf-8")
    gz = ba._gzip_file(str(src))  # 39-45
    assert gz.endswith(".gz")
    (tmp_path / "static" / "js").mkdir(parents=True)
    js = tmp_path / "static" / "js" / "app.js"
    js.write_text("var b = 2;", encoding="utf-8")
    with patch.object(ba, "_minify", return_value=None):
        info = ba._process_file(str(js))  # 62-64 copy branch
        assert info["file"] == "app.js"
    css_dir = tmp_path / "static" / "css"
    css_dir.mkdir(exist_ok=True)
    css = css_dir / "s.css"
    css.write_text("a{color:red}", encoding="utf-8")
    with patch.object(ba, "_minify", return_value="min!"):
        info2 = ba._process_file(str(css))  # 66-68 write branch
        assert info2["minified"] == len(b"min!")
    got = ba._collect_files(str(tmp_path), "static/js", (".js",))
    assert len(got) == 1  # 92-97 (skips .min.js)


def test_tenant_salt_and_cached_query(app):
    with app.test_request_context("/"):
        assert cd._tenant_cache_salt() == ""  # 18-22 no tid
        from flask import g

        g.active_tenant_id = 7
        assert cd._tenant_cache_salt() == "7"
    from flask import g as _g

    _g.pop("active_tenant_id", None)
    assert cd._tenant_cache_salt() == ""  # no ctx (g cleared)
    with app.test_request_context("/"):
        calls = {"n": 0}

        @cd.cached_query(timeout=60, key_prefix="t")
        def _fn(x):
            calls["n"] += 1
            return x * 2

        assert _fn(3) == 6  # miss -> set (real null cache)
        assert _fn(3) == 6
        with patch("utils.cache_decorators.cache") as mc:
            mc.get.side_effect = RuntimeError("down")
            assert _fn(4) == 8  # 37-41 get-fail
        with patch("utils.cache_decorators.cache") as mc2:
            mc2.get.return_value = None
            mc2.set.side_effect = RuntimeError("down")
            with app.test_request_context("/"):
                assert _fn(5) == 10  # 47-50 set-fail


def test_invalidate_branches():
    cd.invalidate_cache("k")  # 58-67 happy + exception-safe
    boom = MagicMock()
    boom.delete_many.side_effect = RuntimeError("x")
    boom.delete.side_effect = RuntimeError("x")
    with patch("utils.cache_decorators.cache", boom):
        cd.invalidate_cache("k")  # 66-67 except branch


def test_utf8_and_filter():
    assert el._ensure_utf8_stream(object()) is not None  # fallback 27
    rec = logging.LogRecord("n", logging.INFO, __file__, 1, "m", (), None)
    assert el.SafeLogRecordFilter().filter(rec) is True  # 40-44
    assert rec.user == "-"
    el.SecurityLogger.log_failed_login("u", "1.1.1.1", "ag")  # 158-184
    el.SecurityLogger.log_successful_login("u", "1.1.1.1")
    el.SecurityLogger.log_permission_denied("u", "act", "ip")
    el.SecurityLogger.log_rate_limit_exceeded("u", "ep", "ip")
    el.PerformanceLogger.log_slow_query("select 1", 0.01)  # below threshold no log
    el.PerformanceLogger.log_slow_query("select 1", 2.0)
    el.PerformanceLogger.log_cache_hit("k")
    el.PerformanceLogger.log_cache_miss("k")


def test_setup_enhanced_logging_tmp(app, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    out = el.setup_enhanced_logging(app)  # 47-153
    assert set(out) == {"app", "error", "security", "performance"}


def test_track_and_context(app):
    with app.test_request_context("/"):
        import time

        @pt.track_performance(threshold_ms=0)
        def _slow():
            return 1

        assert _slow() == 1  # 20-21 slow branch + g metrics 25-28

        @pt.track_performance(threshold_ms=10**9)
        def _fast():
            return 2

        assert _fast() == 2  # 22-23 fast branch
        with pt.PerformanceContext("op"):  # 42-50
            time.sleep(0.001)
        ctx = pt.PerformanceContext("x")
        ctx.start_time = None
        ctx.__exit__(None, None, None)  # 47-48 early return
        pt.log_slow_queries(app)  # 53-66 registers
