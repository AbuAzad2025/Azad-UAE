import json

try:
    from cachelib.serializers import BaseSerializer

    def _patched_dumps(self, value):
        try:
            return json.dumps(value).encode("utf-8")
        except (TypeError, ValueError) as e:
            self._warn(e)
            return None

    def _patched_loads(self, value):
        if value is None:
            return None
        try:
            return json.loads(value.decode("utf-8"))
        except (TypeError, ValueError) as e:
            self._warn(e)
            return None

    BaseSerializer.dumps = _patched_dumps  # type: ignore[method-assign]
    BaseSerializer.loads = _patched_loads  # type: ignore[method-assign]
except ImportError:
    pass
