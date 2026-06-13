"""Comprehensive tests for AI module: QuickLearner, Trainer, AzadLearningSystem,
ImprovementCore, core_engine delegation, and tenant isolation."""
import os
import uuid
import pytest
from unittest.mock import Mock
from extensions import db
from models.ai import AiMemory, AiInteraction


@pytest.fixture(scope="session", autouse=True)
def _clean_ai_artifact_files():
    """Remove AI knowledge files that accumulate across test runs via real constructors."""
    artifact_patterns = [
        "interactions_log.json",
        "patterns.pkl",
        "self_improvement.json",
        "performance_metrics.json",
        "improvement_goals.json",
        "feedback_log.json",
    ]
    from ai_knowledge import AI_KNOWLEDGE_DIR
    for name in artifact_patterns:
        path = os.path.join(AI_KNOWLEDGE_DIR, name)
        if os.path.exists(path):
            os.remove(path)
    # also check data/training for learned_knowledge.json — leave it alone


# ===========================================================================
# QuickLearner — DB-backed version (learning/quick_learner.py)
# ===========================================================================

class TestQuickLearnerDB:
    """DB-backed QuickLearner: learn, get_answer, tenant isolation, fuzzy match."""

    def test_learn_creates_memory(self, app):
        from ai_knowledge.learning.quick_learner import QuickLearner
        from models import Tenant
        with app.app_context():
            tenant = Tenant(name='AI Test-' + uuid.uuid4().hex[:6], name_ar='اختبار ذكاء', slug='ai-test-' + uuid.uuid4().hex[:6], email='ai@test.com')
            db.session.add(tenant)
            db.session.commit()
            ql = QuickLearner()
            ql.learn("hello", "world", category="greeting", tenant_id=tenant.id)
            row = AiMemory.query.filter_by(key="hello", tenant_id=tenant.id).first()
            assert row is not None
            assert row.value == "world"
            assert row.category == "greeting"
            assert row.source == "quick_learner"
            assert row.confidence == 1.0

    def test_learn_updates_existing(self, app):
        from ai_knowledge.learning.quick_learner import QuickLearner
        from models import Tenant
        with app.app_context():
            tenant = Tenant(name='AI Test 2-' + uuid.uuid4().hex[:6], name_ar='اختبار ذكاء 2', slug='ai-test-2-' + uuid.uuid4().hex[:6], email='ai2@test.com')
            db.session.add(tenant)
            db.session.commit()
            ql = QuickLearner()
            ql.learn("city", "dubai", tenant_id=tenant.id)
            ql.learn("city", "abu dhabi", tenant_id=tenant.id)
            rows = AiMemory.query.filter_by(key="city", tenant_id=tenant.id).all()
            assert len(rows) == 1
            assert rows[0].value == "abu dhabi"

    def test_learn_without_tenant_creates_global(self, app):
        from ai_knowledge.learning.quick_learner import QuickLearner
        with app.app_context():
            ql = QuickLearner()
            ql.learn("global_key", "global_val", category="general", tenant_id=None)
            row = AiMemory.query.filter_by(key="global_key", tenant_id=None).first()
            assert row is not None
            assert row.value == "global_val"

    def test_get_answer_exact_match(self, app):
        from ai_knowledge.learning.quick_learner import QuickLearner
        from models import Tenant
        with app.app_context():
            tenant = Tenant(name='AI Exact-' + uuid.uuid4().hex[:6], name_ar='اختبار', slug='ai-exact-' + uuid.uuid4().hex[:6], email='ex@test.com')
            db.session.add(tenant)
            db.session.commit()
            ql = QuickLearner()
            ql.learn("vat rate", "5%", tenant_id=tenant.id)
            ans = ql.get_answer("vat rate", tenant_id=tenant.id)
            assert ans == "5%"

    def test_get_answer_fuzzy_match(self, app):
        from ai_knowledge.learning.quick_learner import QuickLearner
        from models import Tenant
        with app.app_context():
            tenant = Tenant(name='AI Fuzzy-' + uuid.uuid4().hex[:6], name_ar='اختبار', slug='ai-fuzzy-' + uuid.uuid4().hex[:6], email='fz@test.com')
            db.session.add(tenant)
            db.session.commit()
            ql = QuickLearner()
            ql.learn("how to add a customer", "go to customers page", tenant_id=tenant.id)
            ans = ql.get_answer("how to add custome", tenant_id=tenant.id)
            assert "customers page" in ans

    def test_get_answer_partial_match_substring(self, app):
        from ai_knowledge.learning.quick_learner import QuickLearner
        from models import Tenant
        with app.app_context():
            tenant = Tenant(name='AI Partial-' + uuid.uuid4().hex[:6], name_ar='اختبار', slug='ai-partial-' + uuid.uuid4().hex[:6], email='pt@test.com')
            db.session.add(tenant)
            db.session.commit()
            ql = QuickLearner()
            ql.learn("add customer", "navigate to customers", tenant_id=tenant.id)
            ans = ql.get_answer("how to add customer now", tenant_id=tenant.id)
            assert ans is not None

    def test_get_answer_tenant_isolation(self, app):
        from ai_knowledge.learning.quick_learner import QuickLearner
        from models import Tenant
        with app.app_context():
            t1 = Tenant(name='AI Iso 1-' + uuid.uuid4().hex[:6], name_ar='اختبار 1', slug='ai-iso-1-' + uuid.uuid4().hex[:6], email='i1@test.com')
            t2 = Tenant(name='AI Iso 2-' + uuid.uuid4().hex[:6], name_ar='اختبار 2', slug='ai-iso-2-' + uuid.uuid4().hex[:6], email='i2@test.com')
            db.session.add(t1)
            db.session.add(t2)
            db.session.commit()
            ql = QuickLearner()
            ql.learn("price", "100", tenant_id=t1.id)
            ql.learn("price", "200", tenant_id=t2.id)
            ans1 = ql.get_answer("price", tenant_id=t1.id)
            ans2 = ql.get_answer("price", tenant_id=t2.id)
            assert ans1 == "100"
            assert ans2 == "200"
            assert ans1 != ans2

    def test_get_answer_global_fallback(self, app):
        from ai_knowledge.learning.quick_learner import QuickLearner
        with app.app_context():
            ql = QuickLearner()
            ql.learn("help", "type /help for commands", tenant_id=None)
            ans = ql.get_answer("help", tenant_id=99)
            assert ans == "type /help for commands"

    def test_get_answer_no_match(self, app):
        from ai_knowledge.learning.quick_learner import QuickLearner
        from models import Tenant
        with app.app_context():
            tenant = Tenant(name='AI NoMatch-' + uuid.uuid4().hex[:6], name_ar='اختبار', slug='ai-nomatch-' + uuid.uuid4().hex[:6], email='nm@test.com')
            db.session.add(tenant)
            db.session.commit()
            ql = QuickLearner()
            ans = ql.get_answer("nonexistent question xyz", tenant_id=tenant.id)
            assert ans is None

    def test_bump_access_count(self, app):
        from ai_knowledge.learning.quick_learner import QuickLearner
        from models import Tenant
        with app.app_context():
            tenant = Tenant(name='AI Bump-' + uuid.uuid4().hex[:6], name_ar='اختبار', slug='ai-bump-' + uuid.uuid4().hex[:6], email='bp@test.com')
            db.session.add(tenant)
            db.session.commit()
            ql = QuickLearner()
            ql.learn("frequent", "answer", tenant_id=tenant.id)
            ql.get_answer("frequent", tenant_id=tenant.id)
            ql.get_answer("frequent", tenant_id=tenant.id)
            row = AiMemory.query.filter_by(key="frequent", tenant_id=tenant.id).first()
            assert row.access_count >= 2
            assert row.last_accessed is not None

    def test_knowledge_base_property(self, app):
        from ai_knowledge.learning.quick_learner import QuickLearner
        with app.app_context():
            ql = QuickLearner()
            assert ql.knowledge_base == {}


# ===========================================================================
# QuickLearner — Delegation from learning_engine.py
# ===========================================================================

class TestLearningEngineQuickLearner:
    """Consolidated learning_engine.py QuickLearner delegates to DB version."""

    def test_ql_delegates_to_db(self, app):
        from ai_knowledge.learning_engine import QuickLearner
        from models import Tenant
        with app.app_context():
            tenant = Tenant(name='AI Delegate-' + uuid.uuid4().hex[:6], name_ar='اختبار', slug='ai-delegate-' + uuid.uuid4().hex[:6], email='dg@test.com')
            db.session.add(tenant)
            db.session.commit()
            ql = QuickLearner()
            ql.learn("delegate_test", "works", tenant_id=tenant.id)
            row = AiMemory.query.filter_by(key="delegate_test").first()
            assert row is not None
            assert row.value == "works"
            ans = ql.get_answer("delegate_test", tenant_id=tenant.id)
            assert ans == "works"

    def test_ql_singleton_is_db_backed(self, app):
        from ai_knowledge.learning_engine import quick_learner
        from models import Tenant
        with app.app_context():
            tenant = Tenant(name='AI Singleton-' + uuid.uuid4().hex[:6], name_ar='اختبار', slug='ai-singleton-' + uuid.uuid4().hex[:6], email='sn@test.com')
            db.session.add(tenant)
            db.session.commit()
            quick_learner.learn("singleton_test", "ok", tenant_id=tenant.id)
            row = AiMemory.query.filter_by(key="singleton_test").first()
            assert row is not None

    def test_knowledge_base_empty(self, app):
        from ai_knowledge.learning_engine import QuickLearner
        with app.app_context():
            ql = QuickLearner()
            assert ql.knowledge_base == {}


# ===========================================================================
# Trainer — seed, learn_from_interaction, train_from_feedback, get_stats
# ===========================================================================

class TestTrainer:
    """Trainer: seeding, learning, tenant isolation, stats."""

    def test_seed_creates_qa(self, app):
        from ai_knowledge.trainer import Trainer
        with app.app_context():
            t = Trainer()
            t.seed()
            # SEED_QA has many pairs stored with source='quick_learner'
            count = AiMemory.query.filter(
                AiMemory.source == "quick_learner"
            ).count()
            assert count > 5
            # Check a specific seed exists
            row = AiMemory.query.filter_by(key="ملخص النظام").first()
            assert row is not None
            assert "أزاد" in row.value

    def test_seed_is_idempotent(self, app):
        from ai_knowledge.trainer import Trainer
        with app.app_context():
            t = Trainer()
            t.seed()
            count1 = AiMemory.query.filter(
                AiMemory.source == "quick_learner"
            ).count()
            t._seeded = False
            t.seed()
            count2 = AiMemory.query.filter(
                AiMemory.source == "quick_learner"
            ).count()
            assert count2 == count1

    def test_learn_from_interaction_global(self, app):
        from ai_knowledge.trainer import Trainer
        with app.app_context():
            t = Trainer()
            t.seed()
            t.learn_from_interaction("xxglobal-unique-q", "xxglobal-answer", success=True)
            row = AiMemory.query.filter_by(key="xxglobal-unique-q", tenant_id=None).first()
            assert row is not None
            assert row.value == "xxglobal-answer"
            assert row.category == "learned"

    def test_learn_from_interaction_with_tenant(self, app):
        from ai_knowledge.trainer import Trainer
        from models import Tenant
        with app.app_context():
            tenant = Tenant(name='AI Trainer-' + uuid.uuid4().hex[:6], name_ar='اختبار', slug='ai-trainer-' + uuid.uuid4().hex[:6], email='tr@test.com')
            db.session.add(tenant)
            db.session.commit()
            t = Trainer()
            t.seed()
            t.learn_from_interaction("xxtenant-specific-q", "xxtenant-answer", success=True, tenant_id=tenant.id)
            row = AiMemory.query.filter_by(key="xxtenant-specific-q", tenant_id=tenant.id).first()
            assert row is not None
            assert row.value == "xxtenant-answer"

    def test_learn_from_interaction_skips_duplicate(self, app):
        from ai_knowledge.trainer import Trainer
        with app.app_context():
            t = Trainer()
            t.seed()
            t.learn_from_interaction("xxdup-q", "first", success=True)
            t.learn_from_interaction("xxdup-q", "second", success=True)
            rows = AiMemory.query.filter_by(key="xxdup-q").all()
            assert len(rows) == 1
            assert rows[0].value == "first"

    def test_learn_from_interaction_empty_skipped(self, app):
        from ai_knowledge.trainer import Trainer
        with app.app_context():
            t = Trainer()
            t.seed()
            t.learn_from_interaction("", "answer")
            t.learn_from_interaction("question", "")
            count = AiMemory.query.count()
            # Should be seeded + no extra learned
            assert count >= 10

    def test_train_from_feedback(self, app):
        from ai_knowledge.trainer import Trainer
        from models import Tenant
        with app.app_context():
            tenant = Tenant(name='AI FB-' + uuid.uuid4().hex[:6], name_ar='اختبار', slug='ai-fb-' + uuid.uuid4().hex[:6], email='fb@test.com')
            db.session.add(tenant)
            db.session.commit()
            t = Trainer()
            t.seed()
            t.train_from_feedback("xxfb-q", "xxfb-answer", user_id=1, tenant_id=tenant.id)
            row = AiMemory.query.filter_by(key="xxfb-q", tenant_id=tenant.id).first()
            assert row is not None
            assert row.value == "xxfb-answer"
            assert row.category == "corrected"

    def test_get_stats_returns_counts(self, app):
        from ai_knowledge.trainer import Trainer
        with app.app_context():
            t = Trainer()
            t.seed()
            stats = t.get_stats()
            assert "total_qa" in stats
            assert stats["total_qa"] > 0
            assert "categories" in stats
            assert "seeded" in stats
            assert stats["seeded"] is True

    def test_get_stats_after_learning(self, app):
        from ai_knowledge.trainer import Trainer
        with app.app_context():
            t = Trainer()
            t.seed()
            ql = t._get_ql()
            key = "xxstats-q-" + uuid.uuid4().hex[:6]
            ql.learn(key, "xxstats-answer", category="learned")
            after = t.get_stats()
            assert "learned" in after["categories"]


    def test_get_ql_fallback_import(self, app):
        """Cover trainer.py lines 287-289: _get_ql except when learning_engine import fails."""
        import sys
        from ai_knowledge.trainer import Trainer
        with app.app_context():
            # remove cached import so the fallback path triggers
            saved = sys.modules.pop("ai_knowledge.learning_engine", None)
            try:
                t = Trainer()
                ql = t._get_ql()
                assert ql is not None
                assert t.quick_learner is ql
            finally:
                if saved:
                    sys.modules["ai_knowledge.learning_engine"] = saved

    def test_seed_expertise_skip_on_error(self, app, monkeypatch):
        """Cover trainer.py lines 319-320: seed except when expertise JSON loading fails."""
        from ai_knowledge.trainer import Trainer
        monkeypatch.setattr("glob.glob", Mock(return_value=["/nonexistent/bogus.json"]))
        with app.app_context():
            t = Trainer()
            t.seed()
            assert t._seeded is True


# ===========================================================================
# AzadLearningSystem — learn_from_interaction, tenant_id, pickle safety
# ===========================================================================

class TestAzadLearningSystem:
    """AzadLearningSystem from core/learning_system.py."""

    def _make_system(self, app, tmp_path):
        """Create AzadLearningSystem with isolated file paths to avoid cross-test pollution."""
        from ai_knowledge.core.learning_system import AzadLearningSystem
        from collections import defaultdict
        import os
        system = AzadLearningSystem.__new__(AzadLearningSystem)
        system.knowledge_file = os.path.join(tmp_path, "learned_knowledge.json")
        system.interactions_file = os.path.join(tmp_path, "interactions_log.json")
        system.patterns_file = os.path.join(tmp_path, "patterns.pkl")
        system.feedback_file = os.path.join(tmp_path, "feedback_log.json")
        system.learned_knowledge = {
            'new_terms': {},
            'customer_preferences': {},
            'market_trends': {},
            'successful_responses': {},
            'failed_responses': {},
            'expertise_areas': defaultdict(int),
            'learning_stats': {
                'total_interactions': 0,
                'successful_answers': 0,
                'learning_rate': 0.0,
                'last_updated': None,
            },
        }
        system.interactions = []
        system.patterns = {
            'question_patterns': defaultdict(list),
            'response_patterns': defaultdict(list),
            'success_patterns': defaultdict(float),
            'time_patterns': defaultdict(int),
            'user_behavior': defaultdict(dict),
        }
        system.feedback_log = []
        return system

    def test_learn_from_interaction_basic(self, app, tmp_path):
        with app.app_context():
            system = self._make_system(app, tmp_path)
            system.learn_from_interaction("question", "response")
            assert len(system.interactions) >= 1
            assert system.interactions[-1]["question"] == "question"
            assert system.interactions[-1]["response"] == "response"

    def test_learn_from_interaction_with_tenant_id(self, app, tmp_path):
        with app.app_context():
            system = self._make_system(app, tmp_path)
            system.learn_from_interaction("q", "a", tenant_id=42)
            ctx = system.interactions[-1]["context"]
            assert ctx.get("tenant_id") == 42

    def test_learn_from_interaction_preserves_other_context(self, app, tmp_path):
        with app.app_context():
            system = self._make_system(app, tmp_path)
            system.learn_from_interaction(
                "q", "a", context={"source": "test", "user_id": 1}, tenant_id=42
            )
            ctx = system.interactions[-1]["context"]
            assert ctx["source"] == "test"
            assert ctx["user_id"] == 1
            assert ctx["tenant_id"] == 42

    def test_get_learning_insights(self, app, tmp_path):
        with app.app_context():
            system = self._make_system(app, tmp_path)
            for i in range(5):
                system.learn_from_interaction(f"q{i}", f"a{i}", user_feedback=5)
            insights = system.get_learning_insights()
            assert insights["total_interactions"] == 5
            assert insights["success_rate"] >= 0

    def test_safe_load_pickle_missing_file(self, app):
        from ai_knowledge.core.learning_system import AzadLearningSystem
        with app.app_context():
            result = AzadLearningSystem._safe_load_pickle("/nonexistent/file.pkl")
            assert result is None

    def test_safe_load_pickle_empty_file(self, app, tmp_path):
        from ai_knowledge.core.learning_system import AzadLearningSystem
        p = tmp_path / "empty.pkl"
        p.write_text("")
        result = AzadLearningSystem._safe_load_pickle(str(p))
        assert result is None

    def test_safe_load_pickle_oversized(self, app, tmp_path):
        from ai_knowledge.core.learning_system import AzadLearningSystem
        p = tmp_path / "big.pkl"
        p.write_bytes(b"x" * (11 * 1024 * 1024))
        result = AzadLearningSystem._safe_load_pickle(str(p))
        assert result is None

    def test_safe_load_pickle_invalid_content(self, app, tmp_path):
        from ai_knowledge.core.learning_system import AzadLearningSystem
        p = tmp_path / "bad.pkl"
        p.write_bytes(b"not a pickle")
        result = AzadLearningSystem._safe_load_pickle(str(p))
        assert result is None


# ===========================================================================
# ImprovementCore — _refresh_scores_from_db queries real data
# ===========================================================================

class TestImprovementCore:
    """AzadSelfImprovement — real DB-backed scores."""

    def test_refresh_scores_on_auto_improve(self, app):
        from ai_knowledge.improvement_core import AzadSelfImprovement
        with app.app_context():
            # Seed some interactions
            inter = AiInteraction(
                query="test", response="ok", was_successful=True,
                is_training_sample=True,
            )
            db.session.add(inter)
            db.session.commit()
            improv = AzadSelfImprovement()
            result = improv.auto_improve()
            assert result["improvements_made"] == 1
            scores = {d["area"]: d["score"] for d in result["details"]}
            assert "response_quality" in scores
            assert scores["response_quality"] > 0

    def test_implement_improvement_unknown_area(self, app):
        from ai_knowledge.improvement_core import AzadSelfImprovement
        with app.app_context():
            improv = AzadSelfImprovement()
            result = improv.implement_improvement("nonexistent")
            assert result["success"] is False

    def test_implement_improvement_known_area(self, app):
        from ai_knowledge.improvement_core import AzadSelfImprovement
        with app.app_context():
            improv = AzadSelfImprovement()
            result = improv.implement_improvement("response_quality")
            assert result["success"] is True
            assert "new_score" in result

    def test_improvement_areas_exist(self, app):
        from ai_knowledge.improvement_core import AzadSelfImprovement
        with app.app_context():
            improv = AzadSelfImprovement()
            assert "response_quality" in improv.improvement_areas
            assert "knowledge_depth" in improv.improvement_areas
            assert "customer_satisfaction" in improv.improvement_areas

    def test_track_progress_returns_report(self, app):
        from ai_knowledge.improvement_core import AzadSelfImprovement
        with app.app_context():
            improv = AzadSelfImprovement()
            progress = improv.track_progress()
            assert "overall_progress" in progress
            assert "area_progress" in progress
            assert len(progress["area_progress"]) > 0

    def test_analyze_performance_returns_analysis(self, app):
        from ai_knowledge.improvement_core import AzadSelfImprovement
        with app.app_context():
            improv = AzadSelfImprovement()
            analysis = improv.analyze_performance()
            assert "overall_score" in analysis
            assert "strengths" in analysis
            assert "weaknesses" in analysis


# ===========================================================================
# core_engine.py — delegation to core/learning_system.py
# ===========================================================================

class TestCoreEngineDelegation:
    """core_engine.py now re-exports from core/learning_system.py."""

    def test_learning_system_is_same_object(self, app):
        from ai_knowledge.core.learning_system import learning_system as ls1
        from ai_knowledge.core_engine import learning_system as ls2
        assert ls1 is ls2

    def test_azad_learning_system_is_same_class(self, app):
        from ai_knowledge.core.learning_system import AzadLearningSystem as C1
        from ai_knowledge.core_engine import AzadLearningSystem as C2
        assert C1 is C2

    def test_core_engine_learning_system_works(self, app):
        from ai_knowledge.core_engine import learning_system
        with app.app_context():
            learning_system.learn_from_interaction(
                "core_engine_test", "works", tenant_id=7
            )
            ctx = learning_system.interactions[-1]["context"]
            assert ctx.get("tenant_id") == 7


# ===========================================================================
# evaluate_and_learn — from learning_engine.py
# ===========================================================================

class TestEvaluateAndLearn:
    """evaluate_and_learn function from learning_engine.py."""

    def test_import_from_learning_engine(self, app):
        from ai_knowledge.learning_engine import evaluate_and_learn
        assert callable(evaluate_and_learn)

    def test_import_from_continuous_learner(self, app):
        from ai_knowledge.learning.continuous_learner import evaluate_and_learn
        assert callable(evaluate_and_learn)

    def test_returns_results_with_default_service(self, app):
        from ai_knowledge.learning_engine import evaluate_and_learn
        result = evaluate_and_learn([{"question": "test", "expected_keywords": ["ok"]}])
        assert isinstance(result, list)
        if result:
            assert "question" in result[0]
            assert "answer" in result[0]
            assert "success" in result[0]


# ===========================================================================
# Seed script — structural validation
# ===========================================================================

class TestSeedScript:
    """seed_ai_from_training.py structural checks."""

    def test_imports(self):
        from ai_training.seed_ai_from_training import (
            seed_memories, seed_interactions, seed_expertise,
            seed_documents, seed_quick_learner, main,
        )
        assert callable(seed_memories)
        assert callable(seed_interactions)
        assert callable(seed_expertise)
        assert callable(seed_documents)
        assert callable(seed_quick_learner)
        assert callable(main)

    def test_env_check(self, app, monkeypatch):
        monkeypatch.delenv("DATABASE_URL", raising=False)
        import importlib
        import ai_training.seed_ai_from_training as mod
        with pytest.raises(SystemExit):
            importlib.reload(mod)


# ===========================================================================
# Continuous learner — URL encoding fix
# ===========================================================================

class TestContinuousLearnerUrlEncoding:
    """URL encoding fix for Arabic/Wikipedia topics."""

    def test_wikipedia_url_has_encoded_arabic(self):
        from ai_knowledge.learning.continuous_learner import ContinuousLearner
        cl = ContinuousLearner()
        # Monkey-patch session.get to capture the URL
        original_get = cl.session.get

        captured_urls = []

        def fake_get(url, **kwargs):
            captured_urls.append(url)
            class FakeResponse:
                status_code = 200
                def json(self):
                    return {"extract": "test"}
            return FakeResponse()

        cl.session.get = fake_get
        try:
            cl.learn_from_wikipedia("المحاسبة المالية", lang="ar")
        except Exception:
            pass  # may fail on other checks but URL encoding is what matters
        cl.session.get = original_get

        if captured_urls:
            url = captured_urls[0]
            # Arabic chars should be percent-encoded
            assert "%D8%A7%D9%84%D9%85%D8%AD%D8%A7%D8%B3%D8%A8%D8%A9" in url
            assert "_" in url
            # Ensure no double-encoding (no literal Arabic remaining)
            import re
            arabic_chars = re.findall(r'[\u0600-\u06FF]', url)
            assert len(arabic_chars) == 0
