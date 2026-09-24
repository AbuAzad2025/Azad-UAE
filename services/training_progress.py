"""
Training Progress — KPIs, coverage metrics, and mastery tracking.
"""

import logging
from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

from extensions import db
from models.ai import AiMemory
from models.ai_training_advanced import AiKnowledgeGraph, AiTrainingProgress
from services.advanced_trainer import AdvancedTrainer
from utils.tenanting import tenant_query

logger = logging.getLogger(__name__)

advanced_trainer = AdvancedTrainer()


def get_training_progress(tenant_id: int, domain: str = "") -> dict[str, Any]:
    """Get training progress for a tenant with optional domain filter."""
    query = tenant_query(AiTrainingProgress).filter(AiTrainingProgress.tenant_id == int(tenant_id))

    if domain:
        query = query.filter(AiTrainingProgress.domain == domain)

    records = query.all()

    # Calculate statistics
    total = len(records)
    covered = sum(1 for r in records if r.covered)
    not_covered = total - covered
    avg_mastery = sum(r.mastery_score for r in records) / total if total > 0 else 0
    avg_confidence = sum(float(r.confidence) for r in records) / total if total > 0 else 0.0
    avg_velocity = sum(float(r.learning_velocity) for r in records) / total if total > 0 else 0.0

    # Group by domain
    by_domain: dict[str, dict[str, Any]] = defaultdict(lambda: {"total": 0, "covered": 0, "avg_mastery": 0.0})
    for r in records:
        by_domain[r.domain]["total"] += 1
        if r.covered:
            by_domain[r.domain]["covered"] += 1
        by_domain[r.domain]["avg_mastery"] += r.mastery_score

    for domain_data in by_domain.values():
        if domain_data["total"] > 0:
            domain_data["avg_mastery"] /= domain_data["total"]
            domain_data["coverage"] = domain_data["covered"] / domain_data["total"] * 100
        else:
            domain_data["coverage"] = 0.0

    # Determine overall level
    if avg_mastery >= 80:
        level = "expert"
    elif avg_mastery >= 60:
        level = "advanced"
    elif avg_mastery >= 40:
        level = "intermediate"
    elif avg_mastery >= 20:
        level = "beginner"
    else:
        level = "novice"

    return {
        "tenant_id": tenant_id,
        "total_concepts": total,
        "covered_concepts": covered,
        "not_covered_concepts": not_covered,
        "coverage_percentage": round(covered / total * 100, 2) if total > 0 else 0.0,
        "average_mastery_score": round(avg_mastery, 2),
        "average_confidence": round(avg_confidence, 4),
        "average_learning_velocity": round(avg_velocity, 4),
        "level": level,
        "by_domain": dict(by_domain),
        "records": [r.to_dict() for r in records[:100]],  # Top 100
    }


def get_training_metrics(tenant_id: int) -> dict[str, Any]:
    """Get comprehensive training metrics across all domains."""
    # Get domain statistics from advanced trainer
    domain_stats = advanced_trainer.get_domain_statistics(tenant_id)

    # Add knowledge graph stats
    knowledge_graph = tenant_query(AiKnowledgeGraph).filter(AiKnowledgeGraph.tenant_id == int(tenant_id)).all()

    # Count unique concepts and relationships
    unique_concepts = set()
    for edge in knowledge_graph:
        unique_concepts.add(edge.source_concept)
        unique_concepts.add(edge.target_concept)

    # Get memory stats
    memories = tenant_query(AiMemory).filter(AiMemory.tenant_id == int(tenant_id)).all()

    # Calculate velocity trend (last 30 days vs previous 30 days)
    now = datetime.now(UTC)
    recent_memories = [m for m in memories if m.created_at and (now - m.created_at).days <= 30]
    previous_memories = [m for m in memories if m.created_at and 30 < (now - m.created_at).days <= 60]

    velocity = len(recent_memories) / 30 if recent_memories else 0.0
    previous_velocity = len(previous_memories) / 30 if previous_memories else 0.0

    return {
        "tenant_id": tenant_id,
        "total_memories": len(memories),
        "active_memories": sum(1 for m in memories if m.is_active),
        "total_concepts": len(unique_concepts),
        "knowledge_graph_edges": len(knowledge_graph),
        "average_confidence": domain_stats.get("average_confidence", 0.0),
        "average_mastery_score": domain_stats.get("average_mastery_score", 0.0),
        "coverage_percentage": domain_stats.get("coverage_percentage", 0.0),
        "learning_velocity": round(velocity, 4),
        "previous_velocity": round(previous_velocity, 4),
        "velocity_trend": "improving"
        if velocity > previous_velocity
        else ("declining" if velocity < previous_velocity else "stable"),
        "domain_stats": domain_stats.get("domain_stats", {}),
        "level": domain_stats.get("level", "novice"),
        "last_updated": datetime.now(UTC).isoformat(),
    }


def get_concept_details(tenant_id: int, concept_name: str) -> dict[str, Any]:
    """Get detailed information about a specific concept."""
    # Get progress records for this concept
    progress_records = (
        tenant_query(AiTrainingProgress)
        .filter(
            AiTrainingProgress.tenant_id == int(tenant_id),
            AiTrainingProgress.concept_name == concept_name,
        )
        .all()
    )

    if not progress_records:
        return {
            "concept": concept_name,
            "found": False,
            "message": "No training data found for this concept.",
        }

    # Get related knowledge graph edges
    graph_edges = (
        tenant_query(AiKnowledgeGraph)
        .filter(
            AiKnowledgeGraph.tenant_id == int(tenant_id),
            (AiKnowledgeGraph.source_concept == concept_name) | (AiKnowledgeGraph.target_concept == concept_name),
        )
        .all()
    )

    # Get related memories
    related_memories = (
        tenant_query(AiMemory)
        .filter(
            AiMemory.tenant_id == int(tenant_id),
            AiMemory.is_active.is_(True),
        )
        .filter(
            db.or_(
                AiMemory.key.ilike(f"%{concept_name}%"),
                AiMemory.value.ilike(f"%{concept_name}%"),
            )
        )
        .all()
    )

    # Calculate stats
    avg_mastery = sum(r.mastery_score for r in progress_records) / len(progress_records)
    avg_confidence = sum(float(r.confidence) for r in progress_records) / len(progress_records)
    avg_usage = sum(r.usage_count for r in progress_records) / len(progress_records)

    return {
        "concept": concept_name,
        "found": True,
        "total_records": len(progress_records),
        "average_mastery_score": round(avg_mastery, 2),
        "average_confidence": round(avg_confidence, 4),
        "average_usage_count": round(avg_usage, 2),
        "knowledge_graph_edges": [e.to_dict() for e in graph_edges],
        "related_memories": [m.to_dict() for m in related_memories[:10]],
    }


def get_learning_velocity(tenant_id: int) -> dict[str, Any]:
    """Calculate learning velocity for the tenant."""
    progress_records = tenant_query(AiTrainingProgress).filter(AiTrainingProgress.tenant_id == int(tenant_id)).all()

    if not progress_records:
        return {"velocity": 0.0, "trend": "unknown", "total_concepts": 0}

    # Group by week
    from collections import defaultdict

    weekly: dict[int, int] = defaultdict(int)
    for r in progress_records:
        if r.updated_at:
            week = r.updated_at.isocalendar()[1]
            weekly[week] += 1

    # Calculate velocity
    weeks_with_data = len(weekly)
    total_concepts = sum(weekly.values())
    avg_velocity = total_concepts / weeks_with_data if weeks_with_data > 0 else 0.0

    # Determine trend
    sorted_weeks = sorted(weekly.keys())
    if len(sorted_weeks) >= 2:
        recent_avg = sum(weekly[w] for w in sorted_weeks[-2:]) / min(2, len(sorted_weeks))
        previous_avg = sum(weekly[w] for w in sorted_weeks[:-2]) / max(1, len(sorted_weeks) - 2)
        trend = "improving" if recent_avg > previous_avg else ("declining" if recent_avg < previous_avg else "stable")
    else:
        trend = "stable"

    return {
        "velocity": round(avg_velocity, 4),
        "trend": trend,
        "total_concepts": total_concepts,
        "weeks_with_data": weeks_with_data,
        "weekly_breakdown": {str(k): v for k, v in weekly.items()},
    }


def get_knowledge_graph_relationships(tenant_id: int, concept: str = "") -> list[dict[str, Any]]:
    """Get knowledge graph relationships for a tenant."""
    query = tenant_query(AiKnowledgeGraph).filter(AiKnowledgeGraph.tenant_id == int(tenant_id))

    if concept:
        query = query.filter(
            db.or_(
                AiKnowledgeGraph.source_concept.ilike(f"%{concept}%"),
                AiKnowledgeGraph.target_concept.ilike(f"%{concept}%"),
            )
        )

    edges = query.all()
    return [e.to_dict() for e in edges]


def get_training_health_report(tenant_id: int) -> dict[str, Any]:
    """Generate a comprehensive training health report."""
    progress = get_training_progress(tenant_id)
    metrics = get_training_metrics(tenant_id)

    # Calculate health score (0-100)
    coverage = progress.get("coverage_percentage", 0.0)
    mastery = progress.get("average_mastery_score", 0.0)
    velocity = metrics.get("learning_velocity", 0.0)
    concept_count = progress.get("total_concepts", 0)

    health_score = round((coverage * 0.4) + (mastery * 0.3) + (min(velocity * 10, 30) * 0.3), 2)

    # Determine health status
    if health_score >= 80:
        health_status = "excellent"
    elif health_score >= 60:
        health_status = "good"
    elif health_score >= 40:
        health_status = "fair"
    else:
        health_status = "poor"

    # Generate recommendations
    recommendations = []
    if coverage < 50:
        recommendations.append(
            {
                "priority": "high",
                "message": f"Low coverage ({coverage:.1f}%). Add more training data.",
            }
        )
    if mastery < 60:
        recommendations.append(
            {
                "priority": "medium",
                "message": f"Low mastery ({mastery:.1f}%). Focus on high-impact concepts.",
            }
        )
    if velocity < 1.0:
        recommendations.append(
            {
                "priority": "low",
                "message": "Learning velocity is low. Increase training frequency.",
            }
        )

    return {
        "tenant_id": tenant_id,
        "health_score": health_score,
        "health_status": health_status,
        "coverage_percentage": coverage,
        "average_mastery_score": mastery,
        "learning_velocity": velocity,
        "total_concepts": concept_count,
        "active_memories": metrics.get("total_memories", 0),
        "recommendations": recommendations,
        "generated_at": datetime.now(UTC).isoformat(),
    }
