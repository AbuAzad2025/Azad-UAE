import pickle
from cachelib.serializers import BaseSerializer
from utils import compat_patches
assert compat_patches is not None
class TestCompatPatches:
    def test_cachelib_base_serializer_dumps_patched(self):
        ser = BaseSerializer()
        result = ser.dumps("test_value")
        assert result == pickle.dumps("test_value", protocol=pickle.HIGHEST_PROTOCOL)
    def test_cachelib_base_serializer_dumps_returns_none_on_error(self):
        class Unpicklable:
            def __reduce__(self):
                raise pickle.PicklingError("cannot pickle")
        ser = BaseSerializer()
        result = ser.dumps(Unpicklable())
        assert result is None
