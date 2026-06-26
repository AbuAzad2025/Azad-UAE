from __future__ import annotations

import pytest

from models.tenant_store import TenantStore


class TestTenantStoreHelpers:
    def test_repr(self):
        store = TenantStore(tenant_id=1, store_slug='demo', warehouse_id=2)
        assert 'demo' in repr(store)

    def test_logo_url_none_when_empty(self):
        store = TenantStore(tenant_id=1, store_slug='s', warehouse_id=1)
        assert store.logo_url() is None

    def test_logo_url_strips_static_prefix(self):
        store = TenantStore(tenant_id=1, store_slug='s', warehouse_id=1, logo_path='static/uploads/logos/x.png')
        assert store.logo_url() == '/static/uploads/logos/x.png'

    def test_logo_url_uploads_path(self):
        store = TenantStore(tenant_id=1, store_slug='s', warehouse_id=1, logo_path='uploads/logos/y.png')
        assert store.logo_url() == '/static/uploads/logos/y.png'

    def test_seo_title_ar_fallback(self):
        store = TenantStore(tenant_id=1, store_slug='s', warehouse_id=1, title='Main Title')
        assert store.seo_title('ar') == 'Main Title'

    def test_seo_title_en_prefers_meta(self):
        store = TenantStore(
            tenant_id=1, store_slug='s', warehouse_id=1,
            title='AR', meta_title_en='EN Title',
        )
        assert store.seo_title('en') == 'EN Title'

    def test_seo_description_en_prefers_meta(self):
        store = TenantStore(
            tenant_id=1, store_slug='s', warehouse_id=1,
            tagline='Tag', meta_description_en='EN Desc',
        )
        assert store.seo_description('en') == 'EN Desc'

    def test_seo_description_ar_fallback_tagline(self):
        store = TenantStore(tenant_id=1, store_slug='s', warehouse_id=1, tagline='وصف')
        assert store.seo_description('ar') == 'وصف'

    def test_return_policy_en(self):
        store = TenantStore(
            tenant_id=1, store_slug='s', warehouse_id=1,
            return_policy_ar='سياسة عربية', return_policy_en='English policy',
        )
        assert store.return_policy('en') == 'English policy'

    def test_return_policy_ar(self):
        store = TenantStore(
            tenant_id=1, store_slug='s', warehouse_id=1,
            return_policy_ar='سياسة الإرجاع',
        )
        assert store.return_policy('ar') == 'سياسة الإرجاع'
