"""Tests for AI system fixes: DB tables, conversation store, QuickLearner."""
import uuid
import pytest
from datetime import datetime, timezone, timedelta
from extensions import db
from models.ai import AiMemory, AiInteraction, AiExpertise


class TestAiModels:
    def test_ai_memory_creation(self, app):
        from models import Tenant
        with app.app_context():
            tenant = Tenant(name='AI Mem-' + uuid.uuid4().hex[:6], name_ar='اختبار', slug='ai-mem-' + uuid.uuid4().hex[:6], email='m@test.com')
            db.session.add(tenant)
            db.session.commit()
            mem = AiMemory(
                key="test_key",
                value="test_value",
                category="general",
                tenant_id=tenant.id,
                confidence=0.95,
                source="test",
                is_active=True,
            )
            db.session.add(mem)
            db.session.commit()
            assert mem.id is not None
            assert mem.to_dict()["key"] == "test_key"
            assert float(mem.to_dict()["confidence"]) == 0.95

    def test_ai_memory_tenant_isolation(self, app):
        from models import Tenant
        with app.app_context():
            t1 = Tenant(name='AI Iso1-' + uuid.uuid4().hex[:6], name_ar='اختبار 1', slug='ai-iso1-' + uuid.uuid4().hex[:6], email='i1@test.com')
            t2 = Tenant(name='AI Iso2-' + uuid.uuid4().hex[:6], name_ar='اختبار 2', slug='ai-iso2-' + uuid.uuid4().hex[:6], email='i2@test.com')
            db.session.add(t1)
            db.session.add(t2)
            db.session.commit()
            m1 = AiMemory(key="q", value="a1", tenant_id=t1.id, category="test")
            m2 = AiMemory(key="q", value="a2", tenant_id=t2.id, category="test")
            db.session.add_all([m1, m2])
            db.session.commit()
            r1 = AiMemory.query.filter_by(tenant_id=t1.id, key="q").first()
            r2 = AiMemory.query.filter_by(tenant_id=t2.id, key="q").first()
            assert r1.value == "a1"
            assert r2.value == "a2"

    def test_ai_interaction_creation(self, app):
        from models import Tenant
        with app.app_context():
            tenant = Tenant(name='AI Inter-' + uuid.uuid4().hex[:6], name_ar='اختبار', slug='ai-inter-' + uuid.uuid4().hex[:6], email='in@test.com')
            db.session.add(tenant)
            db.session.commit()
            inter = AiInteraction(
                tenant_id=tenant.id,
                user_id=1,
                query="hello",
                response="hi",
                intent="greeting",
                was_successful=True,
                response_time_ms=120,
            )
            db.session.add(inter)
            db.session.commit()
            assert inter.id is not None
            assert inter.to_dict()["query"] == "hello"

    def test_ai_expertise_creation(self, app):
        from models import Tenant
        with app.app_context():
            tenant = Tenant(name='AI Exp-' + uuid.uuid4().hex[:6], name_ar='اختبار', slug='ai-exp-' + uuid.uuid4().hex[:6], email='ex@test.com')
            db.session.add(tenant)
            db.session.commit()
            exp = AiExpertise(
                tenant_id=tenant.id,
                domain="accounting",
                topic="vat",
                knowledge="5% vat in uae",
                priority=5,
            )
            db.session.add(exp)
            db.session.commit()
            assert exp.id is not None
            assert exp.to_dict()["domain"] == "accounting"


class TestConversationStore:
    def test_get_set_clear_context(self, app):
        from ai_knowledge.core.conversation_store import (
            get_context,
            set_context,
            clear_context,
        )
        from models import Tenant
        with app.app_context():
            tenant = Tenant(name='AI Ctx-' + uuid.uuid4().hex[:6], name_ar='اختبار', slug='ai-ctx-' + uuid.uuid4().hex[:6], email='ctx@test.com')
            db.session.add(tenant)
            db.session.commit()
            set_context(1, {"last_action": "عميل", "step": 1}, tenant_id=tenant.id)
            all_mem = AiMemory.query.filter_by(tenant_id=tenant.id, category="conversation").all()
            print("MEMS", [(m.key, m.value, m.is_active) for m in all_mem])
            ctx = get_context(1, tenant_id=tenant.id)
            assert ctx == {"last_action": "عميل", "step": 1}
            clear_context(1, tenant_id=tenant.id)
            ctx2 = get_context(1, tenant_id=tenant.id)
            assert ctx2 is None

    def test_context_expires_after_two_hours(self, app):
        from ai_knowledge.core.conversation_store import (
            get_context,
            set_context,
        )
        from models import Tenant
        with app.app_context():
            tenant = Tenant(name='AI Exp2-' + uuid.uuid4().hex[:6], name_ar='اختبار', slug='ai-exp2-' + uuid.uuid4().hex[:6], email='e2@test.com')
            db.session.add(tenant)
            db.session.commit()
            set_context(2, {"action": "test"}, tenant_id=tenant.id)
            mem = AiMemory.query.filter_by(
                key="conversation_context:2", tenant_id=tenant.id
            ).first()
            mem.last_accessed = datetime.now(timezone.utc) - timedelta(hours=3)
            db.session.commit()
            ctx = get_context(2, tenant_id=tenant.id)
            assert ctx is None


class TestQuickLearner:
    def test_learn_and_get_answer(self, app):
        from ai_knowledge.learning.quick_learner import QuickLearner
        from models import Tenant
        with app.app_context():
            tenant = Tenant(name='AI VAT-' + uuid.uuid4().hex[:6], name_ar='اختبار', slug='ai-vat-' + uuid.uuid4().hex[:6], email='vt@test.com')
            db.session.add(tenant)
            db.session.commit()
            ql = QuickLearner()
            ql.learn("what is vat", "5% in uae", category="tax", tenant_id=tenant.id)
            ans = ql.get_answer("what is vat", tenant_id=tenant.id)
            assert ans == "5% in uae"

    def test_get_answer_fuzzy_match(self, app):
        from ai_knowledge.learning.quick_learner import QuickLearner
        from models import Tenant
        with app.app_context():
            tenant = Tenant(name='AI Fuzzy-' + uuid.uuid4().hex[:6], name_ar='اختبار', slug='ai-fuzzy-' + uuid.uuid4().hex[:6], email='fz@test.com')
            db.session.add(tenant)
            db.session.commit()
            ql = QuickLearner()
            ql.learn("how to add customer", "go to customers page", tenant_id=tenant.id)
            ans = ql.get_answer("how to add custome", tenant_id=tenant.id)
            assert "customers page" in ans

    def test_tenant_isolation(self, app):
        from ai_knowledge.learning.quick_learner import QuickLearner
        from models import Tenant
        with app.app_context():
            t1 = Tenant(name='AI Price1-' + uuid.uuid4().hex[:6], name_ar='اختبار 1', slug='ai-price1-' + uuid.uuid4().hex[:6], email='p1@test.com')
            t2 = Tenant(name='AI Price2-' + uuid.uuid4().hex[:6], name_ar='اختبار 2', slug='ai-price2-' + uuid.uuid4().hex[:6], email='p2@test.com')
            db.session.add(t1)
            db.session.add(t2)
            db.session.commit()
            ql = QuickLearner()
            ql.learn("price", "100", tenant_id=t1.id)
            ql.learn("price", "200", tenant_id=t2.id)
            assert ql.get_answer("price", tenant_id=t1.id) == "100"
            assert ql.get_answer("price", tenant_id=t2.id) == "200"

    def test_global_answer_fallback(self, app):
        from ai_knowledge.learning.quick_learner import QuickLearner
        with app.app_context():
            ql = QuickLearner()
            ql.learn("help", "type commands", tenant_id=None)
            assert ql.get_answer("help", tenant_id=5) == "type commands"


class TestAutoSaveCtx:
    def test_autosave_on_setitem(self, app):
        from ai_knowledge.core.conversation_store import get_context
        from routes.ai import _AutoSaveCtx
        from models import Tenant
        with app.app_context():
            tenant = Tenant(name='AI Auto1-' + uuid.uuid4().hex[:6], name_ar='اختبار', slug='ai-auto1-' + uuid.uuid4().hex[:6], email='a1@test.com')
            db.session.add(tenant)
            db.session.commit()
            ctx = _AutoSaveCtx(10, tenant.id, {})
            ctx["step"] = 2
            db_ctx = get_context(10, tenant_id=tenant.id)
            assert db_ctx == {"step": 2}

    def test_autosave_on_delitem(self, app):
        from ai_knowledge.core.conversation_store import get_context
        from routes.ai import _AutoSaveCtx
        from models import Tenant
        with app.app_context():
            tenant = Tenant(name='AI Auto2-' + uuid.uuid4().hex[:6], name_ar='اختبار', slug='ai-auto2-' + uuid.uuid4().hex[:6], email='a2@test.com')
            db.session.add(tenant)
            db.session.commit()
            ctx = _AutoSaveCtx(11, tenant.id, {"a": 1, "b": 2})
            del ctx["a"]
            db_ctx = get_context(11, tenant_id=tenant.id)
            assert db_ctx == {"b": 2}

    def test_autosave_on_clear(self, app):
        from ai_knowledge.core.conversation_store import get_context
        from routes.ai import _AutoSaveCtx
        from models import Tenant
        with app.app_context():
            tenant = Tenant(name='AI Auto3-' + uuid.uuid4().hex[:6], name_ar='اختبار', slug='ai-auto3-' + uuid.uuid4().hex[:6], email='a3@test.com')
            db.session.add(tenant)
            db.session.commit()
            ctx = _AutoSaveCtx(12, tenant.id, {"x": 1})
            ctx.clear()
            db_ctx = get_context(12, tenant_id=tenant.id)
            assert db_ctx == {}
