"""
Allowlisted subprocess helpers for backup/restore (Bandit-safe pg tool invocation).
"""
from __future__ import annotations

import os
import subprocess  # nosec B404
import sys
from typing import List, Mapping, Optional, Sequence

# Basenames only — full paths must end with one of these names.
_PG_TOOL_BASENAMES = frozenset(
    {
        "pg_dump",
        "pg_dump.exe",
        "pg_restore",
        "pg_restore.exe",
        "psql",
        "psql.exe",
        "createdb",
        "createdb.exe",
        "dropdb",
        "dropdb.exe",
    }
)
_GIT_BASENAMES = frozenset({"git", "git.exe"})


def _executable_basename(path: str) -> str:
    return os.path.basename(path.replace("\\", "/"))


def validate_pg_executable(executable: str) -> str:
    """Return executable path if basename is an allowed PostgreSQL client tool."""
    if not executable or not str(executable).strip():
        raise ValueError("empty executable path")
    base = _executable_basename(executable)
    if base not in _PG_TOOL_BASENAMES:
        raise ValueError(f"executable not allowlisted: {base}")
    return executable


def run_pg_tool(
    argv: Sequence[str],
    *,
    env: Optional[Mapping[str, str]] = None,
    timeout: int = 3600,
    cwd: Optional[str] = None,
) -> subprocess.CompletedProcess:
    """Run a PostgreSQL CLI tool. argv[0] must be allowlisted; never uses shell=True."""
    if not argv:
        raise ValueError("argv required")
    validate_pg_executable(argv[0])
    cmd: List[str] = [str(x) for x in argv]
    return subprocess.run(
        cmd,
        shell=False,
        capture_output=True,
        text=True,
        env=dict(env) if env is not None else None,
        timeout=timeout,
        cwd=cwd,
    )  # nosec B603


def run_git(
    argv: Sequence[str],
    *,
    cwd: Optional[str] = None,
    timeout: int = 15,
) -> subprocess.CompletedProcess:
    if not argv or _executable_basename(argv[0]) not in _GIT_BASENAMES:
        raise ValueError("git executable required")
    return subprocess.run(
        [str(x) for x in argv],
        shell=False,
        capture_output=True,
        text=True,
        cwd=cwd,
        timeout=timeout,
    )  # nosec B603


def run_repo_python_script(
    script_rel_path: str,
    args: Sequence[str],
    *,
    cwd: Optional[str] = None,
    env: Optional[Mapping[str, str]] = None,
    timeout: int = 600,
) -> subprocess.CompletedProcess:
    """Run a .py file under the repo root (no shell)."""
    root: str = os.path.abspath(os.path.join(os.path.dirname(str(__file__)), ".."))
    script = os.path.normpath(os.path.join(root, script_rel_path.replace("/", os.sep)))
    if not script.endswith(".py") or not os.path.isfile(script):
        raise ValueError("script must be an existing .py under repo root")
    if os.path.commonpath([root, script]) != root:
        raise ValueError("script path escapes repo root")
    cmd = [sys.executable, script, *[str(a) for a in args]]
    return subprocess.run(
        cmd,
        shell=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=dict(env) if env is not None else None,
        timeout=timeout,
        cwd=cwd or root,
    )  # nosec B603


def run_python_module(
    module: str,
    args: Sequence[str],
    *,
    cwd: Optional[str] = None,
    env: Optional[Mapping[str, str]] = None,
    timeout: int = 600,
) -> subprocess.CompletedProcess:
    """Run `python -m <module>` with the current interpreter (no shell)."""
    if not module or not module.replace(".", "").isalnum():
        raise ValueError("invalid module name")
    cmd = [sys.executable, "-m", module, *[str(a) for a in args]]
    return subprocess.run(
        cmd,
        shell=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=dict(env) if env is not None else None,
        timeout=timeout,
        cwd=cwd,
    )  # nosec B603
