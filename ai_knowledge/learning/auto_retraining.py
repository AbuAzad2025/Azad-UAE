from datetime import datetime
import logging
import json
import os

from ai_knowledge import get_knowledge_path

logger = logging.getLogger(__name__)


class AutoRetrainingScheduler:
    TRAINING_LOG_FILE = get_knowledge_path("training_history.json")

    @staticmethod
    def should_retrain() -> bool:
        from models import Sale

        current_count = Sale.query.filter_by(status="confirmed").count()

        last_training = AutoRetrainingScheduler.get_last_training_info()
        if not last_training:
            return current_count >= 100

        last_count = last_training.get("sales_count", 0)
        last_date = datetime.fromisoformat(last_training.get("timestamp", "2020-01-01"))

        days_since = (datetime.now() - last_date).days

        if current_count >= last_count + 100:
            return True

        if days_since >= 7 and current_count >= last_count + 50:
            return True

        return False

    @staticmethod
    def trigger_retraining():
        from models import Sale

        try:
            logger.info("🧠 Auto-retraining triggered...")

            from ai_knowledge.neural.neural_engine import get_neural_engine

            neural = get_neural_engine()

            results = neural.train_all_models()

            sales_count = Sale.query.filter_by(status="confirmed").count()
            AutoRetrainingScheduler.log_training(sales_count, results)

            logger.info("✅ Auto-retraining completed successfully")
            return results

        except Exception as e:
            logger.error(f"❌ Auto-retraining failed: {e}")
            return {"success": False, "error": str(e)}

    @staticmethod
    def get_last_training_info():
        try:
            if os.path.exists(AutoRetrainingScheduler.TRAINING_LOG_FILE):
                with open(AutoRetrainingScheduler.TRAINING_LOG_FILE, "r") as f:
                    history = json.load(f)
                    if history:
                        return history[-1]
        except (json.JSONDecodeError, OSError) as exc:
            logger.debug("Could not load training log: %s", exc)

    @staticmethod
    def log_training(sales_count: int, results: dict):
        try:
            history = []
            if os.path.exists(AutoRetrainingScheduler.TRAINING_LOG_FILE):
                with open(AutoRetrainingScheduler.TRAINING_LOG_FILE, "r") as f:
                    history = json.load(f)

            history.append(
                {
                    "timestamp": datetime.now().isoformat(),
                    "sales_count": sales_count,
                    "results": results,
                }
            )

            history = history[-20:]

            with open(AutoRetrainingScheduler.TRAINING_LOG_FILE, "w") as f:
                json.dump(history, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to log training: {e}")

    @staticmethod
    def check_and_train_if_needed():
        if AutoRetrainingScheduler.should_retrain():
            logger.info("📊 Training threshold reached - initiating auto-retraining")
            return AutoRetrainingScheduler.trigger_retraining()
        return {"message": "No retraining needed"}


# إنشاء instance عام
auto_retraining = AutoRetrainingScheduler()
