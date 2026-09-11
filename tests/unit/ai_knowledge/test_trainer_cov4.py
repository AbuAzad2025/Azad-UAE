"""Coverage for ai_knowledge/trainer.py seed expertise-loop arcs 419->416, 421->416."""

from __future__ import annotations

import json
from unittest.mock import patch

from ai_knowledge.trainer import Trainer


class _Cov4FakeQL:
    """Minimal dict-backed quick_learner stand-in (no DB, real dict behavior)."""

    def __init__(self, known=None):
        self.store = dict(known or {})
        self.learned = []

    def get_answer(self, question, tenant_id=None):
        return self.store.get(question)

    def learn(self, question, answer, category="learned", tenant_id=None):
        self.store[question] = answer
        self.learned.append((question, category))


class TestCov4TrainerExpertiseSeed:
    def _run_seed(self, tmp_path, payload, known=None):
        expertise_file = tmp_path / "exp.json"
        expertise_file.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        trainer = Trainer()
        trainer.quick_learner = _Cov4FakeQL(known=known)
        with patch("glob.glob", return_value=[str(expertise_file)]):
            trainer.seed()
        return trainer

    def test_empty_topic_and_knowledge_skip_learn(self, tmp_path):
        """Arc 419->416: areas without topic+knowledge fall through the loop."""
        payload = {
            "expertise_areas": [
                {"topic": "", "knowledge": "معرفة بلا عنوان"},
                {"topic": "cov4_valid_topic", "knowledge": ""},
            ]
        }
        trainer = self._run_seed(tmp_path, payload)
        assert "cov4_valid_topic" not in trainer.quick_learner.store
        assert all(q != "" for q, _cat in trainer.quick_learner.learned)

    def test_existing_answer_skips_learn(self, tmp_path):
        """Arc 421->416: already-known expertise topics are not re-learned."""
        payload = {"expertise_areas": [{"topic": "cov4_known_topic", "knowledge": "جديد"}]}
        trainer = self._run_seed(tmp_path, payload, known={"cov4_known_topic": "قديم"})
        assert trainer.quick_learner.store["cov4_known_topic"] == "قديم"
        assert "cov4_known_topic" not in [q for q, _cat in trainer.quick_learner.learned]

    def test_new_topic_is_learned_from_list_payload(self, tmp_path):
        """List-form expertise file plus the happy-path learn branch."""
        payload = [{"topic": "cov4_fresh_topic", "knowledge": "معرفة جديدة"}]
        trainer = self._run_seed(tmp_path, payload)
        assert trainer.quick_learner.store["cov4_fresh_topic"] == "معرفة جديدة"

    def test_all_known_answers_seed_nothing_new(self, tmp_path):
        """Seed loop skips known answers and finishes with zero new pairs."""
        from ai_knowledge.trainer import SEED_QA

        known = {question: "موجود" for question, _answer in SEED_QA}
        trainer = Trainer()
        trainer.quick_learner = _Cov4FakeQL(known=known)
        with patch("glob.glob", return_value=[]):
            trainer.seed()
        assert trainer.quick_learner.learned == []
        assert trainer._seeded is True

    def test_expertise_glob_error_is_swallowed(self, tmp_path):
        """Expertise-seed read errors are logged, seeding still completes."""
        trainer = Trainer()
        trainer.quick_learner = _Cov4FakeQL()
        with patch("glob.glob", side_effect=OSError("disk")):
            trainer.seed()
        assert trainer._seeded is True
