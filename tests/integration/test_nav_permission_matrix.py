"""Navigation/permission matrix — sidebar & navbar must never widen past the guard.

The permission audit compared every hardcoded ``url_for(...)`` in
``templates/partials/sidebar.html`` and ``templates/partials/navbar.html`` against
the decorator that actually protects the target endpoint. Nine mismatches were
found and fixed; this module freezes the corrected policy.

The check is data-driven from the live route registry: ``permission_required`` /
``admin_required`` / ``owner_required`` / ``company_admin_required`` publish
``_required_permission`` / ``_required_guard`` on the view, so the expected
visibility is derived from the route itself instead of a hand-kept table.

For each navigation link:

* the guard expression (with ``{% set %}`` flag variables inlined) must mention the
  permission the route enforces — otherwise a legitimate role lost access;
* it must not mention any *other* permission — otherwise a role sees an entry and
  lands on 403/404;
* platform-only endpoints must be gated on a global-scope identity, mirroring
  ``is_global_scope_user``.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from flask import current_app

_PARTIALS = Path(__file__).resolve().parents[2] / "templates" / "partials"
_SIDEBAR = _PARTIALS / "sidebar.html"
_NAVBAR = _PARTIALS / "navbar.html"
_CHROME = [_SIDEBAR, _NAVBAR]

_IF_RE = re.compile(r"{%\s*if\s+(.*?)\s*%}")
_SET_RE = re.compile(r"{%\s*set\s+(\w+)\s*=\s*(.*?)\s*%}")
_TAG_RE = re.compile(r"{%\s*(if|elif|else|endif|for|endfor)\b(.*?)%}")
_PERM_RE = re.compile(r"has_permission\(\s*'([a-z_]+)'\s*\)")
_URL_RE = re.compile(r"url_for\(\s*'([a-z_]+\.[a-z_0-9]+)'")
_GLOBAL_SCOPE_RE = re.compile(
    r"\(current_user\.is_owner and not current_user\.tenant_id\)"
    r"|current_user\.role\.slug == 'developer'"
)

# Platform surfaces: only a global owner / developer may even see these entries.
_GLOBAL_ONLY_ENDPOINTS = frozenset(
    {
        "owner.dashboard",
        "owner.system_config",
        "owner.list_backups",
        "owner.system_health",
        "owner.users_list",
        "ai.config",
        "tenants.switch",
    }
)


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _route_requirements() -> dict[str, str | None]:
    """endpoint -> required permission code (None when the route has no permission guard)."""
    out: dict[str, str | None] = {}
    for rule in current_app.url_map.iter_rules():
        view = current_app.view_functions.get(rule.endpoint)
        out[rule.endpoint] = getattr(view, "_required_permission", None)
    return out


def _route_guard_kind() -> dict[str, str | None]:
    """endpoint -> admin/owner guard name published by the decorator."""
    out: dict[str, str | None] = {}
    for rule in current_app.url_map.iter_rules():
        view = current_app.view_functions.get(rule.endpoint)
        out[rule.endpoint] = getattr(view, "_required_guard", None)
    return out


# Identity evidence that must appear in the nav condition for a non-permission
# guard. Keeps admin/company/owner surfaces from degrading to "visible to all".
_GUARD_IDENTITY_TOKENS = {
    "admin": ("is_admin", "is_super_admin", "is_owner"),
    "company_admin": ("super_admin", "manager", "is_super_admin"),
    "owner_or_company_admin": ("is_admin", "is_super_admin", "super_admin", "manager", "is_owner"),
    "global_owner": ("is_owner", "developer"),
}


def _inline_flags(source: str, expression: str) -> str:
    """Substitute ``{% set _flag = ... %}`` definitions used inside ``expression``.

    Word boundaries are essential: ``_sale`` is a substring of ``manage_sales``, so
    a plain ``in`` check would skip exactly the flags that need expanding.
    """
    result = expression
    for _ in range(4):
        changed = False
        for name, value in _SET_RE.findall(source):
            if re.search(rf"\b{re.escape(name)}\b", value):
                continue  # self-referencing definition, leave it in place
            result, hits = re.subn(rf"\b{re.escape(name)}\b", f"({value})", result)
            changed = changed or bool(hits)
        if not changed:
            break
    return result


def _enclosing_guard(source: str, endpoint: str) -> str | None:
    """Return the effective Jinja condition that gates one ``url_for`` call.

    Walks the template with a real block stack (instead of guessing a line
    distance), so a link nested deep inside ``{% if _pay %} … {% endif %}`` is
    attributed to that flag rather than to an unrelated sibling ``{% if %}``.

    The innermost non-``else`` condition is the effective gate: every enclosing
    condition is implied by it. Links that only exist in an ``{% else %}`` branch
    are attributed to the nearest enclosing condition instead, because a negation
    cannot be resolved statically and over-approximating is the safe direction.
    """
    lines = source.splitlines()
    target = next((i for i, line in enumerate(lines) if f"url_for('{endpoint}'" in line), None)
    if target is None:
        return None

    stack: list[tuple[str, bool]] = []
    for line in lines[: target + 1]:
        for tag, rest in _TAG_RE.findall(line):
            if tag in ("if", "elif"):
                stack.append((rest.strip(), False))
            elif tag == "for":
                stack.append(("", False))
            elif tag in ("endif", "endfor"):
                if stack:
                    stack.pop()
            elif tag == "else":
                if stack:
                    expr, _ = stack[-1]
                    stack[-1] = (expr, True)

    for expr, is_else in reversed(stack):
        if expr and not is_else:
            return _inline_flags(source, expr)
    return None


def _nav_links(path: Path) -> dict[str, str]:
    """endpoint -> guard expression, for the hardcoded links in one chrome file."""
    source = _source(path)
    links: dict[str, str] = {}
    for endpoint in dict.fromkeys(_URL_RE.findall(source)):
        guard = _enclosing_guard(source, endpoint)
        if guard is not None:
            links[endpoint] = guard
    return links


_SIDEBAR_LINKS = _nav_links(_SIDEBAR)
_NAVBAR_LINKS = _nav_links(_NAVBAR)
_ALL_LINKS = {**_SIDEBAR_LINKS, **_NAVBAR_LINKS}
_PERMISSION_LINKS = sorted(
    (ep, guard) for ep, guard in _ALL_LINKS.items() if ep not in _GLOBAL_ONLY_ENDPOINTS and _PERM_RE.search(guard)
)
_GLOBAL_LINKS = sorted(ep for ep in _ALL_LINKS if ep in _GLOBAL_ONLY_ENDPOINTS)


def test_matrix_actually_collected_links() -> None:
    """Guard against a vacuous pass: the extraction must see real entries."""
    assert len(_PERMISSION_LINKS) >= 45, sorted(_ALL_LINKS)
    assert len(_GLOBAL_LINKS) >= 3, _GLOBAL_LINKS


def test_admin_surfaces_keep_an_identity_gate() -> None:
    """Routes guarded by admin/company/owner helpers must stay identity-gated in the nav."""
    kinds = _route_guard_kind()
    checked = 0
    for endpoint, kind in sorted(kinds.items()):
        if not kind or endpoint not in _ALL_LINKS or endpoint in _GLOBAL_ONLY_ENDPOINTS:
            continue
        guard = _ALL_LINKS[endpoint]
        tokens = _GUARD_IDENTITY_TOKENS[kind]
        assert any(token in guard for token in tokens), (
            f"{endpoint} is protected by '{kind}' but its nav condition carries no matching identity "
            f"check ({guard.strip()}) — the entry would render for any authenticated user"
        )
        checked += 1
    assert checked >= 3, f"only {checked} admin/company surface(s) inspected"


@pytest.mark.parametrize(("endpoint", "guard"), _PERMISSION_LINKS, ids=[ep for ep, _ in _PERMISSION_LINKS])
def test_nav_visibility_matches_route_guard(endpoint: str, guard: str) -> None:
    required = _route_requirements().get(endpoint, "__missing__")
    assert required != "__missing__", f"{endpoint} is not a registered route"
    if not required:
        return  # login-only route: any authenticated user may see it

    mentioned = set(_PERM_RE.findall(guard))
    assert required in mentioned, (
        f"{endpoint}: route requires '{required}' but the nav condition does not mention it — "
        f"roles with that permission would lose the entry ({guard.strip()})"
    )
    extra = mentioned - {required}
    assert not extra, (
        f"{endpoint}: nav condition also accepts {sorted(extra)}; the route enforces only "
        f"'{required}' so those users would see the link and get 403/404"
    )


@pytest.mark.parametrize("endpoint", _GLOBAL_LINKS)
def test_global_endpoints_require_global_scope_identity(endpoint: str) -> None:
    guard = _ALL_LINKS[endpoint]
    assert _GLOBAL_SCOPE_RE.search(guard), (
        f"{endpoint} must be gated on a global-scope identity (is_owner without tenant, or developer): {guard.strip()}"
    )


def test_sidebar_backup_links_are_not_duplicated() -> None:
    source = _source(_SIDEBAR)
    assert source.count("url_for('tenant_backups.index'") == 1
    assert source.count("url_for('owner.list_backups'") == 1
    # the Company_Backups entry duplicated the tenant route inside the company block
    assert "t('Company_Backups')" not in source


def test_pos_entry_requires_system_and_tenant_flags() -> None:
    assert re.search(r"tenant_enable_pos and system_enable_pos", _source(_SIDEBAR))
