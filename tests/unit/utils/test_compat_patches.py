import importlib
import pickle
import sys
from unittest.mock import MagicMock, patch

import pytest


class TestCompatPatches:
    def test_dumps_serializes_value(self):
        from cachelib.serializers import BaseSerializer

        ser = BaseSerializer()
        payload = ser.dumps({'key': 'value'})
        assert pickle.loads(payload) == {'key': 'value'}

    def test_dumps_returns_none_on_pickling_error(self):
        from cachelib.serializers import BaseSerializer

        ser = BaseSerializer()
        ser._warn = MagicMock()
        with patch('utils.compat_patches.pickle.dumps', side_effect=pickle.PicklingError('bad')):
            assert ser.dumps({'x': 1}) is None
        ser._warn.assert_called_once()

    def test_import_error_branch_skips_patch(self):
        mod_name = 'utils.compat_patches'
        saved = sys.modules.pop(mod_name, None)
        try:
            import builtins
            real_import = builtins.__import__

            def blocked_import(name, globals=None, locals=None, fromlist=(), level=0):
                if name == 'cachelib.serializers' or (
                    fromlist and 'cachelib.serializers' in str(fromlist)
                ):
                    raise ImportError('blocked for test')
                return real_import(name, globals, locals, fromlist, level)

            with patch.object(builtins, '__import__', side_effect=blocked_import):
                mod = importlib.import_module(mod_name)
            assert mod is not None
        finally:
            if saved is not None:
                sys.modules[mod_name] = saved
            else:
                importlib.import_module(mod_name)
