"""
💻 محرك توليد الأكواد - Code Generation Engine
توليد أكواد Python/SQL/JavaScript تلقائياً

القدرات:
- توليد queries SQL
- توليد Python scripts
- توليد تقارير
- توليد API calls
- إصلاح الأكواد
- تحسين الأكواد
"""

import logging
import re
from typing import Any, List, Optional

from sqlalchemy import and_, column, insert, select, table as sa_table, update

logger = logging.getLogger(__name__)

_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _ident(name: str) -> str:
    """Validate a SQL identifier (table/column name); raise if unsafe."""
    if not isinstance(name, str) or not _IDENT_RE.match(name):
        raise ValueError(f"unsafe SQL identifier: {name!r}")
    return name


def _col(table_name: str, col_name: str):
    """Return a bound column expression for ``col_name`` on ``table_name``."""
    return column(col_name)


def _build_where(table_name: str, filters: Optional[dict], prefix: str):
    """Build an SQLAlchemy boolean expression for a WHERE clause (literal values).

    Values are embedded as SQL literals (this helper produces display SQL for an
    AI assistant, not an executed statement), while table/column identifiers are
    validated to prevent injection of arbitrary SQL.
    """
    if not filters or "where" not in filters:
        return None
    clauses = []
    for _i, (k, v) in enumerate(filters["where"].items()):
        clauses.append(_col(table_name, _ident(k)) == v)
    return and_(*clauses) if len(clauses) > 1 else clauses[0]


class CodeGenerator:
    """
    محرك توليد الأكواد الذكي

    يولد:
    - SQL queries للتقارير
    - Python scripts للعمليات
    - JavaScript للواجهات
    - API endpoints
    """

    def __init__(self):
        self.templates = self._load_templates()
        self.generated_code_history = []

    @staticmethod
    def _load_templates():
        """تحميل قوالب الأكواد"""
        return {
            "sql_select": "SELECT {columns} FROM {table} WHERE {conditions}",
            "sql_insert": "INSERT INTO {table} ({columns}) VALUES ({values})",
            "sql_update": "UPDATE {table} SET {updates} WHERE {conditions}",
            "python_function": """def {function_name}({params}):
    \"\"\"{docstring}\"\"\"
    {body}
    return {return_value}""",
            "api_endpoint": """@{blueprint}_bp.route('/{path}', methods=['{method}'])
@login_required
def {function_name}():
    \"\"\"{docstring}\"\"\"
    {body}""",
        }

    @staticmethod
    def generate_sql_query(intent: str, table: str, filters: Optional[dict] = None) -> str:
        """
        توليد SQL query تلقائياً

        Args:
            intent: 'select' | 'insert' | 'update' | 'delete'
            table: اسم الجدول
            filters: شروط البحث

        Returns:
            SQL query جاهز
        """
        try:
            if intent == "select":
                table_name = _ident(table)
                tbl = sa_table(table_name)
                cols = (
                    [_col(table_name, _ident(c)) for c in filters.get("columns", [])]
                    if filters and filters.get("columns")
                    else [column("*")]
                )
                stmt: Any = select(*cols).select_from(tbl)
                where_expr = _build_where(table_name, filters, "w")
                if where_expr is not None:
                    stmt = stmt.where(where_expr)
                if filters and "order_by" in filters:
                    stmt = stmt.order_by(_col(table_name, _ident(filters["order_by"])))
                if filters and "limit" in filters:
                    stmt = stmt.limit(int(filters["limit"]))
                return str(stmt)

            elif intent == "insert":
                table_name = _ident(table)
                if filters and filters.get("values") and filters.get("columns"):
                    col_names = [_ident(c) for c in filters["columns"]]
                    row = dict(zip(col_names, filters["values"]))
                    # Build a lightweight table carrying exactly the declared
                    # columns so the Core construct can render without touching
                    # the live schema (this is display SQL for an AI assistant).
                    tbl = sa_table(table_name, *[column(c) for c in col_names])
                    stmt = insert(tbl).values(**row)
                else:
                    stmt = insert(sa_table(table_name))
                return str(stmt)

            elif intent == "update":
                table_name = _ident(table)
                set_kwargs = {}
                if filters and filters.get("set"):
                    for k, v in filters["set"].items():
                        set_kwargs[_ident(k)] = v
                col_names = list(set_kwargs.keys())
                tbl = sa_table(table_name, *[column(c) for c in col_names]) if col_names else sa_table(table_name)
                stmt = update(tbl)
                if set_kwargs:
                    stmt = stmt.values(**set_kwargs)
                where_expr = _build_where(table_name, filters, "u")
                if where_expr is not None:
                    stmt = stmt.where(where_expr)
                return str(stmt)

            else:
                return f"-- Unsupported intent: {intent}"

        except Exception as e:
            logger.error(f"SQL generation failed: {e}")
            return f"-- Error: {e}"

    @staticmethod
    def generate_python_function(function_name: str, purpose: str, params: Optional[List[str]] = None) -> str:
        """
        توليد دالة Python

        Args:
            function_name: اسم الدالة
            purpose: الغرض منها
            params: المعاملات

        Returns:
            كود Python جاهز
        """
        try:
            params_str = ", ".join(params) if params else ""

            # توليد الجسم حسب الغرض
            if "حساب" in purpose or "calculate" in purpose.lower():
                body = """    # حسابات
    result = 0
    # أضف المنطق هنا
    return result"""

            elif "توقع" in purpose or "predict" in purpose.lower():
                body = """    # توقعات
    from services.ai_service import AIService
    prediction = AIService.predict_sales_trend()
    return prediction"""

            elif "بحث" in purpose or "search" in purpose.lower():
                body = """    # بحث
    from models import Product
    results = Product.query.filter_by(name=query).all()
    return results"""

            else:
                body = """    # منطق الدالة
    pass
    return None"""

            code = f'''def {function_name}({params_str}):
    """
    {purpose}
    
    Args:
        {", ".join(params) if params else "None"}
    
    Returns:
        result
    """
{body}
'''

            return code

        except Exception as e:
            logger.error(f"Python generation failed: {e}")
            return f"# Error: {e}"

    @staticmethod
    def generate_report_query(report_type: str, date_range: Optional[dict] = None) -> str:
        """
        توليد query لتقرير محدد

        Args:
            report_type: 'sales' | 'inventory' | 'financial' | 'customers'
            date_range: {start_date, end_date}

        Returns:
            SQL query للتقرير
        """
        try:
            if report_type == "sales":
                if not date_range:
                    return "-- Missing date range"
                sales_sql = "\n".join(
                    [
                        "SELECT",
                        "    DATE(sale_date) as date,",
                        "    COUNT(*) as sales_count,",
                        "    SUM(amount_aed) as total_sales,",
                        "    AVG(amount_aed) as avg_sale",
                        "FROM sales",
                        "WHERE status = 'confirmed'",
                        f"  AND sale_date BETWEEN '{date_range['start_date']}' AND '{date_range['end_date']}'",
                        "GROUP BY DATE(sale_date)",
                        "ORDER BY date DESC",
                    ]
                )
                return sales_sql

            elif report_type == "inventory":
                return """
SELECT 
    p.name,
    p.sku,
    p.current_stock,
    p.min_stock_alert,
    p.cost_price,
    (p.current_stock * p.cost_price) as stock_value
FROM products p
WHERE p.is_active = TRUE
ORDER BY stock_value DESC
"""

            elif report_type == "customers":
                return """
SELECT 
    c.name,
    c.customer_type,
    COUNT(s.id) as total_orders,
    SUM(s.amount_aed) as total_purchases,
    MAX(s.sale_date) as last_purchase
FROM customers c
LEFT JOIN sales s ON c.id = s.customer_id
WHERE c.is_active = TRUE
GROUP BY c.id
ORDER BY total_purchases DESC
"""

            else:
                return f"-- Unknown report type: {report_type}"

        except Exception as e:
            logger.error(f"Report query generation failed: {e}")
            return f"-- Error: {e}"

    @staticmethod
    def fix_code(broken_code: str, error_message: str) -> dict:
        """
        إصلاح كود معطوب

        Args:
            broken_code: الكود المعطوب
            error_message: رسالة الخطأ

        Returns:
            {
                'fixed_code': الكود المصلح,
                'explanation': شرح الإصلاح,
                'changes': التغييرات
            }
        """
        changes = []

        # إصلاحات شائعة
        fixed_code = broken_code

        # 1. إصلاح الاقتباسات
        if "SyntaxError" in error_message and "quote" in error_message:
            fixed_code = fixed_code.replace("'", '"')
            changes.append("تم تصحيح الاقتباسات")

        # 2. إصلاح المسافات البادئة
        if "IndentationError" in error_message:
            lines = fixed_code.split("\n")
            fixed_lines = []
            for line in lines:
                # إزالة المسافات الزائدة
                stripped = line.lstrip()
                # إضافة مسافات صحيحة (4 spaces)
                if stripped.startswith("def ") or stripped.startswith("class "):
                    fixed_lines.append(stripped)
                elif stripped:
                    fixed_lines.append("    " + stripped)
                else:
                    fixed_lines.append("")

            fixed_code = "\n".join(fixed_lines)
            changes.append("تم تصحيح المسافات البادئة")

        # 3. إصلاح الاستيرادات المفقودة
        if "NameError" in error_message or "not defined" in error_message:
            # استخراج الاسم المفقود
            import re

            match = re.search(r"name '(\w+)' is not defined", error_message)
            if match:
                missing_name = match.group(1)

                # إضافة import محتمل
                if missing_name in ["db", "func"]:
                    fixed_code = f"from extensions import {missing_name}\n" + fixed_code
                    changes.append(f"أضفت استيراد: {missing_name}")

        explanation = "تم تحليل الخطأ وإصلاحه:\n" + "\n".join(f"- {c}" for c in changes)

        return {
            "fixed_code": fixed_code,
            "explanation": explanation,
            "changes": changes,
            "confidence": 0.7 if changes else 0.3,
        }

    @staticmethod
    def optimize_code(code: str) -> dict:
        """
        تحسين وتسريع الكود

        Returns:
            {
                'optimized_code': الكود المحسن,
                'improvements': التحسينات,
                'performance_gain': نسبة التحسين المتوقعة
            }
        """
        improvements = []
        optimized = code

        # 1. استخدام list comprehension بدلاً من loops
        if "for " in code and "append(" in code:
            improvements.append("يمكن استخدام list comprehension للسرعة")

        # 2. استخدام bulk operations في DB
        if code.count("db.session.add(") > 5:
            improvements.append("استخدم db.session.bulk_insert_mappings للسرعة")

        # 3. استخدام query optimization
        if ".all()" in code and "filter" in code:
            improvements.append("استخدم .limit() لتقليل البيانات المسترجعة")

        performance_gain = len(improvements) * 15  # تقدير تقريبي

        return {
            "optimized_code": optimized,
            "improvements": improvements,
            "performance_gain_percent": min(performance_gain, 80),
            "confidence": 0.8,
        }


# ============================================================================
# Singleton
# ============================================================================

_code_generator_instance = None


def get_code_generator():
    """الحصول على مولد الأكواد"""
    global _code_generator_instance
    if _code_generator_instance is None:
        _code_generator_instance = CodeGenerator()
    return _code_generator_instance
