"""Coverage tests for neural_engine.py training + cache-metadata branches (part A)."""

from __future__ import annotations

import json
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from ai_knowledge.neural import neural_engine as ne_mod
from ai_knowledge.neural.neural_engine import AzadNeuralEngine


@pytest.fixture
def engine(tmp_path):
    with patch("ai_knowledge.get_knowledge_path", return_value=str(tmp_path)):
        eng = AzadNeuralEngine()
    return eng


def _accounting_entries(n=12):
    return [
        SimpleNamespace(
            lines=[1, 2],
            total_debit=100.0,
            total_credit=100.0,
            reference_type="Sale" if i % 2 == 0 else "Purchase",
        )
        for i in range(n)
    ]


def _mock_accounting_success(engine):
    engine.scalers["accounting_classifier"] = MagicMock()
    engine.scalers["accounting_classifier"].fit_transform.side_effect = lambda x: x
    engine.models["accounting_classifier"] = MagicMock()
    engine.models["accounting_classifier"].score.return_value = 0.9


class TestCovAccountingClassifierBranch:
    def test_skip_creation_when_model_exists_492_502(self, engine):
        # 492->502: "accounting_classifier" already in self.models skips creation block.
        _mock_accounting_success(engine)
        with (
            patch("models.GLJournalEntry") as mock_entry,
            patch.object(engine, "_save_model", return_value=True),
        ):
            mock_entry.query.limit.return_value.all.return_value = _accounting_entries(12)
            result = engine._train_accounting_internal()
        assert result["success"] is True
        assert result["samples"] == 12

    def test_creation_when_model_missing(self, engine):
        # Complementary path: model absent so the MLPClassifier block runs.
        engine.models.pop("accounting_classifier", None)
        engine.scalers.pop("accounting_classifier", None)
        with (
            patch("models.GLJournalEntry") as mock_entry,
            patch.object(engine, "_save_model", return_value=True),
        ):
            mock_entry.query.limit.return_value.all.return_value = _accounting_entries(12)
            result = engine._train_accounting_internal()
        assert result["success"] is True
        assert "accounting_classifier" in engine.models


class TestCovDetectFraudNormalHour:
    def test_normal_hour_skips_unusual_time_reason_1610_1612(self, engine):
        # 1610->1612: hour=12 is not <6 or >22, so no unusual-time reason is added.
        sale = {
            "amount_aed": 500,
            "discount_amount": 0,
            "subtotal": 500,
            "paid_amount_aed": 500,
            "sale_date": datetime(2024, 1, 15, 12, 0, 0),
        }
        with patch.object(engine, "_load_model", return_value=False):
            result = engine.detect_fraud(sale)
        assert result["is_fraud"] is False
        assert not any("غير معتاد" in r for r in result["reasons"])


def _demand_rows(product_id, start_day, count, qty=5.0):
    return [
        SimpleNamespace(
            product_id=product_id,
            sale_date=datetime(2024, 1, 1 + (start_day + i) % 27, 12, 0, 0),
            total_quantity=qty + (i % 3),
        )
        for i in range(count)
    ]


def _mock_demand_query(rows):
    mock_q = MagicMock()
    mock_q.join.return_value = mock_q
    mock_q.filter.return_value = mock_q
    mock_q.group_by.return_value = mock_q
    mock_q.all.return_value = rows
    return mock_q


class TestCovDemandPredictorBranches:
    def test_thin_product_skipped_1876(self, engine):
        # Line 1876 `continue`: product 99 has <10 rows and is skipped,
        # while product 1 has 30 rows and trains successfully.
        rows = _demand_rows(99, 0, 3) + _demand_rows(1, 0, 30)
        engine.scalers["demand_predictor"] = MagicMock()
        engine.scalers["demand_predictor"].fit_transform.side_effect = lambda x: x
        engine.models["demand_predictor"] = MagicMock()
        engine.models["demand_predictor"].score.return_value = 0.8
        with (
            patch("extensions.db.session.query", return_value=_mock_demand_query(rows)),
            patch.object(engine, "_save_model", return_value=True),
        ):
            result = engine._train_demand_internal()
        assert result["success"] is True
        assert result["samples"] >= 20

    def test_insufficient_samples_1898(self, engine):
        # Line 1898: 30 rows split across thin products -> x empty -> error return.
        rows = []
        for pid in range(5):
            rows += _demand_rows(pid, pid * 2, 6)
        assert len(rows) == 30
        with patch("extensions.db.session.query", return_value=_mock_demand_query(rows)):
            result = engine._train_demand_internal()
        assert result["success"] is False
        assert "samples" in result["error"]


class TestCovMetadataCache:
    def test_missing_models_dir_returns_2203(self, engine):
        engine.models_dir = "/nonexistent-dir-xyz-12345/neural_models"
        engine._load_metadata_cache()  # line 2203 early return, must not raise

    def test_mixed_files_and_corrupt_sidecar_2205_2216(self, engine, tmp_path):
        # 2205: non-meta file skipped; 2213-2214: corrupt JSON skipped with debug log.
        (tmp_path / "notes.pkl").write_text("junk", encoding="utf-8")
        (tmp_path / "broken.meta.json").write_text("{not valid json", encoding="utf-8")
        (tmp_path / "empty.meta.json").write_text(json.dumps({"no_model": 1}), encoding="utf-8")
        (tmp_path / "good.meta.json").write_text(
            json.dumps({"model": "price_optimizer", "samples": 42}),
            encoding="utf-8",
        )
        engine._load_metadata_cache()
        assert engine._model_metadata.get("price_optimizer", {}).get("samples") == 42

    def test_unreadable_sidecar_oserror_2213(self, engine, tmp_path):
        # A directory named *.meta.json raises OSError on open -> debug skip.
        (tmp_path / "dir.meta.json").mkdir(exist_ok=True)
        engine._load_metadata_cache()  # must not raise

    def test_listdir_failure_2216(self, engine):
        with patch("os.listdir", side_effect=OSError("disk gone")):
            engine._load_metadata_cache()  # outer except, must not raise


class TestCovDatasetVolume:
    def test_no_app_context_returns_none_2257(self, engine):
        with patch("flask.has_app_context", return_value=False):
            assert engine._dataset_volume("price_optimizer") is None

    def test_probe_exception_returns_none_2259_2260(self, engine):
        with patch("flask.has_app_context", side_effect=RuntimeError("probe down")):
            assert engine._dataset_volume("price_optimizer") is None

    def test_unknown_model_returns_none_2282(self, engine):
        assert engine._dataset_volume("unknown_model_xyz_123") is None

    def test_db_failure_returns_none_2286_2288(self, engine):
        with patch("extensions.db.session.query", side_effect=RuntimeError("db down")):
            assert engine._dataset_volume("price_optimizer") is None


class TestCovShouldRetrain:
    def _touch(self, engine, name):
        path = f"{engine.models_dir}/{name}.pkl"
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("x")
        return path

    def test_missing_file_requires_retrain(self, engine):
        assert engine.should_retrain("ghost_model_abc", current_samples=10) is True

    def test_unknown_volume_keeps_cache_2303(self, engine):
        self._touch(engine, "price_optimizer")
        with patch.object(engine, "_dataset_volume", return_value=None):
            assert engine.should_retrain("price_optimizer", current_samples=None) is False

    def test_invalid_old_samples_requires_retrain_2308(self, engine):
        self._touch(engine, "price_optimizer")
        engine._model_metadata.pop("price_optimizer", None)
        assert engine.should_retrain("price_optimizer", current_samples=100) is True
        engine._model_metadata["price_optimizer"] = {"samples": 0}
        assert engine.should_retrain("price_optimizer", current_samples=100) is True

    def test_fresh_and_stale_volumes(self, engine):
        self._touch(engine, "price_optimizer")
        engine._model_metadata["price_optimizer"] = {"samples": 100}
        assert engine.should_retrain("price_optimizer", current_samples=105) is False
        assert engine.should_retrain("price_optimizer", current_samples=200) is True
        assert engine.should_retrain("price_optimizer", current_samples=0) is False


class TestCovEnsureLoadedAndStatus:
    def test_already_loaded_2317_2318(self, engine):
        engine._loaded_models.add("price_optimizer")
        assert engine.ensure_model_loaded("price_optimizer") is True

    def test_load_success_marks_loaded_2319_2322(self, engine):
        engine._loaded_models.discard("price_optimizer")
        with patch.object(engine, "_load_model", return_value=True):
            assert engine.ensure_model_loaded("price_optimizer") is True
        assert "price_optimizer" in engine._loaded_models

    def test_load_failure_returns_false_2323(self, engine):
        engine._loaded_models.discard("price_optimizer")
        with patch.object(engine, "_load_model", return_value=False):
            assert engine.ensure_model_loaded("price_optimizer") is False

    def test_cached_model_status_cached_and_missing_2327_2333(self, engine):
        status = engine.get_cached_model_status("price_optimizer")
        assert status["model"] == "price_optimizer"
        assert status["cached"] is False
        assert status["stale"] is True
        path = f"{engine.models_dir}/price_optimizer.pkl"
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("x")
        engine._model_metadata["price_optimizer"] = {
            "samples": 10,
            "trained_at": "2024-01-01",
            "model_version_hash": "abc",
        }
        with (
            patch.object(engine, "_dataset_volume", return_value=10),
            patch.object(ne_mod, "NEURAL_RETRAIN_VOLUME_THRESHOLD", 0.10),
        ):
            status2 = engine.get_cached_model_status("price_optimizer")
        assert status2["cached"] is True
        assert status2["samples"] == 10
        assert status2["stale"] is False
