"""Delete fake activation GL entries to restore real data."""
import os, sys
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)
os.chdir(project_root)
os.environ["DATABASE_URL"] = "postgresql+psycopg2://postgres:123@localhost:5432/azad_uae"
os.environ["SKIP_SYSTEM_INTEGRITY"] = "1"

from app import create_app
from extensions import db
from sqlalchemy import text

app = create_app()


def delete_fake_entries():
    """Delete all fake activation entries (ADJ- prefix)."""
    with app.app_context():
        conn = db.engine.connect()
        
        # Count fake entries
        result = conn.execute(text("""
            SELECT COUNT(*) FROM gl_journal_entries 
            WHERE entry_number LIKE 'ADJ-%'
        """))
        count = result.scalar()
        
        print(f"Found {count} fake activation entries")
        
        if count == 0:
            print("No fake entries to delete")
            return
        
        # Delete GL lines first (cascade doesn't work as expected)
        conn.execute(text("""
            DELETE FROM gl_journal_lines 
            WHERE entry_id IN (
                SELECT id FROM gl_journal_entries 
                WHERE entry_number LIKE 'ADJ-%'
            )
        """))
        
        # Then delete the entries
        conn.execute(text("""
            DELETE FROM gl_journal_entries 
            WHERE entry_number LIKE 'ADJ-%'
        """))
        
        conn.commit()
        print(f"✅ Deleted {count} fake activation entries")
        
        # Verify remaining entries
        result = conn.execute(text("SELECT COUNT(*) FROM gl_journal_entries"))
        remaining = result.scalar()
        print(f"Remaining GL entries: {remaining}")
        
        # Verify remaining lines
        result = conn.execute(text("SELECT COUNT(*) FROM gl_journal_lines"))
        lines = result.scalar()
        print(f"Remaining GL lines: {lines}")


if __name__ == "__main__":
    delete_fake_entries()
