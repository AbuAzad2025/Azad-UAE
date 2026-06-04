"""Read-only Phase 1F / 1G GL mapping validation and seed preview.

Run:
    python tools/qa/gl_mapping_validation_dry_run.py
    python tools/qa/gl_mapping_validation_dry_run.py --tenant-id 3
    python tools/qa/gl_mapping_validation_dry_run.py --issues-only
    python tools/qa/gl_mapping_validation_dry_run.py --preview-seed
    python tools/qa/gl_mapping_validation_dry_run.py --preview-seed --tenant-id 3
"""
import argparse
import json
import os
import sys


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)
os.chdir(PROJECT_ROOT)
os.environ.setdefault("SKIP_SYSTEM_INTEGRITY", "1")

from dotenv import load_dotenv

load_dotenv()

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Read-only GLAccountMapping readiness validation and seed preview.",
    )
    parser.add_argument(
        "--tenant-id",
        type=int,
        default=None,
        help="Target one tenant. Omit to process all tenants.",
    )
    parser.add_argument(
        "--issues-only",
        action="store_true",
        help="Suppress ready rows and show only missing/invalid findings.",
    )
    parser.add_argument(
        "--preview-seed",
        action="store_true",
        help="Phase 1G: Show a read-only preview of proposed GL concept mappings. No data is written.",
    )
    args = parser.parse_args()

    from app import create_app

    app = create_app()
    with app.app_context():
        if args.preview_seed:
            from services.gl_mapping_validation import preview_seed_gl_mapping

            report = preview_seed_gl_mapping(tenant_id=args.tenant_id)
            print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
            return 0
        else:
            from services.gl_mapping_validation import dry_run_gl_mapping_validation

            report = dry_run_gl_mapping_validation(
                tenant_id=args.tenant_id,
                include_ready=not args.issues_only,
            )
            print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
            return 0 if report["ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
