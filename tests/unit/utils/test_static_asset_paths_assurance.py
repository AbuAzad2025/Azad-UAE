"""Static asset path helpers — tenant layout and upload dirs."""

from __future__ import annotations

import pytest

from utils.static_asset_paths import (
    AZAD_FAVICON,
    AZAD_LOGO,
    DEFAULT_PRODUCT_IMAGE,
    TENANT_ASSET_LAYOUT,
    tenant_asset_base,
    tenant_asset_rel,
    tenant_demo_products_dir,
    tenant_upload_dir,
)


class TestTenantAssetPaths:
    def test_tenant_asset_base(self):
        assert tenant_asset_base("acme") == "assets/tenants/acme"

    def test_tenant_asset_rel_known_kind(self):
        rel = tenant_asset_rel("acme", "logo_url")
        assert rel == f"assets/tenants/acme/{TENANT_ASSET_LAYOUT['logo_url']}"

    def test_tenant_asset_rel_unknown_kind_raises(self):
        with pytest.raises(KeyError, match="missing"):
            tenant_asset_rel("acme", "missing")

    def test_tenant_upload_dir_requires_id(self):
        with pytest.raises(ValueError, match="tenant_id required"):
            tenant_upload_dir(0, "products")

    def test_tenant_upload_dir_sanitizes_category(self):
        path = tenant_upload_dir(5, "../products")
        assert path == "uploads/tenants/5/products"
        assert ".." not in path

    def test_tenant_demo_products_dir_normalizes_slug(self):
        assert tenant_demo_products_dir("  ACME  ") == "assets/tenants/acme/demo-products"
        assert tenant_demo_products_dir("") == "assets/tenants//demo-products"

    def test_constants_are_relative_static_paths(self):
        assert AZAD_LOGO.startswith("assets/")
        assert AZAD_FAVICON.startswith("assets/")
        assert DEFAULT_PRODUCT_IMAGE.startswith("assets/")
