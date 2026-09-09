"""Coverage tests for neural_engine.py scheduling/worker/save branches (part B)."""

from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest

import ai_knowledge.neural.neural_engine as ne_mod
from ai_knowledge.neural.neural_engine import AzadNeuralEngine


@pytest.fixture
def engine(tmp_path):
    with patch("ai_knowledge.get_knowledge_path", return_value=str(tmp_path)):
        eng = AzadNeuralEngine()
    return eng


@contextmanager
def _fake_ctx():
    yield


class TestCovPersistMetadata:
    def test_persist_oserror_warns_and_returns_2240_2242(self, engine):
        import builtins

        real_open = builtins.open

        def _boom(path, *args, **kwargs):
            if str(path).endswith(".meta.json"):
                raise OSError("read-only")
            return real_open(path, *args, **kwargs)

        with patch("builtins.open", side_effect=_boom):
            engine._persist_metadata("price_optimizer", 10)  # must not raise
        assert "price_optimizer" not in engine._model_metadata


class TestCovScheduleRetrain:
    def test_unknown_model_rejected(self, engine):
        assert engine.schedule_background_retrain("nope_unknown") is False

    def test_current_app_failure_falls_back_to_none_2364_2365(self, engine):
        captured = {}

        class FakeThread:
            def __init__(self, **kwargs):
                captured.update(kwargs)

            def start(self):
                captured["started"] = True

        class _BoomProxy:
            def _get_current_object(self):
                raise RuntimeError("no ctx")

        with (
            patch("flask.current_app", _BoomProxy()),
            patch("threading.Thread", FakeThread),
        ):
            assert engine.schedule_background_retrain("price_optimizer") is True
        assert captured.get("started") is True
        assert captured.get("args")[3] is None  # app_obj is None
        engine._retrain_inflight.discard("price_optimizer")

    def test_already_inflight_rejected(self, engine):
        engine._retrain_inflight.add("price_optimizer")
        try:
            assert engine.schedule_background_retrain("price_optimizer") is False
        finally:
            engine._retrain_inflight.discard("price_optimizer")

    def test_thread_spawn_failure_cleans_up_2374_2378(self, engine):
        with patch("threading.Thread", side_effect=RuntimeError("spawn failed")):
            assert engine.schedule_background_retrain("price_optimizer") is False
        assert "price_optimizer" not in engine._retrain_inflight


class TestCovBackgroundWorker:
    def _prep(self, engine, succeed=True):
        if succeed:
            engine.train_price_optimizer = MagicMock(return_value={"success": True})
        else:
            engine.train_price_optimizer = MagicMock(side_effect=RuntimeError("train boom"))

    def test_app_obj_success_2386(self, engine):
        self._prep(engine, succeed=True)
        app_obj = MagicMock()
        app_obj.app_context.return_value = _fake_ctx()
        engine._background_retrain_worker("price_optimizer", "train_price_optimizer", None, app_obj)
        engine.train_price_optimizer.assert_called_once_with(None)
        assert "price_optimizer" not in engine._retrain_inflight

    def test_app_obj_failure_warns_2388_2389(self, engine):
        self._prep(engine, succeed=False)
        app_obj = MagicMock()
        app_obj.app_context.return_value = _fake_ctx()
        engine._background_retrain_worker("price_optimizer", "train_price_optimizer", None, app_obj)
        assert "price_optimizer" not in engine._retrain_inflight

    def test_from_app_context_success_2390_2393(self, engine):
        self._prep(engine, succeed=True)
        engine._background_retrain_worker("price_optimizer", "train_price_optimizer", _fake_ctx, None)
        engine.train_price_optimizer.assert_called_once_with(_fake_ctx)
        assert "price_optimizer" not in engine._retrain_inflight

    def test_from_app_context_failure_warns_2394_2395(self, engine):
        self._prep(engine, succeed=False)
        engine._background_retrain_worker("price_optimizer", "train_price_optimizer", _fake_ctx, None)
        assert "price_optimizer" not in engine._retrain_inflight

    def test_no_context_success_2396_2398(self, engine):
        self._prep(engine, succeed=True)
        engine._background_retrain_worker("price_optimizer", "train_price_optimizer", None, None)
        engine.train_price_optimizer.assert_called_once_with(None)
        assert "price_optimizer" not in engine._retrain_inflight

    def test_no_context_failure_warns_2399_2400(self, engine):
        self._prep(engine, succeed=False)
        engine._background_retrain_worker("price_optimizer", "train_price_optimizer", None, None)
        assert "price_optimizer" not in engine._retrain_inflight


class TestCovMaybeScheduleRetrain:
    def test_unknown_volume_never_triggers_2412_2413(self, engine):
        with patch.object(engine, "_dataset_volume", return_value=None):
            assert engine.maybe_schedule_retrain("price_optimizer") is False

    def test_drift_schedules_background_2414_2415(self, engine):
        with (
            patch.object(engine, "_dataset_volume", return_value=50),
            patch.object(engine, "should_retrain", return_value=True),
            patch.object(engine, "schedule_background_retrain", return_value=True) as sched,
        ):
            assert engine.maybe_schedule_retrain("price_optimizer") is True
        sched.assert_called_once_with("price_optimizer", None)

    def test_fresh_cache_does_not_schedule_2416(self, engine):
        with (
            patch.object(engine, "_dataset_volume", return_value=50),
            patch.object(engine, "should_retrain", return_value=False),
        ):
            assert engine.maybe_schedule_retrain("price_optimizer") is False

    def test_check_exception_returns_false_2417_2419(self, engine):
        with patch.object(engine, "_dataset_volume", side_effect=RuntimeError("boom")):
            assert engine.maybe_schedule_retrain("price_optimizer") is False


class TestCovPredictWarm:
    def test_predict_next_week_success(self, engine):
        payload = {
            "forecast": [{"day": 1}],
            "total_expected": 123.0,
            "trend": "up",
            "confidence": 0.7,
        }
        with patch.object(engine, "forecast_sales", return_value=payload):
            result = engine.predict_next_week_sales(7)
        assert result["success"] is True
        assert result["predicted_amount"] == 123.0

    def test_predict_next_week_empty(self, engine):
        with patch.object(engine, "forecast_sales", return_value={"forecast": []}):
            result = engine.predict_next_week_sales(7)
        assert result["success"] is False

    def test_predict_next_week_exception_2440_2442(self, engine):
        with patch.object(engine, "forecast_sales", side_effect=RuntimeError("boom")):
            result = engine.predict_next_week_sales(7)
        assert result["success"] is False
        assert "boom" in result["error"]

    def test_warm_cache_success(self, engine):
        with patch.object(engine, "load_all_models", return_value=["a"]):
            assert engine.warm_cache() == ["a"]

    def test_warm_cache_exception_returns_empty_2448_2450(self, engine):
        with patch.object(engine, "load_all_models", side_effect=RuntimeError("boom")):
            assert engine.warm_cache() == []


class TestCovSaveModel:
    def test_metadata_persist_failure_still_succeeds_2479_2480(self, engine):
        engine.models["price_optimizer"] = MagicMock()
        engine.scalers["price_optimizer"] = MagicMock()
        engine.training_status["price_optimizer"] = {"samples": 5}
        with (
            patch("joblib.dump", return_value=None),
            patch.object(engine, "_persist_metadata", side_effect=RuntimeError("meta down")),
        ):
            assert engine._save_model("price_optimizer") is True


class TestCovTrainAllModels:
    def _ok(self, *args, **kwargs):
        return {"success": True}

    def test_skip_cache_check_with_use_cache_false_2555_2568(self, engine):
        with patch.object(engine, "should_retrain") as sr:
            with (
                patch.object(engine, "train_price_optimizer", return_value=self._ok()),
                patch.object(engine, "train_sales_forecaster", return_value=self._ok()),
                patch.object(engine, "train_customer_classifier", return_value=self._ok()),
                patch.object(engine, "train_fraud_detector", return_value=self._ok()),
                patch.object(engine, "train_inventory_optimizer", return_value=self._ok()),
                patch.object(engine, "train_demand_predictor", return_value=self._ok()),
                patch.object(engine, "train_financial_planning", return_value=self._ok()),
                patch.object(engine, "train_maintenance_prediction", return_value=self._ok()),
                patch.object(engine, "train_accounting_assistant", return_value=self._ok()),
                patch.object(engine, "train_profit_optimizer", return_value=self._ok()),
                patch.object(engine, "train_churn_predictor", return_value=self._ok()),
            ):
                result = engine.train_all_models(use_cache=False)
        sr.assert_not_called()  # 2555->2568: cache check bypassed entirely
        assert result["success"] is True
        assert result["trained_models"] == 11

    def test_cache_check_exception_trains_anyway_2566_2567(self, engine):
        with patch.object(engine, "should_retrain", side_effect=RuntimeError("cache boom")):
            with (
                patch.object(engine, "train_price_optimizer", return_value=self._ok()),
                patch.object(engine, "train_sales_forecaster", return_value=self._ok()),
                patch.object(engine, "train_customer_classifier", return_value=self._ok()),
                patch.object(engine, "train_fraud_detector", return_value=self._ok()),
                patch.object(engine, "train_inventory_optimizer", return_value=self._ok()),
                patch.object(engine, "train_demand_predictor", return_value=self._ok()),
                patch.object(engine, "train_financial_planning", return_value=self._ok()),
                patch.object(engine, "train_maintenance_prediction", return_value=self._ok()),
                patch.object(engine, "train_accounting_assistant", return_value=self._ok()),
                patch.object(engine, "train_profit_optimizer", return_value=self._ok()),
                patch.object(engine, "train_churn_predictor", return_value=self._ok()),
            ):
                result = engine.train_all_models(force=False, use_cache=True)
        assert result["success"] is True

    def test_typeerror_fallback_calls_with_none_2574_2575(self, engine):
        def needs_arg(from_app_context):
            assert from_app_context is None
            return {"success": True}

        with patch.object(engine, "should_retrain", return_value=True):
            with (
                patch.object(engine, "train_price_optimizer", side_effect=needs_arg),
                patch.object(engine, "train_sales_forecaster", return_value=self._ok()),
                patch.object(engine, "train_customer_classifier", return_value=self._ok()),
                patch.object(engine, "train_fraud_detector", return_value=self._ok()),
                patch.object(engine, "train_inventory_optimizer", return_value=self._ok()),
                patch.object(engine, "train_demand_predictor", return_value=self._ok()),
                patch.object(engine, "train_financial_planning", return_value=self._ok()),
                patch.object(engine, "train_maintenance_prediction", return_value=self._ok()),
                patch.object(engine, "train_accounting_assistant", return_value=self._ok()),
                patch.object(engine, "train_profit_optimizer", return_value=self._ok()),
                patch.object(engine, "train_churn_predictor", return_value=self._ok()),
            ):
                result = engine.train_all_models()
        assert result["results"]["price_optimizer"]["success"] is True

    def test_cache_fresh_skip(self, engine):
        with patch.object(engine, "should_retrain", return_value=False):
            with patch.object(engine, "train_price_optimizer") as price_mock:
                result = engine.train_all_models()
        price_mock.assert_not_called()
        assert result["results"]["price_optimizer"]["skipped"] is True


class TestCovGetNeuralEngine:
    def test_warm_cache_failure_still_returns_instance_2726_2727(self, tmp_path):
        ne_mod._neural_engine_instance = None
        try:
            with (
                patch("ai_knowledge.get_knowledge_path", return_value=str(tmp_path)),
                patch.object(AzadNeuralEngine, "warm_cache", side_effect=RuntimeError("warm down")),
            ):
                inst = ne_mod.get_neural_engine()
            assert isinstance(inst, AzadNeuralEngine)
        finally:
            ne_mod._neural_engine_instance = None
