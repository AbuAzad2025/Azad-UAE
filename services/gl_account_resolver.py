"""Dynamic GL account resolver for Phase 1J.

The resolver is intentionally isolated from posting flows.  While
ENABLE_DYNAMIC_GL_MAPPING is disabled, ``resolve_gl_account`` returns ``None``
without querying mappings so existing legacy posting paths can remain active.
When the flag is enabled, it resolves a GL concept to a tenant-owned, active,
postable GLAccount or raises GLMappingError.
"""
from __future__ import annotations

from dataclasses import dataclass

from flask import current_app, has_app_context

from config import Config
from models._constants import VALID_GL_CONCEPT_CODES
from models.gl import GLAccount, GLAccountMapping


@dataclass(frozen=True)
class GLMappingError(RuntimeError):
    """Raised when dynamic GL concept resolution cannot safely resolve."""

    tenant_id: int
    concept_code: str
    branch_id: int | None
    issue: str

    def __post_init__(self) -> None:
        RuntimeError.__init__(self, self.message)

    @property
    def message(self) -> str:
        return (
            "GL mapping error: "
            f"tenant_id={self.tenant_id}, "
            f"concept_code={self.concept_code}, "
            f"branch_id={self.branch_id}, "
            f"issue={self.issue}"
        )


def is_dynamic_gl_mapping_enabled(config: object | None = None) -> bool:
    """Return the effective dynamic GL mapping feature flag value."""
    if config is not None:
        if hasattr(config, "get"):
            return bool(config.get("ENABLE_DYNAMIC_GL_MAPPING", False))
        return bool(getattr(config, "ENABLE_DYNAMIC_GL_MAPPING", False))

    if has_app_context():
        return bool(current_app.config.get("ENABLE_DYNAMIC_GL_MAPPING", False))

    return bool(getattr(Config, "ENABLE_DYNAMIC_GL_MAPPING", False))


def resolve_gl_account(
    tenant_id: int,
    concept_code: str,
    branch_id: int | None = None,
) -> GLAccount | None:
    """Resolve a concept to GLAccount only when dynamic mapping is enabled.

    Returns ``None`` when ENABLE_DYNAMIC_GL_MAPPING is false. This preserves the
    current legacy posting behavior for callers that explicitly fall back to
    hardcoded account lookups while the feature flag remains disabled.

    Raises:
        GLMappingError: when the feature flag is enabled but the mapping or
        mapped account is missing/invalid.
    """
    if not is_dynamic_gl_mapping_enabled():
        return None

    return _resolve_dynamic_gl_account(
        tenant_id=tenant_id,
        concept_code=concept_code,
        branch_id=branch_id,
    )


def _resolve_dynamic_gl_account(
    tenant_id: int,
    concept_code: str,
    branch_id: int | None = None,
) -> GLAccount:
    """Resolve using GLAccountMapping after feature-flag gating."""
    normalized_concept = _normalize_concept_code(
        tenant_id=tenant_id,
        concept_code=concept_code,
        branch_id=branch_id,
    )
    mapping = _find_active_mapping(
        tenant_id=tenant_id,
        concept_code=normalized_concept,
        branch_id=branch_id,
    )
    if mapping is None:
        _raise_missing_or_inactive_mapping(
            tenant_id=tenant_id,
            concept_code=normalized_concept,
            branch_id=branch_id,
        )

    return _validated_account(
        mapping=mapping,
        tenant_id=tenant_id,
        concept_code=normalized_concept,
        branch_id=branch_id,
    )


def _normalize_concept_code(
    tenant_id: int,
    concept_code: str,
    branch_id: int | None,
) -> str:
    normalized = str(concept_code or "").strip().upper()
    if normalized not in VALID_GL_CONCEPT_CODES:
        raise GLMappingError(
            tenant_id=tenant_id,
            concept_code=normalized,
            branch_id=branch_id,
            issue="Unknown GL concept code.",
        )
    return normalized


def _find_active_mapping(
    tenant_id: int,
    concept_code: str,
    branch_id: int | None = None,
) -> GLAccountMapping | None:
    if branch_id is not None:
        branch_mapping = _one_or_error(
            GLAccountMapping.query.filter_by(
                tenant_id=tenant_id,
                concept_code=concept_code,
                branch_id=branch_id,
                is_active=True,
            ).all(),
            tenant_id=tenant_id,
            concept_code=concept_code,
            branch_id=branch_id,
            scope="branch override",
        )
        if branch_mapping is not None:
            return branch_mapping

    return _one_or_error(
        GLAccountMapping.query.filter_by(
            tenant_id=tenant_id,
            concept_code=concept_code,
            branch_id=None,
            is_active=True,
        ).all(),
        tenant_id=tenant_id,
        concept_code=concept_code,
        branch_id=None,
        scope="tenant default",
    )


def _one_or_error(
    mappings: list[GLAccountMapping],
    tenant_id: int,
    concept_code: str,
    branch_id: int | None,
    scope: str,
) -> GLAccountMapping | None:
    if len(mappings) > 1:
        raise GLMappingError(
            tenant_id=tenant_id,
            concept_code=concept_code,
            branch_id=branch_id,
            issue=f"Duplicate active {scope} mappings exist.",
        )
    return mappings[0] if mappings else None


def _raise_missing_or_inactive_mapping(
    tenant_id: int,
    concept_code: str,
    branch_id: int | None,
) -> None:
    inactive_query = GLAccountMapping.query.filter_by(
        tenant_id=tenant_id,
        concept_code=concept_code,
        is_active=False,
    )
    if branch_id is not None:
        inactive_branch = inactive_query.filter_by(branch_id=branch_id).first()
        if inactive_branch is not None:
            raise GLMappingError(
                tenant_id=tenant_id,
                concept_code=concept_code,
                branch_id=branch_id,
                issue="Branch override mapping exists but is inactive.",
            )

    inactive_default = inactive_query.filter_by(branch_id=None).first()
    if inactive_default is not None:
        raise GLMappingError(
            tenant_id=tenant_id,
            concept_code=concept_code,
            branch_id=branch_id,
            issue="Tenant-level mapping exists but is inactive.",
        )

    raise GLMappingError(
        tenant_id=tenant_id,
        concept_code=concept_code,
        branch_id=branch_id,
        issue="No active GL account mapping exists for this concept.",
    )


def _validated_account(
    mapping: GLAccountMapping,
    tenant_id: int,
    concept_code: str,
    branch_id: int | None,
) -> GLAccount:
    if mapping.branch_id is not None:
        branch = mapping.branch
        if branch is None:
            raise GLMappingError(
                tenant_id=tenant_id,
                concept_code=concept_code,
                branch_id=branch_id,
                issue="Branch override references a missing branch.",
            )
        if branch.tenant_id != tenant_id:
            raise GLMappingError(
                tenant_id=tenant_id,
                concept_code=concept_code,
                branch_id=branch_id,
                issue="Branch override belongs to a different tenant.",
            )

    account = mapping.gl_account
    if account is None:
        raise GLMappingError(
            tenant_id=tenant_id,
            concept_code=concept_code,
            branch_id=branch_id,
            issue="Mapped GL account does not exist.",
        )
    if account.tenant_id != tenant_id:
        raise GLMappingError(
            tenant_id=tenant_id,
            concept_code=concept_code,
            branch_id=branch_id,
            issue="Mapped GL account belongs to a different tenant.",
        )
    if not account.is_active:
        raise GLMappingError(
            tenant_id=tenant_id,
            concept_code=concept_code,
            branch_id=branch_id,
            issue="Mapped GL account is inactive.",
        )
    if account.is_header:
        raise GLMappingError(
            tenant_id=tenant_id,
            concept_code=concept_code,
            branch_id=branch_id,
            issue="Mapped GL account is a header/group account and is not postable.",
        )
    return account
