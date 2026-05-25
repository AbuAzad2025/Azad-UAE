"""
Global username policy for multi-tenant login.
- Platform reserved: owner, azad (and variants without tenant prefix)
- Company users: {TENANT_CODE}_{local_part}
"""

from __future__ import annotations

import re

# Platform-only logins (case-insensitive exact match)
PLATFORM_RESERVED = frozenset({"owner", "azad"})

# Explicit tenant slug -> username prefix (uppercase)
TENANT_PREFIX_BY_SLUG: dict[str, str] = {
    "default": "DEF",
    "alhazem": "HZM",
    "alhazem-batteries": "HZM",  # legacy slug alias
    "t-aed": "AED",
    "t-usd": "USD",
    "t-ils": "ILS",
}

USERNAME_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_]{2,48}$")
LOCAL_PART_PATTERN = re.compile(r"^[a-z][a-z0-9_]{1,39}$")


def normalize_username(value: str) -> str:
    return (value or "").strip().lower()


def is_platform_reserved(username: str) -> bool:
    return normalize_username(username) in PLATFORM_RESERVED


def tenant_username_prefix(tenant) -> str:
    """Derive short uppercase tenant code for usernames."""
    if tenant is None:
        return ""
    slug = (getattr(tenant, "slug", None) or "").strip().lower()
    if slug in TENANT_PREFIX_BY_SLUG:
        return TENANT_PREFIX_BY_SLUG[slug]
    if slug.startswith("t-") and len(slug) > 2:
        part = slug[2:].split("-")[0]
        return part.upper()[:6]
    cleaned = re.sub(r"[^a-z0-9]+", "", slug)
    if len(cleaned) >= 3:
        return cleaned[:3].upper()
    return "TN"


def branch_key(branch_code: str | None) -> str:
    code = (branch_code or "").strip().upper()
    if not code:
        return "main"
    if code in ("MAIN", "HQ"):
        return "main"
    parts = code.split("-")
    if len(parts) >= 2 and parts[-1].isalnum() and len(parts[-1]) <= 3:
        return parts[-1].lower()
    return code.lower().replace("-", "_")[:12]


def build_company_username(tenant, local_part: str) -> str:
    prefix = tenant_username_prefix(tenant)
    local = (local_part or "").strip().lower()
    if not prefix:
        raise ValueError("لا يمكن إنشاء مستخدم شركة بدون رمز تينانت.")
    if not LOCAL_PART_PATTERN.match(local):
        raise ValueError(f"جزء اسم المستخدم غير صالح: {local_part}")
    return f"{prefix}_{local}"


def parse_company_username(username: str) -> tuple[str, str] | None:
    """Return (prefix, local_part) or None if not a prefixed company username."""
    raw = (username or "").strip()
    if "_" not in raw:
        return None
    prefix, local = raw.split("_", 1)
    if not prefix or not local:
        return None
    if not re.match(r"^[A-Za-z][A-Za-z0-9]{1,5}$", prefix):
        return None
    return prefix.upper(), local.lower()


def validate_username_for_user(username: str, *, is_owner: bool = False, tenant=None) -> str | None:
    """
    Return error message in Arabic or None if valid.
    """
    raw = (username or "").strip()
    if not raw:
        return "اسم المستخدم مطلوب."

    if not USERNAME_PATTERN.match(raw):
        return "اسم المستخدم: حروف وأرقام وشرطة سفلية فقط (3–50 حرفاً)."

    lowered = normalize_username(raw)

    if is_owner:
        if lowered != "owner":
            return "حساب مالك المنصة يجب أن يكون owner فقط."
        return None

    if is_platform_reserved(lowered):
        return "اسم المستخدم محجوز لمنصة ازاد (owner / azad)."

    if tenant is None:
        return "يجب ربط المستخدم بشركة (تينانت) لاستخدام بادئة الشركة."

    expected_prefix = tenant_username_prefix(tenant)
    parsed = parse_company_username(raw)
    if not parsed:
        return f"استخدم الصيغة: {expected_prefix}_اسم_المستخدم (مثال: {expected_prefix}_ahmad)"

    prefix, local = parsed
    if prefix != expected_prefix:
        return f"بادئة الشركة يجب أن تكون {expected_prefix}_ وليس {prefix}_"

    if not LOCAL_PART_PATTERN.match(local):
        return "جزء الاسم بعد البادئة: أحرف صغيرة إنجليزية وأرقام وشرطة سفلية."

    return None


def is_platform_user(user) -> bool:
    if not user:
        return False
    if getattr(user, "is_owner", False):
        return True
    uname = normalize_username(getattr(user, "username", ""))
    return uname in PLATFORM_RESERVED
