from extensions import db
from sqlalchemy import text
import logging

logger = logging.getLogger(__name__)


class DatabaseOptimizer:
    @staticmethod
    def vacuum_postgres():
        if "postgresql" in str(db.engine.url):
            try:
                with db.engine.connect() as conn:
                    conn = conn.execution_options(isolation_level="AUTOCOMMIT")
                    conn.exec_driver_sql("VACUUM (ANALYZE)")
                logger.info("✅ PostgreSQL database optimized (VACUUM ANALYZE)")
                return {"success": True, "message": "Database optimized"}
            except Exception as e:
                logger.error(f"❌ Database optimization failed: {e}")
                return {"success": False, "error": str(e)}
        return {"success": False, "message": "Only PostgreSQL supported"}

    @staticmethod
    def analyze_tables():
        try:
            if "postgresql" in str(db.engine.url):
                db.session.execute(text("ANALYZE"))
                db.session.flush()
            logger.info("✅ Database tables analyzed")
            return {"success": True}
        except Exception as e:
            logger.error(f"❌ Table analysis failed: {e}")
            return {"success": False, "error": str(e)}

    @staticmethod
    def get_table_sizes():
        try:
            if "postgresql" in str(db.engine.url):
                result = db.session.execute(
                    text("""
                    SELECT c.relname AS table_name,
                           c.reltuples::bigint AS row_estimate
                    FROM pg_class c
                    JOIN pg_namespace n ON n.oid = c.relnamespace
                    WHERE n.nspname = 'public' AND c.relkind = 'r'
                    ORDER BY c.relname
                """)
                )

                tables = []
                for row in result:
                    tables.append({"table_name": row[0], "row_count": int(row[1] or 0)})

                return {"success": True, "tables": tables}

            return {"success": False, "message": "Only PostgreSQL supported"}

        except Exception as e:
            return {"success": False, "error": str(e)}

    @staticmethod
    def optimize_all():
        results = {}

        results["vacuum"] = DatabaseOptimizer.vacuum_postgres()
        results["analyze"] = DatabaseOptimizer.analyze_tables()
        results["sizes"] = DatabaseOptimizer.get_table_sizes()

        return results
