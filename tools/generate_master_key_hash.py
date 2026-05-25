import hashlib
import os


def main():
    master_key = os.environ.get("MASTER_KEY") or ""
    if not master_key:
        raise SystemExit("Set MASTER_KEY environment variable.")

    digest = hashlib.sha256(master_key.encode("utf-8")).hexdigest()
    print(f"AZAD_MASTER_KEY_SHA256={digest}")


if __name__ == "__main__":
    main()
