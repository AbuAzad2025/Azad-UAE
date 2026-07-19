import json

try:
    from cachelib.serializers import BaseSerializer

    def _patched_dumps(self, value, *args, **kwargs):
        try:
            return json.dumps(value).encode("utf-8")
        except (TypeError, ValueError) as e:
            self._warn(e)
            return None

    def _patched_loads(self, value, *args, **kwargs):
        if value is None:
            return None
        try:
            return json.loads(value.decode("utf-8"))
        except (TypeError, ValueError) as e:
            self._warn(e)
            return None

    BaseSerializer.dumps = _patched_dumps  # type: ignore[assignment]
    BaseSerializer.loads = _patched_loads  # type: ignore[assignment]
except ImportError:
    pass
