import hashlib
import os
import sys


def _resolve_hash_file() -> str:
    override = (os.environ.get("AZAD_MASTER_HASH_FILE") or "").strip()
    if override:
        return override
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    try:
        sys.path.insert(0, base_dir)
        from config import instance_dir
        return os.path.join(instance_dir, ".master_key_sha256")
    except Exception:
        return os.path.join(base_dir, "instance", ".master_key_sha256")


def main():
    master_key = os.environ.get("MASTER_KEY") or ""
    if not master_key:
        raise SystemExit("Set MASTER_KEY environment variable.")

    digest = hashlib.sha256(master_key.encode("utf-8")).hexdigest()
    path = _resolve_hash_file()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(digest)
    print("OK")


if __name__ == "__main__":
    main()
