"""
Verify Dynamic GL Resolution PATH (not just resulting code).

For each critical concept, this test:
1. Looks up the expected mapped account from GLAccountMapping.
2. Creates a journal line with ONLY concept_code (no hardcoded account).
3. Verifies the created GLJournalLine.account_id == mapped account_id.

If this passes, the resolution is 100% dynamic.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

CRITICAL_CONCEPTS = [
    "CASH", "BANK", "AR", "AP",
    "INVENTORY_ASSET", "COGS", "SALES_REVENUE",
    "SALES_DISCOUNT", "VAT_INPUT", "VAT_OUTPUT",
    "CHEQUES_UNDER_COLLECTION", "PARTNER_CURRENT_ACCOUNT", "MERCHANT_CURRENT_ACCOUNT",
]


def main():
    from app import create_app
    from extensions import db
    from models import Tenant, GLAccountMapping, GLJournalEntry
    from services.gl_service import GLService
    from services.gl_account_resolver import resolve_gl_account, is_dynamic_gl_mapping_enabled
    from decimal import Decimal
    from datetime import datetime, timezone
    import sqlalchemy as sa

    app = create_app()

    with app.app_context():
        from flask import current_app
        flag_original = current_app.config.get('ENABLE_DYNAMIC_GL_MAPPING', False)
        current_app.config['ENABLE_DYNAMIC_GL_MAPPING'] = True

        try:
            tenant = Tenant.query.filter(Tenant.is_active == True).first()
            if not tenant:
                print("FAIL: No active tenant")
                return 1

            tid = tenant.id
            print(f"Tenant: {tenant.name} (id={tid})")
            print(f"Dynamic flag enabled: {is_dynamic_gl_mapping_enabled()}")
            print()

            all_pass = True
            test_entries = []

            for concept in CRITICAL_CONCEPTS:
                mapping = GLAccountMapping.query.filter_by(
                    tenant_id=tid, concept_code=concept
                ).first()

                if not mapping:
                    print(f"  {concept}: SKIP — no mapping for this tenant")
                    continue

                expected_account_id = mapping.gl_account_id

                # Create a minimal balanced entry using ONLY concept_code
                entry = GLService.create_journal_entry(
                    date=datetime.now(timezone.utc),
                    description=f"Test Dynamic GL — {concept}",
                    lines=[
                        {
                            "concept_code": concept,
                            "debit": Decimal("100.00"),
                            "description": f"Test {concept} debit",
                        },
                        {
                            "concept_code": "CASH",  # balancing side
                            "credit": Decimal("100.00"),
                            "description": "Balancing CASH",
                        },
                    ],
                    tenant_id=tid,
                    currency=tenant.default_currency or "AED",
                )
                db.session.commit()
                test_entries.append(entry.id)

                # Verify the line
                debit_line = [l for l in entry.lines if l.debit > 0][0]
                actual_account_id = debit_line.account_id

                if actual_account_id == expected_account_id:
                    print(f"  {concept}: PASS -> account_id={actual_account_id} (matches mapping)")
                else:
                    print(f"  {concept}: FAIL -> expected account_id={expected_account_id}, got {actual_account_id}")
                    all_pass = False

            print()
            if all_pass:
                print("=== ALL CONCEPTS RESOLVED DYNAMICALLY ===")
            else:
                print("=== SOME CONCEPTS FAILED DYNAMIC RESOLUTION ===")

            return 0 if all_pass else 1

        finally:
            # Cleanup
            if 'test_entries' in dir() and test_entries:
                db.session.execute(
                    sa.text("""
                        DELETE FROM gl_journal_lines WHERE entry_id IN :eids
                    """),
                    {"eids": tuple(test_entries)}
                )
                db.session.execute(
                    sa.text("""
                        DELETE FROM gl_journal_entries WHERE id IN :eids
                    """),
                    {"eids": tuple(test_entries)}
                )
                db.session.commit()
            current_app.config['ENABLE_DYNAMIC_GL_MAPPING'] = flag_original
            print("\nCleanup complete. Flag restored.")


if __name__ == '__main__':
    sys.exit(main())
