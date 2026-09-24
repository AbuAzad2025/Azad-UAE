"""
Advanced Trainer — Semantic matching, neural training, and knowledge graph building.
"""

import logging
from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

from extensions import db
from models.ai import AiMemory
from models.ai_training_advanced import (
    AiKnowledgeGraph,
    AiTrainingProgress,
)
from utils.tenanting import tenant_query

logger = logging.getLogger(__name__)

# Thresholds for semantic training
MIN_CONFIDENCE = 0.7
SEMANTIC_SIMILARITY_THRESHOLD = 0.85
MASTERY_THRESHOLD = 80
PROGRESS_THRESHOLD = 0.5


class AdvancedTrainer:
    """Advanced training with semantic matching, knowledge graphs, and progress tracking."""

    def __init__(self):
        self._concept_cache: dict[str, list[str]] = defaultdict(list)
        self._domain_cache: dict[str, list[str]] = defaultdict(list)

    def build_semantic_index(self, tenant_id: int) -> dict[str, Any]:
        """Build semantic index from tenant's AiMemory records."""
        memories = (
            tenant_query(AiMemory).filter(AiMemory.tenant_id == int(tenant_id), AiMemory.is_active.is_(True)).all()
        )

        index: dict[str, Any] = {
            "total_records": len(memories),
            "domains": defaultdict(int),
            "top_concepts": [],
            "similar_pairs": [],
        }

        # Build domain index
        for mem in memories:
            domain = mem.category or "general"
            index["domains"][domain] += 1

            # Extract key concepts from values (simple heuristic)
            concepts = self._extract_concepts(mem.value)
            for concept in concepts:
                self._concept_cache[concept].append(mem.key)
                index["domains"][f"concept:{concept}"] += 1

        # Find similar pairs using simple Jaccard similarity
        similar_pairs = self._find_similar_pairs(memories)
        index["similar_pairs"] = similar_pairs

        # Sort domains by frequency
        index["domains"] = dict(sorted(index["domains"].items(), key=lambda x: x[1], reverse=True))

        # Top concepts by frequency
        concept_freq: dict[str, int] = defaultdict(int)
        for concepts in self._concept_cache.values():
            for c in concepts:
                concept_freq[c] += 1
        index["top_concepts"] = sorted(concept_freq.items(), key=lambda x: x[1], reverse=True)[:20]

        logger.info(
            f"Built semantic index for tenant {tenant_id}: "
            f"{index['total_records']} records, "
            f"{len(index['domains'])} domains"
        )

        return index

    def train_semantic_model(self, tenant_id: int, question: str, answer: str) -> dict[str, Any]:
        """Train semantic model from a Q&A pair with embedding-like similarity."""
        # Create memory entry
        mem = AiMemory(
            tenant_id=tenant_id,
            key=question.lower()[:255],
            value=answer[:4000],
            category="learned",
            confidence=1.0,
            source="semantic_training",
            is_active=True,
        )
        db.session.add(mem)
        db.session.flush()

        # Build knowledge graph edge for this concept
        concepts = self._extract_concepts(answer)
        for concept in concepts[:5]:  # Limit to 5 concepts
            graph_edge = AiKnowledgeGraph(
                tenant_id=tenant_id,
                source_concept=concept,
                target_concept=question[:100],  # Question is target
                relationship_type="example_of",
                strength=0.9,
            )
            db.session.add(graph_edge)

        db.session.flush()

        # Update semantic index
        self._update_semantic_cache(tenant_id, question, answer)

        # Track mastery progress
        self._update_mastery_progress(tenant_id, question, answer)

        logger.info(f"Semantic training completed for tenant {tenant_id}: {len(concepts)} concepts extracted")

        return {
            "success": True,
            "memory_id": mem.id,
            "concepts_extracted": len(concepts),
            "graph_edges_added": len(concepts[:5]),
        }

    def find_related_concepts(self, tenant_id: int, query_concept: str) -> list[dict[str, Any]]:
        """Find related concepts in the knowledge graph."""
        edges = (
            tenant_query(AiKnowledgeGraph)
            .filter(
                AiKnowledgeGraph.tenant_id == int(tenant_id),
                AiKnowledgeGraph.source_concept.ilike(f"%{query_concept}%"),
            )
            .all()
        )

        results = []
        for edge in edges:
            results.append(
                {
                    "source": edge.source_concept,
                    "target": edge.target_concept,
                    "relationship": edge.relationship_type,
                    "strength": float(edge.strength),
                }
            )

        # Also search reverse edges
        reverse_edges = (
            tenant_query(AiKnowledgeGraph)
            .filter(
                AiKnowledgeGraph.tenant_id == int(tenant_id),
                AiKnowledgeGraph.target_concept.ilike(f"%{query_concept}%"),
            )
            .all()
        )
        for edge in reverse_edges:
            results.append(
                {
                    "source": edge.source_concept,
                    "target": edge.target_concept,
                    "relationship": f"reverse_{edge.relationship_type}",
                    "strength": float(edge.strength),
                }
            )

        return results

    def detect_knowledge_gaps(self, tenant_id: int) -> list[dict[str, Any]]:
        """Detect gaps in knowledge based on concept relationships."""
        # Get all active knowledge graph edges for this tenant
        edges = tenant_query(AiKnowledgeGraph).filter(AiKnowledgeGraph.tenant_id == int(tenant_id)).all()

        # Get all active memories
        memories = (
            tenant_query(AiMemory).filter(AiMemory.tenant_id == int(tenant_id), AiMemory.is_active.is_(True)).all()
        )

        if not edges or not memories:
            return []

        # Find concepts that are prerequisites but not covered
        covered_concepts = set()
        for mem in memories:
            covered_concepts.update(self._extract_concepts(mem.value))

        gaps = []
        for edge in edges:
            if edge.source_concept not in covered_concepts and edge.strength > 0.7:
                gaps.append(
                    {
                        "source": edge.source_concept,
                        "target": edge.target_concept,
                        "relationship": edge.relationship_type,
                        "gap_type": "prerequisite_missing",
                        "recommendation": (
                            f"Add training data for '{edge.source_concept}' to understand '{edge.target_concept}'"
                        ),
                    }
                )

        logger.info(f"Knowledge gaps detected for tenant {tenant_id}: {len(gaps)} gaps")
        return gaps

    def generate_training_recommendations(self, tenant_id: int) -> list[dict[str, Any]]:
        """Generate personalized training recommendations based on usage patterns."""
        # Get usage statistics
        memories = tenant_query(AiMemory).filter(AiMemory.tenant_id == int(tenant_id)).all()

        if not memories:
            return []

        recommendations = []

        # Analyze by domain
        domain_stats: dict[str, dict[str, Any]] = defaultdict(lambda: {"count": 0, "avg_confidence": 0.0})
        for mem in memories:
            domain = mem.category or "general"
            domain_stats[domain]["count"] += 1
            conf = float(mem.confidence) if mem.confidence else 0.0
            domain_stats[domain]["avg_confidence"] += conf

        # Calculate averages
        for domain, stats in domain_stats.items():
            stats["avg_confidence"] /= stats["count"]
            stats["coverage"] = (
                "high" if stats["avg_confidence"] > 0.8 else ("medium" if stats["avg_confidence"] > 0.5 else "low")
            )

            if stats["coverage"] != "high":
                recommendations.append(
                    {
                        "domain": domain,
                        "coverage": stats["coverage"],
                        "avg_confidence": round(stats["avg_confidence"], 2),
                        "suggestion": (
                            f"Add more training data for '{domain}' "
                            f"(current coverage: {stats['coverage']}, "
                            f"confidence: {stats['avg_confidence']:.2f})"
                        ),
                    }
                )

        logger.info(f"Generated {len(recommendations)} training recommendations for tenant {tenant_id}")
        return recommendations

    def _extract_concepts(self, text: str) -> list[str]:
        """Extract key concepts from text using simple heuristics."""
        # Split text into words
        words = text.lower().split()

        # Filter for meaningful words (3+ chars, not common articles)
        common_words = {
            "the",
            "and",
            "is",
            "are",
            "was",
            "were",
            "in",
            "on",
            "at",
            "to",
            "for",
            "of",
            "with",
            "by",
            "from",
            "or",
            "a",
            "an",
            "it",
            "this",
            "that",
            "these",
            "those",
            "can",
            "will",
            "shall",
            "should",
            "would",
            "could",
            "may",
            "might",
            "must",
            "not",
            "but",
            "if",
            "then",
            "than",
            "so",
            "such",
            "no",
            "nor",
            "about",
            "up",
            "out",
            "as",
            "into",
        }

        concepts = [
            w.strip(".,;:!?()[]{}\"'-")
            for w in words
            if len(w.strip(".,;:!?()[]{}\"'-")) >= 3 and w not in common_words and not w.startswith("http")
        ]

        # Deduplicate while preserving order
        seen = set()
        unique_concepts = []
        for c in concepts:
            if c not in seen:
                seen.add(c)
                unique_concepts.append(c)

        return unique_concepts[:20]  # Limit to top 20 concepts

    def _find_similar_pairs(self, memories: list[AiMemory]) -> list[dict[str, Any]]:
        """Find similar Q&A pairs using Jaccard similarity."""
        similar_pairs = []
        memory_pairs = []

        for mem in memories:
            words = set(self._extract_concepts(mem.value))
            memory_pairs.append((mem, words))

        # Compare all pairs (O(n^2) but acceptable for training data)
        for i in range(len(memory_pairs)):
            for j in range(i + 1, len(memory_pairs)):
                mem1, words1 = memory_pairs[i]
                mem2, words2 = memory_pairs[j]

                # Jaccard similarity
                intersection = words1 & words2
                union = words1 | words2
                if union:
                    similarity = len(intersection) / len(union)
                    if similarity > SEMANTIC_SIMILARITY_THRESHOLD:
                        similar_pairs.append(
                            {
                                "pair_1": mem1.key[:50],
                                "pair_2": mem2.key[:50],
                                "similarity": round(similarity, 4),
                                "common_concepts": len(intersection),
                            }
                        )

        return similar_pairs

    def _update_semantic_cache(self, tenant_id: int, question: str, answer: str):
        """Update the semantic cache with new training data."""
        concepts = self._extract_concepts(answer)
        for concept in concepts:
            self._concept_cache[concept].append(question[:255])

        # Update domain cache
        domain = self._extract_domain(question, answer)
        self._domain_cache[domain].append(question[:255])

    def _extract_domain(self, question: str, answer: str) -> str:
        """Extract the domain/category from question and answer."""
        text = f"{question} {answer}".lower()
        if any(w in text for w in ["tax", "vat", "customs", "جمارك", "ضريبة"]):
            return "tax_customs"
        elif any(w in text for w in ["sales", "invoice", "customer", "facture", "مبيعات"]):
            return "sales"
        elif any(w in text for w in ["inventory", "stock", "warehouse", "مخزون"]):
            return "inventory"
        elif any(w in text for w in ["payment", "cheque", "receipt", "دفعة", "شيك"]):
            return "payments"
        elif any(w in text for w in ["employee", "salary", "payroll", "راتب", "موظف"]):
            return "hr"
        return "general"

    def _update_mastery_progress(self, tenant_id: int, question: str, answer: str):
        """Update mastery progress tracking for the tenant."""
        concepts = self._extract_concepts(answer)
        domain = self._extract_domain(question, answer)

        for concept in concepts:
            # Check if progress record exists
            existing = (
                tenant_query(AiTrainingProgress)
                .filter(
                    AiTrainingProgress.tenant_id == int(tenant_id),
                    AiTrainingProgress.concept_name == concept,
                )
                .first()
            )

            if existing:
                # Update existing record
                existing.usage_count += 1
                existing.confidence = min(float(existing.confidence) + 0.1, 1.0)  # Cap at 1.0
                existing.last_accessed = datetime.now(UTC)
                existing.mastery_score = self._calculate_mastery_score(existing.usage_count, existing.confidence)
            else:
                # Create new progress record
                progress = AiTrainingProgress(
                    tenant_id=int(tenant_id),
                    domain=domain,
                    topic=domain,
                    concept_name=concept,
                    covered=True,
                    usage_count=1,
                    confidence=0.9,
                    mastery_score=self._calculate_mastery_score(1, 0.9),
                    learning_velocity=1.0,
                    last_accessed=datetime.now(UTC),
                )
                db.session.add(progress)

        db.session.flush()

    def _calculate_mastery_score(self, usage_count: int, confidence: float) -> int:
        """Calculate mastery score based on usage and confidence."""
        # Formula: (usage_count * 10) + (confidence * 90), capped at 100
        score = min(int((usage_count * 10) + (confidence * 90)), 100)
        return max(score, 0)

    def get_domain_statistics(self, tenant_id: int) -> dict[str, Any]:
        """Get comprehensive domain statistics for a tenant."""
        memories = tenant_query(AiMemory).filter(AiMemory.tenant_id == int(tenant_id)).all()

        domains: dict[str, dict[str, Any]] = defaultdict(lambda: {"count": 0, "confidence_sum": 0.0, "active_count": 0})
        for mem in memories:
            domain = mem.category or "general"
            domains[domain]["count"] += 1
            domains[domain]["confidence_sum"] += float(mem.confidence) if mem.confidence else 0.0
            if mem.is_active:
                domains[domain]["active_count"] += 1

        # Calculate averages
        domain_stats: dict[str, dict[str, Any]] = {}
        for domain, stats in domains.items():
            avg_conf = stats["confidence_sum"] / stats["count"] if stats["count"] > 0 else 0.0
            domain_stats[domain] = {
                "total_records": stats["count"],
                "active_records": stats["active_count"],
                "average_confidence": round(avg_conf, 4),
                "coverage": ("high" if avg_conf > 0.8 else ("medium" if avg_conf > 0.5 else "low")),
            }

        # Get overall progress
        progress_records = tenant_query(AiTrainingProgress).filter(AiTrainingProgress.tenant_id == int(tenant_id)).all()

        total_concepts = len(progress_records)
        covered_concepts = sum(1 for p in progress_records if p.covered)
        avg_mastery = sum(p.mastery_score for p in progress_records) / total_concepts if total_concepts > 0 else 0

        return {
            "tenant_id": tenant_id,
            "domain_stats": domain_stats,
            "total_concepts": total_concepts,
            "covered_concepts": covered_concepts,
            "coverage_percentage": round((covered_concepts / total_concepts * 100) if total_concepts > 0 else 0, 2),
            "average_mastery_score": round(avg_mastery, 2),
            "total_memories": len(memories),
        }


# Global instance
advanced_trainer = AdvancedTrainer()
