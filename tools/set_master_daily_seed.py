import os
import sys


def _resolve_seed_file() -> str:
    override = (os.environ.get("AZAD_MASTER_SEED_FILE") or "").strip()
    if override:
        return override
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    try:
        sys.path.insert(0, base_dir)
        from config import instance_dir
        return os.path.join(instance_dir, ".master_daily_seed")
    except Exception:
        return os.path.join(base_dir, "instance", ".master_daily_seed")


def main():
    seed = os.environ.get("MASTER_DAILY_SEED") or ""
    if not seed:
        raise SystemExit("Set MASTER_DAILY_SEED environment variable.")

    path = _resolve_seed_file()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(seed)
    print("OK")


if __name__ == "__main__":
    main()
