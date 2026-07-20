"""
Allowlisted subprocess helpers for backup/restore.

All external execution is delegated to the hardened, central
``utils.secure_subprocess.SecureSubprocess`` utility, which enforces
``shell=False``, list-argument invocation, and an executable allowlist.  This
module exists only to expose the backup-specific entry points.
"""

from __future__ import annotations

from typing import Mapping, Optional, Sequence

from utils.secure_subprocess import SecureSubprocess

# Re-export the allowlist names for callers that validate independently.
from utils.secure_subprocess import (  # noqa: F401
    _GIT_BASENAMES,
    _PG_TOOL_BASENAMES,
)


def validate_pg_executable(executable: str) -> str:
    """Return executable path if its basename is an allowed PostgreSQL client tool."""
    if not executable or not str(executable).strip():
        raise ValueError("empty executable path")
    base = executable.replace("\\", "/").split("/")[-1]
    if base not in _PG_TOOL_BASENAMES:
        raise ValueError(f"executable not allowlisted: {base}")
    return executable


def run_pg_tool(
    argv: Sequence[str],
    *,
    env: Optional[Mapping[str, str]] = None,
    timeout: int = 3600,
    cwd: Optional[str] = None,
):
    """Run a PostgreSQL CLI tool. argv[0] must be allowlisted; never uses shell=True."""
    return SecureSubprocess.run_pg_tool(argv, env=env, timeout=timeout, cwd=cwd)


def run_git(
    argv: Sequence[str],
    *,
    cwd: Optional[str] = None,
    timeout: int = 15,
):
    """Run the git CLI (allowlisted basename)."""
    return SecureSubprocess.run_git(argv, cwd=cwd, timeout=timeout)


def run_repo_python_script(
    script_rel_path: str,
    args: Sequence[str],
    *,
    cwd: Optional[str] = None,
    env: Optional[Mapping[str, str]] = None,
    timeout: int = 600,
):
    """Run a .py file under the repo root (no shell)."""
    return SecureSubprocess.run_repo_python_script(script_rel_path, args, cwd=cwd, env=env, timeout=timeout)


def run_python_module(
    module: str,
    args: Sequence[str],
    *,
    cwd: Optional[str] = None,
    env: Optional[Mapping[str, str]] = None,
    timeout: int = 600,
):
    """Run `python -m <module>` with the current interpreter (no shell)."""
    return SecureSubprocess.run_python_module(module, args, cwd=cwd, env=env, timeout=timeout)
