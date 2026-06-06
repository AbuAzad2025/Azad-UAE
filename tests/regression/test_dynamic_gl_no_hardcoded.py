"""
End-to-end test: Activate Dynamic GL Mapping and verify ZERO hardcoded
account codes are used in postings.

Strategy:
1. Enable ENABLE_DYNAMIC_GL_MAPPING temporarily.
2. Create synthetic transactions through service layer.
3. Inspect created GL lines — assert no legacy hardcoded codes.
4. Roll back all test data.

Legacy hardcoded codes to watch for:
  '1130' (AR), '1140' (Inventory), '1150' (Cheques)
  '2110' (AP), '2130' (VAT Output)
  '4100' (Sales Revenue), '4300' (Shipping)
  '5100' (COGS), '5200' (Sales Discount)
  '3350' (Partner), '2115' (Merchant)
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

LEGACY_CODES = {'1130', '1140', '1150', '2110', '2130', '4100', '4300', '5100', '5200', '3350', '2115'}


def main():
    from app import create_app
    from extensions import db
    from models import Tenant, GLAccount, GLJournalEntry, GLJournalLine
    from services.gl_service import GLService
    from services.gl_posting import post_or_fail, GlPostingError
    from utils.gl_reference_types import GLRef
    from decimal import Decimal
    import sqlalchemy as sa

    app = create_app()

    with app.app_context():
        # Pick the first active tenant with GL accounts
        tenant = Tenant.query.filter(Tenant.is_active == True).first()
        if not tenant:
            print("FAIL: No active tenant found.")
            return 1

        tenant_id = tenant.id
        print(f"Tenant: {tenant.name} (id={tenant_id})")

        # Check feature flag state
        from flask import current_app
        flag_original = current_app.config.get('ENABLE_DYNAMIC_GL_MAPPING', False)
        print(f"Original flag state: {flag_original}")

        # Temporarily enable via current_app.config (runtime)
        current_app.config['ENABLE_DYNAMIC_GL_MAPPING'] = True
        print("Flag temporarily ENABLED for test.")

        try:
            # Count GL entries before
            before_count = db.session.execute(
                sa.text("SELECT COUNT(*) FROM gl_journal_entries WHERE tenant_id = :tid"),
                {"tid": tenant_id}
            ).scalar()
            print(f"GL entries before: {before_count}")

            # --- TEST 1: GL Entry via create_journal_entry ---
            print("\n--- TEST 1: create_journal_entry ---")
            try:
                from datetime import datetime, timezone
                entry = GLService.create_journal_entry(
                    date=datetime.now(timezone.utc),
                    description="Test Dynamic GL Manual Entry",
                    lines=[
                        {
                            "concept_code": "CASH",
                            "debit": Decimal("1000.00"),
                            "description": "Test debit",
                        },
                        {
                            "concept_code": "SALES_REVENUE",
                            "credit": Decimal("1000.00"),
                            "description": "Test credit",
                        },
                    ],
                    tenant_id=tenant_id,
                    currency=tenant.default_currency or "AED",
                )
                db.session.commit()
                print(f"Entry created: id={entry.id}")
                _inspect_lines(entry, "create_journal_entry")
            except Exception as e:
                print(f"create_journal_entry FAILED: {e}")
                db.session.rollback()
                return 1

            # --- TEST 2: post_or_fail with concept codes ---
            print("\n--- TEST 2: post_or_fail ---")
            try:
                post_or_fail(
                    [
                        {
                            "concept_code": "AR",
                            "debit": Decimal("500.00"),
                            "description": "AR test",
                        },
                        {
                            "concept_code": "SALES_REVENUE",
                            "credit": Decimal("500.00"),
                            "description": "Revenue test",
                        },
                    ],
                    description="Test post_or_fail dynamic",
                    reference_type=GLRef.SALE,
                    reference_id=-1,
                    currency=tenant.default_currency or "AED",
                    tenant_id=tenant_id,
                )
                db.session.commit()
                # Find the entry we just created
                entry2 = GLJournalEntry.query.filter(
                    GLJournalEntry.description == "Test post_or_fail dynamic",
                    GLJournalEntry.tenant_id == tenant_id,
                ).order_by(GLJournalEntry.id.desc()).first()
                if entry2:
                    print(f"Entry created: id={entry2.id}")
                    _inspect_lines(entry2, "post_or_fail")
            except GlPostingError as e:
                print(f"post_or_fail FAILED: {e}")
                db.session.rollback()
                return 1
            except Exception as e:
                print(f"post_or_fail FAILED unexpectedly: {e}")
                db.session.rollback()
                return 1

            # --- TEST 3: Ensure no legacy codes appeared ---
            print("\n--- TEST 3: Legacy Code Audit ---")
            after_entries = db.session.execute(
                sa.text("""
                    SELECT gje.id, gje.description
                    FROM gl_journal_entries gje
                    WHERE gje.tenant_id = :tid AND gje.id > :before_id
                """),
                {"tid": tenant_id, "before_id": before_count}
            ).fetchall()

            violations = []
            for e_row in after_entries:
                lines = db.session.execute(
                    sa.text("""
                        SELECT ga.code, jl.description
                        FROM gl_journal_lines jl
                        JOIN gl_accounts ga ON ga.id = jl.account_id
                        WHERE jl.entry_id = :eid
                    """),
                    {"eid": e_row[0]}
                ).fetchall()
                for acct, desc in lines:
                    if acct in LEGACY_CODES:
                        violations.append(f"  Entry {e_row[0]} ('{e_row[1]}') line '{desc}' uses hardcoded code {acct}")

            if violations:
                print("FAIL: Legacy hardcoded codes detected!")
                for v in violations:
                    print(v)
                return 1
            else:
                print("PASS: Zero legacy hardcoded codes found in all test entries.")

            print("\n=== ALL TESTS PASSED ===")
            return 0

        finally:
            # Cleanup: delete test entries
            print("\n--- Cleanup ---")
            db.session.execute(
                sa.text("""
                    DELETE FROM gl_journal_lines
                    WHERE entry_id IN (
                        SELECT id FROM gl_journal_entries
                        WHERE tenant_id = :tid AND description LIKE 'Test%'
                    )
                """),
                {"tid": tenant_id}
            )
            db.session.execute(
                sa.text("""
                    DELETE FROM gl_journal_entries
                    WHERE tenant_id = :tid AND description LIKE 'Test%'
                """),
                {"tid": tenant_id}
            )
            db.session.commit()
            current_app.config['ENABLE_DYNAMIC_GL_MAPPING'] = flag_original
            print("Test data removed. Flag restored to original state.")


def _inspect_lines(entry, label):
    for line in entry.lines:
        acct_code = line.account.code if line.account else '???'
        concept = getattr(line, 'concept_code', None) or 'N/A'
        print(f"  {label} line: account={acct_code} concept={concept} "
              f"debit={line.debit} credit={line.credit}")


if __name__ == '__main__':
    sys.exit(main())
