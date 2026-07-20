"""
Discover tenant branding assets under static/assets/tenants/{slug}/.
"""

from __future__ import annotations

import os
import re

from utils.static_asset_paths import TENANT_ASSET_LAYOUT, tenant_asset_rel

FOLDER_TO_SLUG: dict[str, str] = {
    "alhazem": "alhazem",
    "nasrallah": "nasrallah",
    "ramallah": "ramallah",
    "default": "default",
    "dubai_electronics": "dubai_electronics",
    "abudhabi_construction": "abudhabi_construction",
    "sharjah_trading": "sharjah_trading",
}

SLUG_TO_FOLDER: dict[str, str] = {
    "alhazem": "alhazem",
    "alhazem-batteries": "alhazem",
    "nasrallah": "nasrallah",
    "ramallah": "ramallah",
    "default": "default",
    "dubai_electronics": "dubai_electronics",
    "dubai-electronics": "dubai_electronics",
    "abudhabi_construction": "abudhabi_construction",
    "abudhabi-construction": "abudhabi_construction",
    "abu-dhabi-construction": "abudhabi_construction",
    "sharjah_trading": "sharjah_trading",
    "sharjah-trading": "sharjah_trading",
}


def _repo_static_root() -> str:
    return str(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static"))


def static_assets_root() -> str:
    from flask import current_app

    return str(os.path.join(str(current_app.root_path), "static", "assets"))


def discover_tenant_folders() -> list[str]:
    root = os.path.join(_repo_static_root(), "assets", "tenants")
    if not os.path.isdir(root):
        return []
    out: list[str] = []
    for name in sorted(os.listdir(root)):
        path = os.path.join(root, name)
        if os.path.isdir(path) and not name.startswith("."):
            out.append(name)
    return out


def branding_paths_for_folder(folder: str) -> dict[str, str]:
    """Relative static paths for known asset files if they exist on disk."""
    disk_root = os.path.join(_repo_static_root(), "assets", "tenants", folder)
    branding: dict[str, str] = {}
    for field, rel_suffix in TENANT_ASSET_LAYOUT.items():
        if os.path.isfile(os.path.join(disk_root, rel_suffix.replace("/", os.sep))):
            branding[field] = tenant_asset_rel(folder, field)
    return branding


def slug_from_folder(folder: str) -> str:
    return FOLDER_TO_SLUG.get(folder, folder.strip().lower())


def folder_for_slug(slug: str) -> str | None:
    slug = (slug or "").strip().lower()
    if slug in SLUG_TO_FOLDER:
        folder = SLUG_TO_FOLDER[slug]
        root = os.path.join(_repo_static_root(), "assets", "tenants", folder)
        return folder if os.path.isdir(root) else None
    folder = re.sub(r"[^a-z0-9-]+", "", slug)
    root = os.path.join(_repo_static_root(), "assets", "tenants", folder)
    return folder if os.path.isdir(root) else None


def branding_for_tenant_slug(slug: str) -> dict[str, str]:
    folder = folder_for_slug(slug)
    if not folder:
        return {}
    return branding_paths_for_folder(folder)
