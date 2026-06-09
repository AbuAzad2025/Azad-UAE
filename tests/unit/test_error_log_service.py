import pytest
from services.logging_core import LoggingCore


def test_get_parsed_errors_valid_parsing(tmp_path):
    log_file = tmp_path / "errors.log"
    log_content = """[2026-06-07 10:00:00] ERROR in mod1:10
Message: error message 1
Path: /path/1

[2026-06-07 10:05:00] WARNING in mod2:20
Message: warning message 2
Path: /path/2
"""
    log_file.write_text(log_content, encoding='utf-8')

    errors, total_pages, total, stats = LoggingCore.parse_error_log(log_file=str(log_file))

    assert total == 2
    assert errors[1]['level'] == 'ERROR'
    assert errors[0]['level'] == 'WARNING'
    assert errors[1]['module'] == 'mod1'
    assert errors[0]['module'] == 'mod2'


def test_get_parsed_errors_unknown_entry(tmp_path):
    log_file = tmp_path / "errors.log"
    log_file.write_text("invalid header line\nSome traceback", encoding='utf-8')

    errors, _, _, _ = LoggingCore.parse_error_log(log_file=str(log_file))

    assert len(errors) == 1
    assert errors[0]['level'] == 'UNKNOWN'
    assert "invalid header line" in errors[0]['message']


def test_get_parsed_errors_filtering(tmp_path):
    log_file = tmp_path / "errors.log"
    log_content = """[2026-06-07 10:00:00] ERROR in mod1:10
Message: test error
Path: /path/1

[2026-06-07 10:05:00] WARNING in mod1:20
Message: test warning
Path: /path/2
"""
    log_file.write_text(log_content, encoding='utf-8')

    # Filter by level
    errors, _, _, _ = LoggingCore.parse_error_log(log_file=str(log_file), level_filter='ERROR')
    assert len(errors) == 1
    assert errors[0]['level'] == 'ERROR'

    # Filter by search
    errors, _, _, _ = LoggingCore.parse_error_log(log_file=str(log_file), search='warning')
    assert len(errors) == 1
    assert errors[0]['level'] == 'WARNING'


def test_get_parsed_errors_pagination(tmp_path):
    log_file = tmp_path / "errors.log"
    # 60 entries
    content = ""
    for i in range(60):
        content += f"[2026-06-07 10:00:00] ERROR in mod:1\nMessage: m{i}\nPath: p\n\n"
    log_file.write_text(content, encoding='utf-8')

    # Page 1 (50 items)
    errors, total_pages, total, _ = LoggingCore.parse_error_log(log_file=str(log_file), page=1, per_page=50)
    assert total == 60
    assert total_pages == 2
    assert len(errors) == 50

    # Page 2 (10 items)
    errors, _, _, _ = LoggingCore.parse_error_log(log_file=str(log_file), page=2, per_page=50)
    assert len(errors) == 10


def test_get_parsed_errors_stats(tmp_path):
    log_file = tmp_path / "errors.log"
    log_content = """[2026-06-07 10:00:00] ERROR in mod1:10
Message: msg
Path: p

[2026-06-07 10:05:00] ERROR in mod2:20
Message: msg
Path: p
"""
    log_file.write_text(log_content, encoding='utf-8')

    _, _, _, stats = LoggingCore.parse_error_log(log_file=str(log_file))

    assert stats['total'] == 2
    assert stats['by_level']['ERROR'] == 2
    assert stats['by_module']['mod1'] == 1
    assert stats['by_module']['mod2'] == 1


def test_get_parsed_errors_file_not_exists():
    errors, _, total, _ = LoggingCore.parse_error_log(log_file='nonexistent.log')
    assert total == 0
    assert errors == []
