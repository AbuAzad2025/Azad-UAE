"""Stage 3 regressions: entities, relative periods, follow-up TTL, read cache."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from ai_knowledge.cognitive import engine, followup, normalizer, read_cache
from ai_knowledge.cognitive.contracts import CognitiveIntent
from ai_knowledge.cognitive.slots import extract_slots
from utils.tenanting import get_active_tenant_id


def _user(uid=7, tid=1, perms=(), can_see_costs=False):
    allowed = frozenset(perms)

    def has_permission(code):
        return code in allowed or (code == "view_costs" and can_see_costs)

    def see_costs():
        return can_see_costs

    return SimpleNamespace(
        id=uid,
        tenant_id=tid,
        is_authenticated=True,
        is_owner=False,
        role=SimpleNamespace(slug="accountant"),
        branch_id=None,
        has_permission=has_permission,
        can_see_costs=see_costs,
    )


def test_interrogative_guard_blocks_writes_but_not_reads():
    assert normalizer.has_interrogative("كم رصيده؟")
    assert normalizer.has_interrogative("what is my balance?")
    assert not normalizer.has_interrogative("رصيد: أحمد")
    assert normalizer.interrogative_blocks_write("كم رصيده؟", "create_sale") is True
    assert normalizer.interrogative_blocks_write("كم رصيده؟", "customer_balance") is False
    assert normalizer.interrogative_blocks_write("رصيد: أحمد", "receive_payment") is False


def test_relative_periods_and_entities_are_extracted():
    cases = {
        "مبيعات الشهر الماضي": (60, "last_month"),
        "sales last week": (14, "last_week"),
        "today sales": (1, "today"),
        "السنة الماضية": (365, "last_year"),
    }
    for prompt, expected in cases.items():
        normalized = normalizer.normalize_message(prompt)
        assert normalized.relative_period == expected, prompt
        slots = extract_slots(CognitiveIntent.SALES_SUMMARY, normalized)
        assert slots.values["days"] == str(expected[0])
        assert slots.values["period_label"] == expected[1]


def test_multiword_name_currency_sku_and_reference():
    normalized = normalizer.normalize_message("رصيد العميل أحمد محمد شيقل sku WID-42 فاتورة 1234")
    slots = extract_slots(CognitiveIntent.CUSTOMER_BALANCE, normalized)

    assert slots.values["customer_name"] == "أحمد محمد"
    assert slots.values["currency"] == "ILS"
    assert slots.values["sku"] == "WID-42"
    assert slots.values["reference_number"] == "1234"

    english = normalizer.normalize_message("customer balance for Ahmad USD invoice 9988")
    english_slots = extract_slots(CognitiveIntent.CUSTOMER_BALANCE, english)
    assert english_slots.values["customer_name"] == "Ahmad"
    assert english_slots.values["currency"] == "USD"
    assert english_slots.values["reference_number"] == "9988"


def test_followup_context_ttl_and_explicit_reset():
    followup.clear_context()
    user = _user(perms=("view_reports",))
    signature = followup.permission_signature(user)

    followup.set_context(1, 7, signature, {"customer_name": "Ahmad"})
    assert followup.get_context(1, 7, signature) == {"customer_name": "Ahmad"}

    with patch.object(followup.time, "monotonic", return_value=10_000):
        followup.set_context(1, 7, signature, {"customer_name": "Ahmad"})
    with patch.object(followup.time, "monotonic", return_value=10_000 + followup.TTL_SECONDS + 1):
        assert followup.get_context(1, 7, signature) == {}

    followup.set_context(1, 7, signature, {"customer_name": "Ahmad"})
    assert followup.is_reset("ابدأ من جديد")
    assert followup.is_reset("clear context")
    followup.clear_context(1, 7)
    assert followup.get_context(1, 7, signature) == {}


def test_followup_context_revalidates_tenant_and_cost_signature():
    followup.clear_context()
    reader = _user(perms=("view_reports",), can_see_costs=True)
    signature = followup.permission_signature(reader)
    followup.set_context(1, 7, signature, {"days": "60"})

    other_tenant = _user(uid=7, tid=2, perms=("view_reports",), can_see_costs=True)
    other_cost = _user(perms=("view_reports",), can_see_costs=False)

    assert followup.get_context(2, 7, followup.permission_signature(other_tenant)) == {}
    assert followup.get_context(1, 7, followup.permission_signature(other_cost)) == {}

    # Re-store with the original authority: a mismatched turn must not leave
    # a usable entry behind for the higher-clearance caller.
    followup.set_context(1, 7, signature, {"days": "60"})
    assert followup.get_context(1, 7, signature) == {"days": "60"}


def _cache_key(prompt="sales summary", intent=CognitiveIntent.SALES_SUMMARY, user=None):
    normalized = normalizer.normalize_message(prompt)
    slots = extract_slots(intent, normalized)
    return read_cache.make_key(normalized, intent, slots, user or _user())


def test_read_cache_hit_and_cross_tenant_isolation():
    followup.clear_context()
    cache = read_cache.ReadCache()
    user = _user(perms=("view_reports",))
    key = _cache_key(user=user)

    assert cache.get(key, user) is None
    cache.set(key, "grounded-result")
    assert cache.get(key, user) == "grounded-result"

    other = _user(uid=8, tid=2, perms=("view_reports",))
    other_key = _cache_key(user=other)
    assert cache.get(other_key, other) is None

    # A same-id user with different permissions must not read the entry either.
    downgraded = _user(perms=())
    assert cache.get(key, downgraded) is None
    assert cache.stats()["hits"] == 1


def test_read_cache_invalidation_on_tenant_write():
    cache = read_cache.ReadCache()
    user = _user()
    key = _cache_key(user=user)
    cache.set(key, "stale")

    cache.invalidate_tenant(get_active_tenant_id(user))
    assert cache.get(key, user) is None

    with (
        patch("utils.db_safety.atomic_transaction") as transaction,
        patch.object(read_cache, "invalidate_tenant_reads") as invalidate,
    ):
        with read_cache.ai_write_transaction("probe", 1):
            pass
    assert transaction.called
    invalidate.assert_called_once_with(1)


def test_engine_followup_reuses_and_revalidates_slots():
    followup.clear_context()
    read_cache.get_default_cache().invalidate_all()
    user = _user(perms=("view_reports", "manage_customers"))
    with (
        patch.object(engine, "_history", return_value=[]),
        patch.object(
            engine,
            "check_access",
            return_value=(True, "view_reports"),
        ),
        patch.object(engine, "_answer_data", return_value=SimpleNamespace(decision="answer")) as answer,
    ):
        first = engine.process("sales summary", user)
        second = engine.process("sales summary", user)
        assert first is answer.return_value
        assert second is answer.return_value
        # The second turn is served from the read cache, not recomputed.
        assert answer.call_count == 1
        assert read_cache.get_default_cache().stats()["hits"] >= 1

    downgraded = _user(perms=(), can_see_costs=False)
    assert followup.get_context(1, 7, followup.permission_signature(downgraded)) == {}
