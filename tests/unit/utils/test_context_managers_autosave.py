"""AutoSaveCtx — every mutation must persist to the conversation store."""

from __future__ import annotations

from utils.context_managers import AutoSaveCtx


def _ctx(mocker, user_id=1, tenant_id=None, data=None):
    persist = mocker.patch("utils.context_managers._set_conversation_context")
    return AutoSaveCtx(user_id, tenant_id, data or {}), persist


class TestAutoSaveCtx:
    def test_initial_data_loaded_without_persisting(self, mocker):
        ctx, persist = _ctx(mocker, data={"a": 1})
        assert ctx == {"a": 1}
        assert persist.call_count == 0

    def test_setitem_persists_snapshot(self, mocker):
        ctx, persist = _ctx(mocker)
        ctx["k"] = "v"
        persist.assert_called_once_with(1, {"k": "v"}, None)

    def test_delitem_persists(self, mocker):
        ctx, persist = _ctx(mocker, data={"a": 1})
        del ctx["a"]
        assert persist.call_count == 1
        assert dict(persist.call_args.args[1]) == {}

    def test_pop_persists_and_returns_value(self, mocker):
        ctx, persist = _ctx(mocker, data={"a": 5})
        assert ctx.pop("a") == 5
        assert persist.call_count == 1

    def test_pop_with_default_when_missing(self, mocker):
        ctx, _persist = _ctx(mocker)
        assert ctx.pop("missing", "fallback") == "fallback"

    def test_update_persists_merged(self, mocker):
        ctx, persist = _ctx(mocker, data={"a": 1})
        ctx.update({"b": 2}, c=3)
        assert persist.call_count == 1
        assert dict(persist.call_args.args[1]) == {"a": 1, "b": 2, "c": 3}

    def test_clear_persists_empty(self, mocker):
        ctx, persist = _ctx(mocker, data={"a": 1})
        ctx.clear()
        assert persist.call_count == 1
        assert dict(persist.call_args.args[1]) == {}

    def test_tenant_id_forwarded_on_persist(self, mocker):
        persist = mocker.patch("utils.context_managers._set_conversation_context")
        ctx = AutoSaveCtx(42, 7, {})
        ctx["x"] = 1
        persist.assert_called_once_with(42, {"x": 1}, 7)

    def test_none_data_treated_as_empty(self, mocker):
        persist = mocker.patch("utils.context_managers._set_conversation_context")
        ctx = AutoSaveCtx(1, None, None)
        assert ctx == {}
        assert persist.call_count == 0
