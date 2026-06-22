"""
Manual migration to add prices_include_vat and taxable_amount columns.

Tables affected:
- tenants: add prices_include_vat (boolean, default=False)
- branches: add prices_include_vat (boolean, default=False, nullable=True)
- sales: add prices_include_vat (boolean, default=False), taxable_amount (numeric, default=0)
- purchases: add prices_include_vat (boolean, default=False), taxable_amount (numeric, default=0)
"""

from sqlalchemy import create_engine, text

DATABASE_URL = "postgresql+psycopg2://postgres:123@localhost:5432/azad_uae"


def migrate():
    engine = create_engine(DATABASE_URL)
    with engine.connect() as conn:
        # tenants
        conn.execute(text("""
            ALTER TABLE tenants
            ADD COLUMN IF NOT EXISTS prices_include_vat BOOLEAN NOT NULL DEFAULT FALSE
        """))

        # branches
        conn.execute(text("""
            ALTER TABLE branches
            ADD COLUMN IF NOT EXISTS prices_include_vat BOOLEAN DEFAULT FALSE
        """))

        # sales
        conn.execute(text("""
            ALTER TABLE sales
            ADD COLUMN IF NOT EXISTS prices_include_vat BOOLEAN NOT NULL DEFAULT FALSE
        """))
        conn.execute(text("""
            ALTER TABLE sales
            ADD COLUMN IF NOT EXISTS taxable_amount NUMERIC(15, 3) NOT NULL DEFAULT 0
        """))

        # purchases
        conn.execute(text("""
            ALTER TABLE purchases
            ADD COLUMN IF NOT EXISTS prices_include_vat BOOLEAN NOT NULL DEFAULT FALSE
        """))
        conn.execute(text("""
            ALTER TABLE purchases
            ADD COLUMN IF NOT EXISTS taxable_amount NUMERIC(15, 3) NOT NULL DEFAULT 0
        """))

        conn.commit()
        print("[OK] Migration applied successfully.")


if __name__ == '__main__':
    migrate()
