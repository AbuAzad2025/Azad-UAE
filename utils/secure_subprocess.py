"""
SecureSubprocess — hardened, allowlisted wrapper around subprocess.

This is the single, audited chokepoint for all external process execution in
the codebase.  It exists so that no business-logic module calls ``subprocess``
directly.  Security guarantees enforced here:

* ``shell=False`` is mandatory (no shell interpretation, no glob/var expansion).
* Commands are always passed as a *list of arguments* — never a single string
  that could be split or injected.
* The executable (``argv[0]``) MUST be allowlisted by basename, preventing
  execution of arbitrary binaries.
* Optional path-traversal guards keep script execution inside the repo root.
"""

from __future__ import annotations

import os
import subprocess  # nosec B404 -- audited chokepoint: only this module may import subprocess (shell=False + argv[0] allowlist enforced)
import sys
from typing import List, Mapping, Optional, Sequence

# Executables permitted by basename (OS-agnostic: .exe appended automatically
# on Windows).  Anything not in these sets is rejected before execution.
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
_PYTHON_BASENAMES = frozenset(
    {os.path.basename(sys.executable), "python", "python.exe"}
)


def _executable_basename(path: str) -> str:
    return os.path.basename(path.replace("\\", "/"))


def _validate_basename_allowlist(executable: str, allowed: frozenset[str]) -> str:
    if not executable or not str(executable).strip():
        raise ValueError("empty executable path")
    base = _executable_basename(executable)
    if base not in allowed:
        raise ValueError(f"executable not allowlisted: {base}")
    return base


class SecureSubprocess:
    """Central, hardened executor for allowlisted external tooling."""

    @staticmethod
    def run(
        argv: Sequence[str],
        *,
        allowed_basenames: frozenset[str],
        env: Optional[Mapping[str, str]] = None,
        timeout: int = 600,
        cwd: Optional[str] = None,
        encoding: str = "utf-8",
        errors: str = "replace",
    ) -> subprocess.CompletedProcess:
        """Execute an allowlisted command as a list of arguments.

        Never uses ``shell=True``.  The executable basename must be present in
        ``allowed_basenames``.  Returns a ``subprocess.CompletedProcess``.
        """
        if not argv:
            raise ValueError("argv required")
        _validate_basename_allowlist(argv[0], allowed_basenames)
        cmd: List[str] = [str(x) for x in argv]
        return subprocess.run(  # nosec B603 -- shell=False is mandatory and argv[0] is allowlisted by basename above
            cmd,
            shell=False,
            capture_output=True,
            text=True,
            encoding=encoding,
            errors=errors,
            env=dict(env) if env is not None else None,
            timeout=timeout,
            cwd=cwd,
        )

    @staticmethod
    def run_pg_tool(
        argv: Sequence[str],
        *,
        env: Optional[Mapping[str, str]] = None,
        timeout: int = 3600,
        cwd: Optional[str] = None,
    ) -> subprocess.CompletedProcess:
        """Run a PostgreSQL client tool (allowlisted basenames)."""
        return SecureSubprocess.run(
            argv,
            allowed_basenames=_PG_TOOL_BASENAMES,
            env=env,
            timeout=timeout,
            cwd=cwd,
        )

    @staticmethod
    def run_git(
        argv: Sequence[str],
        *,
        cwd: Optional[str] = None,
        timeout: int = 15,
    ) -> subprocess.CompletedProcess:
        """Run the git CLI (allowlisted basename)."""
        if not argv or _executable_basename(argv[0]) not in _GIT_BASENAMES:
            raise ValueError("git executable required")
        return SecureSubprocess.run(
            argv,
            allowed_basenames=_GIT_BASENAMES,
            timeout=timeout,
            cwd=cwd,
        )

    @staticmethod
    def run_repo_python_script(
        script_rel_path: str,
        args: Sequence[str],
        *,
        cwd: Optional[str] = None,
        env: Optional[Mapping[str, str]] = None,
        timeout: int = 600,
    ) -> subprocess.CompletedProcess:
        """Run a ``.py`` file under the repo root (path-traversal guarded)."""
        root: str = os.path.abspath(os.path.join(os.path.dirname(str(__file__)), ".."))
        script = os.path.normpath(
            os.path.join(root, script_rel_path.replace("/", os.sep))
        )
        if not script.endswith(".py") or not os.path.isfile(script):
            raise ValueError("script must be an existing .py under repo root")
        if os.path.commonpath([root, script]) != root:
            raise ValueError("script path escapes repo root")
        cmd = [sys.executable, script, *[str(a) for a in args]]
        return SecureSubprocess.run(
            cmd,
            allowed_basenames=_PYTHON_BASENAMES,
            env=env,
            timeout=timeout,
            cwd=cwd or root,
        )

    @staticmethod
    def run_python_module(
        module: str,
        args: Sequence[str],
        *,
        cwd: Optional[str] = None,
        env: Optional[Mapping[str, str]] = None,
        timeout: int = 600,
    ) -> subprocess.CompletedProcess:
        """Run ``python -m <module>`` with the current interpreter."""
        if not module or not module.replace(".", "").isalnum():
            raise ValueError("invalid module name")
        cmd = [sys.executable, "-m", module, *[str(a) for a in args]]
        return SecureSubprocess.run(
            cmd,
            allowed_basenames=_PYTHON_BASENAMES,
            env=env,
            timeout=timeout,
            cwd=cwd,
        )
