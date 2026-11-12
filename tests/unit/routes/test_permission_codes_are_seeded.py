"""Every @permission_required code must be a code the system can actually grant.

The seeder builds the ``permissions`` table from
``utils.constants.PERMISSION_CODES``. A ``@permission_required("...")`` guard
naming a code that is not in that tuple therefore describes a permission that
does not exist: no role can hold it, so the route answers 403 for everyone -
including a company admin, and including the platform owner whenever they are
acting on a company tenant rather than their own.

That is not hypothetical. This test was added after an audit found ten such
codes gating thirty-four routes: all seven of ``/assets``, four of
``/purchases/grn``, five of ``/purchases/requisitions``, seven of
``/hr/overtime`` and ``/hr/leave-ledger``, two product label routes and eight
AI routes. An earlier instance had already been found and patched by hand for
``budget:create``/``budget:approve``, so the failure mode has a history here:
someone adds a guard with a sensible new code and never registers it.

The check is over the routes as text rather than over a running app, because
the point is to catch the guard *before* it is deployed.
"""

from __future__ import annotations

import pathlib
import re

from utils.constants import PERMISSION_CODES, PERMISSIONS

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[3]
ROUTES_DIR = PROJECT_ROOT / "routes"

_GUARD_RE = re.compile(r"""@permission_required\(\s*["']([^"']+)["']\s*\)""")
# A permission checked by hand rather than by a decorator. The literal has to
# be a seeded code for exactly the same reason: a code nobody can hold makes
# the branch unreachable, and an *action* that checks a code that does not
# exist is an action that is silently refused for everybody.
_CHECK_RE = re.compile(r"""has_permission\(\s*["']([^"']+)["']\s*\)""")


def _guarded_codes():
    """(code, "routes/<file>:<line>") for every permission guard in routes/."""
    found = []
    for path in sorted(ROUTES_DIR.rglob("*.py")):
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            for code in _GUARD_RE.findall(line):
                found.append((code, f"routes/{path.name}:{lineno}"))
    return found


def _checked_codes():
    """(code, "path:line") for every hand-written permission check."""
    found = []
    for base in ("routes", "services"):
        root = PROJECT_ROOT / base
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*.py")):
            for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                for code in _CHECK_RE.findall(line):
                    found.append((code, f"{base}/{path.name}:{lineno}"))
    return found


def test_the_routes_directory_exists():
    assert ROUTES_DIR.is_dir(), f"{ROUTES_DIR} is not a directory"


def test_every_hand_checked_permission_code_is_seedable():
    """A permission checked by hand must name a code that can be granted.

    The decorator scan above cannot see these: the AI action router keeps a
    map of action names to permission codes, and a code that is not seeded
    there is unreachable for everybody. ``manage_cheques`` was one: no role
    can hold it, so the AI cheque wizard was dead for every non-owner.
    """
    seeded = set(PERMISSION_CODES)
    dead = [(code, where) for code, where in _checked_codes() if code not in seeded]
    assert not dead, (
        "these permission checks name a code that is never seeded:\n"
        + "\n".join(f"  {code}  at {where}" for code, where in dead)
        + "\nadd the code(s) to utils.constants.PERMISSION_CODES and PERMISSIONS"
    )


def test_every_guarded_permission_code_is_seedable():
    """The regression: a guard on a code that cannot be granted is a dead route."""
    seeded = set(PERMISSION_CODES)
    dead = [(code, where) for code, where in _guarded_codes() if code not in seeded]
    assert not dead, (
        "these routes guard on a permission that is never seeded, so no role can "
        "ever hold it and the route answers 403 for everyone:\n"
        + "\n".join(f"  {code}  at {where}" for code, where in dead)
        + "\nadd the code(s) to utils.constants.PERMISSION_CODES and PERMISSIONS"
    )


def test_every_seeded_permission_has_a_display_name():
    """A permission with no label renders as its own code in a role editor."""
    unnamed = sorted(set(PERMISSION_CODES) - set(PERMISSIONS))
    assert not unnamed, f"these permissions have no entry in PERMISSIONS: {unnamed}"


def test_every_display_name_maps_back_to_a_seeded_code():
    """PERMISSIONS must not drift into describing codes that do not exist."""
    extra = sorted(set(PERMISSIONS) - set(PERMISSION_CODES))
    assert not extra, f"PERMISSIONS describes codes that are not seeded: {extra}"
