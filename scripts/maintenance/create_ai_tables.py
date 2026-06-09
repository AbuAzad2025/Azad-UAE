"""Create missing AI tables: ai_memories, ai_interactions, ai_expertise."""
import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from app import create_app
from extensions import db
from sqlalchemy import inspect

def create_ai_tables():
    app = create_app()
    with app.app_context():
        from models.ai import AiMemory, AiInteraction, AiExpertise
        inspector = inspect(db.engine)
        tables = inspector.get_table_names()
        for t in ["ai_memories", "ai_interactions", "ai_expertise"]:
            if t in tables:
                print(f"  Table {t} already exists — skipping.")
            else:
                print(f"  Creating table {t} ...")
        db.create_all()
        print("\nDone. Verifying:")
        inspector = inspect(db.engine)
        for t in ["ai_memories", "ai_interactions", "ai_expertise"]:
            status = "OK" if t in inspector.get_table_names() else "FAIL"
            print(f"  {t}: {status}")


if __name__ == "__main__":
    create_ai_tables()
