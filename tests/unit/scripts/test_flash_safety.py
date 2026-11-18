"""Flash messages must never carry a raw exception string.

A system exception can contain SQL, table names, file paths or credentials.
``safe_error()`` logs the full traceback and returns a clean support reference;
these guards stop a route from interpolating ``str(exc)`` into a flash again.
"""

from __future__ import annotations

import glob
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def _flash_calls() -> list[tuple[str, int, str]]:
    calls = []
    for path in glob.glob(os.path.join(ROOT, "routes", "**", "*.py"), recursive=True):
        with open(path, encoding="utf-8", errors="ignore") as fh:
            for number, line in enumerate(fh, 1):
                if "flash(" not in line:
                    continue
                calls.append((os.path.relpath(path, ROOT), number, line))
    return calls


def test_no_raw_exception_in_flash_messages() -> None:
    unsafe = re.compile(r"str\((e|exc|error)\)|\b(e|exc|error)\.message|\{(e|exc|error)\}")
    offenders = [
        f"{path}:{number}" for path, number, line in _flash_calls() if unsafe.search(line[line.index("flash(") :])
    ]
    assert not offenders, offenders


def test_flash_call_sites_use_safe_error() -> None:
    offender_files = set()
    for path, _number, line in _flash_calls():
        if "safe_error(" in line or "BusinessRuleError" in line:
            continue
        if re.search(r"flash\(f?[\"']", line) and re.search(r"\b(e|exc|error)\b", line):
            offender_files.add(path)
    assert not offender_files, offender_files


def test_safe_error_logs_and_returns_reference() -> None:
    from utils.error_messages import safe_error

    class _Logger:
        def __init__(self) -> None:
            self.calls = 0

        def error(self, *_args, **_kwargs) -> None:
            self.calls += 1

    exc = RuntimeError("secret-value-ABCDEFGH")
    logger = _Logger()
    message = safe_error(exc, context="test", logger=logger)  # type: ignore[arg-type]
    assert "secret-value-ABCDEFGH" not in message
    assert logger.calls == 1
    assert re.search(r"[0-9A-F]{8}", message)
