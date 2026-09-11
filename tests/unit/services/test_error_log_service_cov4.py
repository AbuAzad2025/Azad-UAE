"""Cov4: error_log_service — file-missing/parse/filter/paginate/stats arcs."""

from __future__ import annotations

from services.error_log_service import ErrorLogService


def _write_log(path, content):
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def test_missing_file_returns_empty(tmp_path):
    paginated, total_pages, total, stats = ErrorLogService.get_parsed_errors(error_file=str(tmp_path / "nope.log"))
    assert paginated == []
    assert total_pages == 1
    assert total == 0
    assert stats == {}


def test_parse_header_entry_with_message_path_and_none_tb(tmp_path):
    p = tmp_path / "errors.log"
    _write_log(
        p,
        "[2026-01-02 10:11:12] ERROR in app:42\nMessage: boom happened\nPath: /x/y\nNone\n",
    )
    paginated, total_pages, total, stats = ErrorLogService.get_parsed_errors(error_file=str(p))
    assert total == 1
    entry = paginated[0]
    assert entry["level"] == "ERROR"
    assert entry["module"] == "app"
    assert entry["message"] == "boom happened"
    assert entry["path"] == "/x/y"
    assert entry["traceback"] == ""
    assert stats["total"] == 1
    assert stats["by_level"] == {"ERROR": 1}


def test_parse_non_header_entry_and_empty_entries_skipped(tmp_path):
    p = tmp_path / "errors.log"
    _write_log(p, "just some random line without header\nTraceback line2\n\n\n   \n")
    paginated, _, total, stats = ErrorLogService.get_parsed_errors(error_file=str(p))
    assert total == 1
    assert paginated[0]["level"] == "UNKNOWN"
    assert paginated[0]["traceback"] == "Traceback line2"
    assert stats["by_level"] == {"UNKNOWN": 1}


def test_search_and_level_filter_and_pagination(tmp_path):
    p = tmp_path / "errors.log"
    _write_log(
        p,
        "[2026-01-02 10:00:00] ERROR in billing:10\nMessage: alpha failure\nPath: /a\n"
        "\n\n"
        "[2026-01-03 11:00:00] WARNING in auth:20\nMessage: beta warning\nPath: /b\n",
    )
    # search hits module/message/path/traceback (lower + strip branch)
    paginated, _, total, _ = ErrorLogService.get_parsed_errors(search="  ALPHA ", error_file=str(p))
    assert total == 1
    assert paginated[0]["module"] == "billing"
    # level filter upper() branch
    paginated, _, total, _ = ErrorLogService.get_parsed_errors(level_filter="warning", error_file=str(p))
    assert total == 1
    assert paginated[0]["level"] == "WARNING"
    # pagination branch
    paginated, total_pages, total, _ = ErrorLogService.get_parsed_errors(page=2, per_page=1, error_file=str(p))
    assert total == 2
    assert total_pages == 2
    assert len(paginated) == 1
    # combined filter yielding nothing still keeps total_pages==1
    paginated, total_pages, total, stats = ErrorLogService.get_parsed_errors(search="zzz-no-match", error_file=str(p))
    assert total == 0
    assert stats == {}


def test_entry_without_message_path_lines(tmp_path):
    p = tmp_path / "errors.log"
    _write_log(
        p,
        "[2026-05-01 09:00:00] INFO in worker:7\nSome traceback body here\n",
    )
    paginated, _, total, stats = ErrorLogService.get_parsed_errors(error_file=str(p))
    assert total == 1
    assert paginated[0]["message"] == ""
    assert paginated[0]["traceback"] == "Some traceback body here"
    assert stats["by_module"] == {"worker": 1}
