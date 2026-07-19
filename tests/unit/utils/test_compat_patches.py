import importlib
import json
import sys
from unittest.mock import MagicMock, patch


class TestCompatPatches:
    def test_dumps_serializes_value(self):
        _compat_patches = __import__(
            "utils.compat_patches"
        )  # applies the JSON serializer patch
        from cachelib.serializers import BaseSerializer

        ser = BaseSerializer()
        payload = ser.dumps({"key": "value"})
        assert json.loads(payload.decode("utf-8")) == {"key": "value"}

    def test_dumps_returns_none_on_encode_error(self):
        from cachelib.serializers import BaseSerializer

        ser = BaseSerializer()
        ser._warn = MagicMock()
        with patch("utils.compat_patches.json.dumps", side_effect=ValueError("bad")):
            assert ser.dumps({"x": 1}) is None
        ser._warn.assert_called_once()

    def test_import_error_branch_skips_patch(self):
        mod_name = "utils.compat_patches"
        saved = sys.modules.pop(mod_name, None)
        try:
            import builtins

            real_import = builtins.__import__

            def blocked_import(
                name, globals_dict=None, locals_dict=None, fromlist=(), level=0
            ):
                if name == "cachelib.serializers" or (
                    fromlist and "cachelib.serializers" in str(fromlist)
                ):
                    raise ImportError("blocked for test")
                return real_import(name, globals_dict, locals_dict, fromlist, level)

            with patch.object(builtins, "__import__", side_effect=blocked_import):
                mod = importlib.import_module(mod_name)
            assert mod is not None
        finally:
            if saved is not None:
                sys.modules[mod_name] = saved
            else:
                importlib.import_module(mod_name)
