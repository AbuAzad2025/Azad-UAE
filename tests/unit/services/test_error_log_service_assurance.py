"""Error log service — stack trace parsing, search, pagination, purge limits."""

from __future__ import annotations

import textwrap


from services.error_log_service import ErrorLogService

SAMPLE_LOG = textwrap.dedent("""\
    [2025-06-01 10:15:30] ERROR in services.payroll:42
    Message: Division by zero
    Path: /api/payroll/run
    Traceback (most recent call last):
      File "payroll.py", line 42, in run
        1/0
    ZeroDivisionError: division by zero

    [2025-06-01 11:00:00] WARNING in services.auth:10
    Message: login failed password=secret123
    Path: /login
    None
""")


class TestParseErrors:
    """get_parsed_errors — structured stack trace extraction."""

    def test_parses_standard_error_blocks(self, tmp_path):
        log_file = tmp_path / "errors.log"
        log_file.write_text(SAMPLE_LOG, encoding="utf-8")

        rows, pages, total, stats = ErrorLogService.get_parsed_errors(
            page=1,
            per_page=50,
            error_file=str(log_file),
        )
        assert total == 2
        assert rows[0]["level"] == "WARNING"
        assert rows[1]["level"] == "ERROR"
        assert "Division by zero" in rows[1]["message"]
        assert "payroll.py" in rows[1]["traceback"]
        assert stats["by_level"]["ERROR"] == 1

    def test_missing_log_returns_empty(self, tmp_path):
        rows, pages, total, stats = ErrorLogService.get_parsed_errors(
            error_file=str(tmp_path / "missing.log"),
        )
        assert rows == []
        assert total == 0
        assert stats == {}

    def test_malformed_header_treated_as_unknown(self, tmp_path):
        log_file = tmp_path / "bad.log"
        log_file.write_text("garbled line without header\nmore text", encoding="utf-8")

        rows, _, total, _ = ErrorLogService.get_parsed_errors(error_file=str(log_file))
        assert total == 1
        assert rows[0]["level"] == "UNKNOWN"


class TestFilteringAndPagination:
    """Search, level filter, per-page auto-purge window."""

    def test_search_filters_message_and_traceback(self, tmp_path):
        log_file = tmp_path / "errors.log"
        log_file.write_text(SAMPLE_LOG, encoding="utf-8")

        rows, _, total, _ = ErrorLogService.get_parsed_errors(
            search="division",
            error_file=str(log_file),
        )
        assert total == 1
        assert "Division" in rows[0]["message"]

    def test_level_filter_case_insensitive(self, tmp_path):
        log_file = tmp_path / "errors.log"
        log_file.write_text(SAMPLE_LOG, encoding="utf-8")

        rows, _, total, _ = ErrorLogService.get_parsed_errors(
            level_filter="warning",
            error_file=str(log_file),
        )
        assert total == 1
        assert rows[0]["level"] == "WARNING"

    def test_pagination_limits_page_size(self, tmp_path):
        log_file = tmp_path / "many.log"
        blocks = []
        for i in range(5):
            blocks.append(f"[2025-06-01 12:{i:02d}:00] ERROR in mod{i}:1\nMessage: err {i}\nPath: /\n")
        log_file.write_text("\n\n".join(blocks), encoding="utf-8")

        rows, total_pages, total, _ = ErrorLogService.get_parsed_errors(
            page=2,
            per_page=2,
            error_file=str(log_file),
        )
        assert total == 5
        assert total_pages == 3
        assert len(rows) == 2

    def test_sensitive_payload_preserved_in_raw_for_audit_scrubbing(self, tmp_path):
        """Raw block retained; downstream audit service scrubs on ingest."""
        log_file = tmp_path / "secrets.log"
        log_file.write_text(
            "[2025-06-01 09:00:00] ERROR in api:1\nMessage: api_key=leak\nPath: /\n",
            encoding="utf-8",
        )
        rows, _, _, _ = ErrorLogService.get_parsed_errors(error_file=str(log_file))
        assert "api_key=leak" in rows[0]["message"]
        assert "api_key=leak" in rows[0]["raw"]
