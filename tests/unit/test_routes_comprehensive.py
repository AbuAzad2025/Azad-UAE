"""Smoke-test every registered route: auto-discovers all URL rules and exercises them."""
import re
import pytest
from werkzeug.exceptions import HTTPException


def _resolve_url(rule_str):
    def _replacer(m):
        converter = m.group(1)
        name = m.group(2)
        if converter in ("int", "float"):
            return "1"
        if converter == "uuid":
            return "00000000-0000-0000-0000-000000000000"
        if name in ("lang", "language", "locale", "lang_code"):
            return "en"
        if name == "path":
            return "test"
        return "test"
    result = re.sub(r"<(\w+):(\w+)>", _replacer, rule_str)
    result = re.sub(r"<(\w+)>", lambda m: "en" if m.group(1) in ("lang", "language", "locale", "lang_code") else "test", result)
    return result


SKIP_PREFIXES = ("/static/", "/media/", "/_debug_toolbar/")


def _matches_skip(up):
    return any(up.startswith(p) for p in SKIP_PREFIXES)


def test_all_routes_smoke(app, auth_client, owner_client):
    errors = []
    rules = list(app.url_map.iter_rules())
    for rule in rules:
        url_pattern = rule.rule
        if _matches_skip(url_pattern):
            continue
        url = _resolve_url(url_pattern)
        for method in rule.methods:
            if method in ("HEAD", "OPTIONS"):
                continue
            client = owner_client if url_pattern.startswith("/owner") else auth_client
            try:
                resp = client.open(url, method=method)
                if resp.status_code == 500:
                    errors.append(f"500 {method} {url} ({rule.endpoint})")
            except HTTPException:
                pass
            except Exception as e:
                errors.append(f"EXCEPTION {method} {url}: {e}")
    if errors:
        pytest.fail("Routes with errors:\n" + "\n".join(errors[:50]))
