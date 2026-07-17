import pickle

try:
    from cachelib.serializers import BaseSerializer

    def _patched_dumps(self, value, protocol=pickle.HIGHEST_PROTOCOL):
        try:
            return pickle.dumps(value, protocol)
        except (pickle.PickleError, pickle.PicklingError) as e:
            self._warn(e)
            return None

    BaseSerializer.dumps = _patched_dumps
except ImportError:
    pass
