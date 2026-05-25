"""
Discover tenant branding assets under static/img/tenants/{slug}/.
Folder name = tenant slug (e.g. alhazem → img/tenants/alhazem/logo.png).
"""

from __future__ import annotations

import os
import re

# Slug in DB may differ from folder; map folder → canonical slug
FOLDER_TO_SLUG: dict[str, str] = {
    "alhazem": "alhazem",
}

SLUG_TO_FOLDER: dict[str, str] = {
    "alhazem": "alhazem",
    "alhazem-batteries": "alhazem",
}


def static_img_root() -> str:
    from flask import current_app
    return os.path.join(current_app.root_path, "static", "img")


def discover_tenant_folders() -> list[str]:
    root = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "static",
        "img",
        "tenants",
    )
    if not os.path.isdir(root):
        return []
    out = []
    for name in sorted(os.listdir(root)):
        path = os.path.join(root, name)
        if os.path.isdir(path) and not name.startswith("."):
            out.append(name)
    return out


def branding_paths_for_folder(folder: str) -> dict[str, str]:
    """Relative static paths for known asset files if they exist on disk."""
    base = f"img/tenants/{folder}"
    keys = {
        "logo_url": "logo.png",
        "logo_dark_url": "logo_dark.png",
        "favicon_url": "favicon.png",
        "og_image_url": "og-1200x630.png",
    }
    root = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "static",
        "img",
        "tenants",
        folder,
    )
    branding = {}
    for field, filename in keys.items():
        if os.path.isfile(os.path.join(root, filename)):
            branding[field] = f"{base}/{filename}"
    for size, filename in (("icon_192", "icon-192.png"), ("icon_512", "icon-512.png")):
        if os.path.isfile(os.path.join(root, filename)):
            branding[size] = f"{base}/{filename}"
    return branding


def slug_from_folder(folder: str) -> str:
    return FOLDER_TO_SLUG.get(folder, folder.strip().lower())


def folder_for_slug(slug: str) -> str | None:
    slug = (slug or "").strip().lower()
    if slug in SLUG_TO_FOLDER:
        folder = SLUG_TO_FOLDER[slug]
        root = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "static",
            "img",
            "tenants",
            folder,
        )
        return folder if os.path.isdir(root) else None
    folder = re.sub(r"[^a-z0-9-]+", "", slug)
    root = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "static",
        "img",
        "tenants",
        folder,
    )
    return folder if os.path.isdir(root) else None


def branding_for_tenant_slug(slug: str) -> dict[str, str]:
    folder = folder_for_slug(slug)
    if not folder:
        return {}
    return branding_paths_for_folder(folder)
