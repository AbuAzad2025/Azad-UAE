"""Low-level context managers with zero route-layer dependencies.

AutoSaveCtx is extracted here to break the circular import chain:
routes.__init__ → routes.ai_routes.__init__ → shared → routes.ai_routes (back).
"""

from ai_knowledge.core.conversation_store import set_context as _set_conversation_context


class AutoSaveCtx(dict):
    """Dict subclass that auto-persists mutations to the conversation store."""

    def __init__(self, user_id: int, tenant_id: int | None, data: dict):
        super().__init__(data or {})
        self._user_id = user_id
        self._tenant_id = tenant_id

    def _persist(self) -> None:
        _set_conversation_context(self._user_id, dict(self), self._tenant_id)

    def __setitem__(self, key, value):
        super().__setitem__(key, value)
        self._persist()

    def __delitem__(self, key):
        super().__delitem__(key)
        self._persist()

    def pop(self, key, *args):
        result = super().pop(key, *args)
        self._persist()
        return result

    def update(self, *args, **kwargs):
        super().update(*args, **kwargs)
        self._persist()

    def clear(self):
        super().clear()
        self._persist()
