import os
import secrets
import logging
logger = logging.getLogger(__name__)
def ensure_secret_key(instance_dir: str, env_value: str | None = None) -> str:
    key = env_value
    if key:
        return key
    secret_file = os.path.join(instance_dir, "secret_key")
    if os.path.exists(secret_file):
        try:
            with open(secret_file, "r", encoding="utf-8") as f:
                key = f.read().strip()
        except Exception:
            key = None
    if not key:
        key = secrets.token_hex(32)
        try:
            os.makedirs(instance_dir, exist_ok=True)
            with open(secret_file, "w", encoding="utf-8") as f:
                f.write(key)
        except Exception:
            pass
        logger.info("[Dev] SECRET_KEY generated for development")
    return key
def ensure_card_encryption_key(instance_dir: str, env_value: str | None = None) -> str:
    key = env_value
    if key:
        return key
    key_path = os.path.join(instance_dir, ".card_encryption_key")
    try:
        if os.path.exists(key_path):
            with open(key_path, "r", encoding="utf-8") as f:
                key = (f.read() or "").strip()
    except Exception:
        key = None
    if not key:
        key = secrets.token_hex(32)
        try:
            os.makedirs(instance_dir, exist_ok=True)
            with open(key_path, "w", encoding="utf-8") as f:
                f.write(key)
        except Exception:
            pass
    return key
def bootstrap_keys(app, instance_dir: str | None = None) -> None:
    if instance_dir is None:
        instance_dir = os.path.join(
            os.path.abspath(os.path.dirname(os.path.dirname(__file__))),
            "instance",
        )
    current_secret = app.config.get("SECRET_KEY")
    app.config["SECRET_KEY"] = ensure_secret_key(instance_dir, current_secret)
    current_card = app.config.get("CARD_ENCRYPTION_KEY")
    app.config["CARD_ENCRYPTION_KEY"] = ensure_card_encryption_key(instance_dir, current_card)
