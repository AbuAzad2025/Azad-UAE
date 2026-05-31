"""Legacy alias — delegates to hardened master_login module."""

from utils.master_login import verify_daily_master_key as verify_license_signature

__all__ = ["verify_license_signature"]
