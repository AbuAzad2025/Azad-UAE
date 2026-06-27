"""Tenant assets — slug/folder discovery and branding paths."""
from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

from utils.tenant_assets import (
    FOLDER_TO_SLUG,
    SLUG_TO_FOLDER,
    branding_for_tenant_slug,
    branding_paths_for_folder,
    discover_tenant_folders,
    folder_for_slug,
    slug_from_folder,
    static_assets_root,
)


class TestSlugMapping:
    def test_slug_from_folder_known(self):
        assert slug_from_folder('alhazem') == 'alhazem'

    def test_slug_from_folder_unknown_lowercases(self):
        assert slug_from_folder('CustomFolder') == 'customfolder'

    @patch('utils.tenant_assets.os.path.isdir', return_value=True)
    def test_folder_for_slug_mapped(self, _isdir):
        assert folder_for_slug('dubai-electronics') == 'dubai_electronics'

    @patch('utils.tenant_assets.os.path.isdir', return_value=False)
    def test_folder_for_slug_missing_dir(self, _isdir):
        assert folder_for_slug('dubai_electronics') is None

    @patch('utils.tenant_assets.os.path.isdir', return_value=True)
    def test_folder_for_slug_sanitized(self, _isdir):
        assert folder_for_slug('my-company!') == 'my-company'

    @patch('utils.tenant_assets.os.path.isdir', return_value=False)
    def test_folder_for_slug_empty(self, _isdir):
        assert folder_for_slug('') is None


class TestDiscoverTenantFolders:
    @patch('utils.tenant_assets.os.listdir', return_value=['alhazem', '.hidden', 'default'])
    @patch('utils.tenant_assets.os.path.isdir', side_effect=lambda p: not p.endswith('.hidden'))
    @patch('utils.tenant_assets._repo_static_root', return_value='/static')
    def test_skips_hidden_and_files(self, _root, _isdir, _listdir):
        folders = discover_tenant_folders()
        assert folders == ['alhazem', 'default']

    @patch('utils.tenant_assets.os.path.isdir', return_value=False)
    @patch('utils.tenant_assets._repo_static_root', return_value='/static')
    def test_missing_root_returns_empty(self, _root, _isdir):
        assert discover_tenant_folders() == []


class TestBrandingPaths:
    @patch('utils.tenant_assets.os.path.isfile', return_value=True)
    @patch('utils.tenant_assets._repo_static_root', return_value='/repo/static')
    def test_branding_paths_for_existing_files(self, _root, _isfile):
        paths = branding_paths_for_folder('default')
        assert 'logo_url' in paths
        assert paths['logo_url'].startswith('assets/tenants/default/')

    @patch('utils.tenant_assets.os.path.isfile', return_value=False)
    @patch('utils.tenant_assets._repo_static_root', return_value='/repo/static')
    def test_branding_paths_empty_when_no_files(self, _root, _isfile):
        assert branding_paths_for_folder('empty') == {}

    @patch('utils.tenant_assets.branding_paths_for_folder', return_value={'logo_url': 'x'})
    @patch('utils.tenant_assets.folder_for_slug', return_value='default')
    def test_branding_for_tenant_slug(self, _folder, _paths):
        assert branding_for_tenant_slug('default') == {'logo_url': 'x'}

    @patch('utils.tenant_assets.folder_for_slug', return_value=None)
    def test_branding_for_unknown_slug(self, _folder):
        assert branding_for_tenant_slug('missing') == {}


class TestStaticAssetsRoot:
    def test_uses_flask_app_root(self, app):
        with app.app_context():
            root = static_assets_root()
            assert root.endswith(os.path.join('static', 'assets'))
