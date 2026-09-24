"""Unit tests for services/advanced_trainer.py and training_progress.py."""

from __future__ import annotations

from services.advanced_trainer import AdvancedTrainer
from services.training_progress import (
    get_concept_details,
    get_knowledge_graph_relationships,
    get_learning_velocity,
    get_training_health_report,
    get_training_metrics,
    get_training_progress,
)


def _seed_memory(db_session, tenant_id, key="What is VAT?", value="VAT in UAE is 5 percent tax"):
    from models.ai import AiMemory

    mem = AiMemory(
        key=key,
        value=value,
        category="tax",
        tenant_id=tenant_id,
        confidence=1.0,
        source="quick_learner",
        is_active=True,
    )
    db_session.add(mem)
    db_session.flush()
    return mem


class TestSemanticIndex:
    def test_build_index(self, db_session, sample_tenant):
        _seed_memory(db_session, sample_tenant.id)
        index = AdvancedTrainer().build_semantic_index(sample_tenant.id)
        assert index["total_records"] == 1
        assert "tax" in index["domains"]

    def test_build_index_empty(self, db_session, sample_tenant):
        index = AdvancedTrainer().build_semantic_index(sample_tenant.id)
        assert index["total_records"] == 0

    def test_train_semantic_model(self, db_session, sample_tenant):
        result = AdvancedTrainer().train_semantic_model(sample_tenant.id, "What is VAT?", "VAT in UAE is 5 percent")
        assert result["success"] is True
        assert result["concepts_extracted"] > 0
        assert result["graph_edges_added"] > 0


class TestKnowledgeGraph:
    def test_find_related_concepts(self, db_session, sample_tenant):
        AdvancedTrainer().train_semantic_model(sample_tenant.id, "What is VAT?", "VAT in UAE is 5 percent tax")
        related = AdvancedTrainer().find_related_concepts(sample_tenant.id, "vat")
        assert len(related) > 0

    def test_detect_gaps_empty(self, db_session, sample_tenant):
        gaps = AdvancedTrainer().detect_knowledge_gaps(sample_tenant.id)
        assert gaps == []

    def test_recommendations_empty(self, db_session, sample_tenant):
        recs = AdvancedTrainer().generate_training_recommendations(sample_tenant.id)
        assert recs == []

    def test_recommendations_low_coverage(self, db_session, sample_tenant):
        from models.ai import AiMemory

        mem = AiMemory(
            key="q",
            value="a",
            category="obscure",
            tenant_id=sample_tenant.id,
            confidence=0.1,
            source="quick_learner",
            is_active=True,
        )
        db_session.add(mem)
        db_session.flush()
        recs = AdvancedTrainer().generate_training_recommendations(sample_tenant.id)
        assert any(r["domain"] == "obscure" for r in recs)


class TestExtractConcepts:
    def test_filters_common_words(self):
        concepts = AdvancedTrainer()._extract_concepts("The tax and the VAT are in UAE")
        assert "the" not in concepts
        assert "tax" in concepts

    def test_domain_detection(self):
        t = AdvancedTrainer()
        assert t._extract_domain("vat question", "tax answer") == "tax_customs"
        assert t._extract_domain("invoice?", "customer sale") == "sales"
        assert t._extract_domain("stock?", "warehouse inventory") == "inventory"
        assert t._extract_domain("cheque?", "payment receipt") == "payments"
        assert t._extract_domain("salary?", "employee payroll") == "hr"
        assert t._extract_domain("hello", "world") == "general"

    def test_mastery_score_bounds(self):
        t = AdvancedTrainer()
        assert t._calculate_mastery_score(0, 0.0) == 0
        assert t._calculate_mastery_score(100, 1.0) == 100


class TestTrainingProgress:
    def test_progress_empty(self, db_session, sample_tenant):
        data = get_training_progress(sample_tenant.id)
        assert data["total_concepts"] == 0
        assert data["level"] == "novice"

    def test_progress_after_training(self, db_session, sample_tenant):
        AdvancedTrainer().train_semantic_model(sample_tenant.id, "What is VAT?", "VAT in UAE is 5 percent tax")
        data = get_training_progress(sample_tenant.id)
        assert data["total_concepts"] > 0
        assert data["covered_concepts"] == data["total_concepts"]

    def test_metrics(self, db_session, sample_tenant):
        _seed_memory(db_session, sample_tenant.id)
        metrics = get_training_metrics(sample_tenant.id)
        assert metrics["total_memories"] == 1
        assert metrics["tenant_id"] == sample_tenant.id

    def test_health_report(self, db_session, sample_tenant):
        health = get_training_health_report(sample_tenant.id)
        assert "health_score" in health
        assert health["health_status"] in ("excellent", "good", "fair", "poor")

    def test_concept_details_missing(self, db_session, sample_tenant):
        details = get_concept_details(sample_tenant.id, "nonexistent-xyz")
        assert details["found"] is False

    def test_velocity_empty(self, db_session, sample_tenant):
        vel = get_learning_velocity(sample_tenant.id)
        assert vel["total_concepts"] == 0

    def test_graph_relationships_empty(self, db_session, sample_tenant):
        rels = get_knowledge_graph_relationships(sample_tenant.id)
        assert rels == []
