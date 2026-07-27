"""SaaS feature gating — ``@feature_required`` route decorator.

Locks a whole module entry point behind the tenant's ``enable_<feature>``
flag (copied from the subscribed Package at activation):

- API requests (``/api/...`` or JSON) → ``403 {"error": "FEATURE_LOCKED", "feature": ...}``
- Web requests → ``403`` with a localized upgrade hint.

No tenant context (owner/platform mode) → allowed through.

Built on the same flag resolution as ``require_subscription_feature``
(utils/decorators.py) — nullable POS sub-features inherit the plan default.
"""

from __future__ import annotations

from functools import wraps

from flask import abort, jsonify, request
from flask_babel import gettext

from extensions import db
from utils.pos_features import POS_SUBFEATURES, pos_feature_enabled


def _wants_json() -> bool:
    if request.path.startswith("/api/") or "/api/" in request.path:
        return True
    if request.is_json:
        return True
    best = request.accept_mimetypes.best_match(["application/json", "text/html"])
    return best == "application/json" and request.accept_mimetypes[best] > request.accept_mimetypes["text/html"]


def feature_required(feature_name: str):
    """Gate a route by the tenant's ``enable_<feature_name>`` flag."""

    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            denial = _feature_denial(feature_name)
            if denial is not None:
                return denial
            return f(*args, **kwargs)

        return wrapper

    return decorator


def _feature_denial(feature_name: str):
    """Return a denial response when the feature is locked, else None."""
    from models.tenant import Tenant
    from utils.tenanting import get_active_tenant_id

    tid = get_active_tenant_id()
    if not tid:
        return None  # owner/platform context
    tenant = db.session.get(Tenant, int(tid))
    if tenant is None:
        abort(403, description=gettext("المستأجر غير موجود"))

    enabled = getattr(tenant, f"enable_{feature_name}", True)
    if enabled is None and feature_name in POS_SUBFEATURES:
        # Nullable POS sub-feature: NULL inherits the plan default.
        enabled = pos_feature_enabled(tenant, feature_name)

    if enabled:
        return None
    if _wants_json():
        return jsonify({"error": "FEATURE_LOCKED", "feature": feature_name}), 403
    abort(
        403,
        description=gettext(
            'ميزة "%(feature)s" غير مفعّلة في باقتك الحالية. رقِّ باقتك لتفعيلها.',
            feature=feature_name,
        ),
    )


def install_feature_gate(bp, feature_name: str) -> None:
    """Lock every route of a blueprint behind the tenant's feature flag."""

    @bp.before_request
    def _check_feature_flag():  # noqa: ANN202 — flask before_request hook
        return _feature_denial(feature_name)
