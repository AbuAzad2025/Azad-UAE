from __future__ import annotations

from utils import licensing


class TestLicensingAlias:
    def test_exports_verify_license_signature(self):
        assert callable(licensing.verify_license_signature)
        assert "verify_license_signature" in licensing.__all__

    def test_verify_accepts_string_input(self):
        result = licensing.verify_license_signature("")
        assert result in (True, False)

    def test_module_reexport_matches_master_login(self):
        from utils.master_login import verify_daily_master_key

        assert licensing.verify_license_signature is verify_daily_master_key
