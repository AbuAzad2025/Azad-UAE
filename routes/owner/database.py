"""Database tools, SQL console, and maintenance routes for the owner blueprint."""

from routes.owner import (
    render_template,
    request,
    jsonify,
    flash,
    redirect,
    url_for,
    current_app,
    current_user,
    text,
    inspect,
    db,
    AuditLog,
    ArchivedRecord,
    owner_required,
)
from services.logging_core import LoggingCore
from routes.owner import owner_bp
from utils.db_safety import atomic_transaction
from routes.owner.shared import (
    _invalidate_owner_changes,
    _audit_owner_db_action,
    _mask_db_uri,
    _validate_select_only_sql,
    _resolve_browsable_table,
    _resolve_truncatable_table,
    _resolve_known_table,
    _known_tables_map,
    _is_sensitive_stats_table,
    _inspector_column_names,
    _validate_postgresql_uri,
    _is_blocked_table,
)

import logging
import os
import json
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)

_EXPORT_FORMATS = frozenset({"sql", "json"})


@owner_bp.route("/database-tools")
@owner_required
def database_tools():
    from sqlalchemy import text, inspect

    inspector = inspect(db.engine)
    tables_info = []
    restricted_count = 0

    for table_name in inspector.get_table_names():
        safe_table = _resolve_known_table(table_name)
        if not safe_table:
            continue
        if _is_sensitive_stats_table(safe_table):
            restricted_count += 1
            continue

        columns = inspector.get_columns(safe_table)
        indexes = inspector.get_indexes(safe_table)
        row_count = db.session.execute(
            text(f'SELECT COUNT(*) FROM "{safe_table}"')  # nosec B608
        ).scalar()

        tables_info.append(
            {
                "name": safe_table,
                "columns_count": len(columns),
                "indexes_count": len(indexes),
                "rows_count": row_count,
            }
        )

    _audit_owner_db_action(
        "view_database_tools",
        {
            "visible_tables": len(tables_info),
            "restricted_tables": restricted_count,
        },
    )

    return render_template(
        "owner/database_tools.html",
        tables=tables_info,
        restricted_tables=restricted_count,
    )


@owner_bp.route("/execute-query", methods=["POST"])
@owner_required
def execute_query():
    from sqlalchemy import text

    query_text = request.form.get("query", "").strip()

    if not query_text:
        return jsonify({"error": "Query is empty"}), 400

    ok, validation_error = _validate_select_only_sql(query_text)
    if not ok:
        current_app.logger.warning(
            "execute_query rejected user_id=%s reason=%s",
            current_user.id,
            validation_error,
        )
        return jsonify({"error": validation_error}), 400

    try:
        result = db.session.execute(text(query_text))

        rows = result.fetchall()
        columns = result.keys()

        data = [dict(zip(columns, row)) for row in rows]

        _audit_owner_db_action(
            "execute_query", {"query_prefix": query_text[:200], "row_count": len(data)}
        )

        return jsonify({"success": True, "rows": data, "count": len(data)})

    except Exception:
        current_app.logger.exception("Owner database query failed")
        return jsonify({"error": "تعذر تنفيذ الاستعلام حالياً"}), 400


@owner_bp.route("/clear-cache", methods=["POST"])
@owner_required
def clear_cache():
    from extensions import cache

    try:
        cache.clear()
        flash("✅ تم مسح الذاكرة المؤقتة بنجاح", "success")
    except Exception as e:
        LoggingCore.log_error(
            message=f"Cache clear failed: {e}",
            category="BACKEND",
            level="WARNING",
            source="routes.owner.clear_cache",
            exception=e,
        )
        # If Redis is down, gracefully degrade to null cache temporarily
        try:
            cache_type = getattr(cache, "cache", None)
            type_name = type(cache_type).__name__ if cache_type else "unknown"
            if type_name != "NullCache":
                app = cache.app if hasattr(cache, "app") else None
                if app:
                    cache.init_app(app, config={"CACHE_TYPE": "null"})
            flash("⚠️ Redis غير متاح — تم التبديل لـ null cache وتجاوز الخطأ", "warning")
        except Exception as inner:
            LoggingCore.log_error(
                message=f"Cache fallback to null also failed: {inner}",
                category="BACKEND",
                level="ERROR",
                source="routes.owner.clear_cache.fallback",
                exception=inner,
            )
            flash(f"❌ خطأ: {str(e)}", "danger")

    return redirect(url_for("owner.dashboard"))


@owner_bp.route("/truncate-table", methods=["POST"])
@owner_required
def truncate_table():
    """مسح جدول بالكامل"""
    table_name = request.form.get("table_name")
    confirm = request.form.get("confirm")

    if confirm != "YES_DELETE_ALL":
        flash("❌ يجب كتابة YES_DELETE_ALL للتأكيد", "danger")
        return redirect(url_for("owner.database_tools"))

    safe_table = _resolve_truncatable_table(str(table_name or ""))
    if not safe_table:
        current_app.logger.warning(
            "truncate_table rejected table=%r user_id=%s",
            table_name,
            current_user.id,
        )
        flash("❌ جدول غير معروف أو محمي — لا يمكن مسحه", "danger")
        return redirect(url_for("owner.database_tools"))

    try:
        with atomic_transaction("truncate_table"):
            db.session.execute(text(f"DELETE FROM {safe_table}"))  # nosec B608

        LoggingCore.log_audit(
            "truncate_table",
            "database",
            0,
            {"table": safe_table, "requested_name": table_name},
        )

        flash(f"✅ تم مسح جدول {safe_table} بنجاح", "success")
    except Exception as e:
        flash(f"❌ خطأ: {str(e)}", "danger")

    return redirect(url_for("owner.database_tools"))


@owner_bp.route("/browse-table/<table_name>")
@owner_required
def browse_table(table_name):
    """تصفح محتويات جدول"""
    page = request.args.get("page", 1, type=int)
    per_page = 50

    safe_table = _resolve_browsable_table(table_name)
    if not safe_table:
        flash("❌ جدول غير معروف أو غير مسموح", "danger")
        return redirect(url_for("owner.database_tools"))

    try:
        count_result = db.session.execute(text(f'SELECT COUNT(*) FROM "{safe_table}"'))  # nosec B608
        total = count_result.scalar()

        offset = (page - 1) * per_page
        result = db.session.execute(
            text(f'SELECT * FROM "{safe_table}" LIMIT {per_page} OFFSET {offset}')  # nosec B608
        )

        rows = result.fetchall()
        columns = result.keys()

        total_pages = (total + per_page - 1) // per_page

        return render_template(
            "owner/browse_table.html",
            table_name=safe_table,
            columns=columns,
            rows=rows,
            page=page,
            total_pages=total_pages,
            total=total,
        )

    except Exception as e:
        flash(f"❌ خطأ: {str(e)}", "danger")
        return redirect(url_for("owner.database_tools"))


@owner_bp.route("/update-row/<table_name>/<int:row_id>", methods=["POST"])
@owner_required
def update_row(table_name, row_id):
    """تحديث صف في جدول — للتعديل المرئي من أدوات قاعدة البيانات."""
    safe_table = _resolve_browsable_table(table_name)
    if not safe_table:
        return jsonify({"success": False, "error": "جدول غير مسموح"}), 403

    updates = request.get_json(silent=True) or {}
    if not updates:
        return jsonify({"success": False, "error": "لا توجد بيانات للتحديث"}), 400

    try:
        inspector = inspect(db.engine)
        columns = {col["name"] for col in inspector.get_columns(safe_table)}
        pk_cols = (
            inspector.get_pk_constraint(safe_table).get("constrained_columns") or []
        )
        if not pk_cols:
            return jsonify({"success": False, "error": "الجدول بدون مفتاح أساسي"}), 400
        pk_name = pk_cols[0]

        safe_updates = {}
        for col, val in updates.items():
            if col not in columns or col == pk_name:
                continue
            safe_updates[col] = val if val != "" else None

        if not safe_updates:
            return jsonify({"success": False, "error": "لا حقول صالحة للتحديث"}), 400

        set_clause = ", ".join(f'"{k}" = :{k}' for k in safe_updates)
        params = dict(safe_updates)
        params["row_id"] = row_id

        with atomic_transaction("update_table_row"):
            db.session.execute(
                text(
                    f'UPDATE "{safe_table}" SET {set_clause} WHERE "{pk_name}" = :row_id'
                ),  # nosec B608
                params,
            )

        LoggingCore.log_audit(
            "update_row",
            "database",
            row_id,
            {"table": safe_table, "columns": list(safe_updates.keys())},
        )
        return jsonify({"success": True})
    except Exception:
        current_app.logger.exception("Owner table row update failed")
        return jsonify({"success": False, "error": "تعذر تحديث السجل حالياً"}), 500


@owner_bp.route("/edit-table-data/<table_name>")
@owner_required
def edit_table_data(table_name):
    """تعديل بيانات الجدول"""
    safe_table = _resolve_browsable_table(table_name)
    if not safe_table:
        flash("❌ جدول غير معروف أو غير مسموح", "danger")
        return redirect(url_for("owner.database_tools"))

    try:
        result = db.session.execute(text(f'SELECT * FROM "{safe_table}" LIMIT 100'))  # nosec B608
        rows = result.fetchall()
        columns = result.keys()

        return render_template(
            "owner/edit_table.html", table_name=safe_table, columns=columns, rows=rows
        )

    except Exception as e:
        flash(f"❌ خطأ: {str(e)}", "danger")
        return redirect(url_for("owner.database_tools"))


@owner_bp.route("/sql-console", methods=["GET", "POST"])
@owner_required
def sql_console():
    """SQL Console - تنفيذ استعلامات مباشرة"""
    result_data = None
    error = None

    if request.method == "POST":
        sql_query = request.form.get("sql_query", "").strip()
        ok, validation_error = _validate_select_only_sql(sql_query)
        if not ok:
            error = validation_error
        else:
            try:
                result = db.session.execute(text(sql_query))
                rows = result.fetchall()
                columns = result.keys()
                result_data = {
                    "columns": list(columns),
                    "rows": [list(row) for row in rows],
                    "count": len(rows),
                }

                LoggingCore.log_audit(
                    "sql_execute",
                    "database",
                    0,
                    {"query": sql_query[:200]},
                )

            except Exception as e:
                error = str(e)

    return render_template("owner/sql_console.html", result=result_data, error=error)


@owner_bp.route("/export-database", methods=["POST"])
@owner_required
def export_database():
    """تصدير قاعدة البيانات"""
    export_format = (request.form.get("format") or "sql").strip().lower()

    if export_format not in _EXPORT_FORMATS:
        flash("❌ صيغة تصدير غير مدعومة", "danger")
        return redirect(url_for("owner.database_tools"))

    try:
        backup_dir = "instance/backups/exports"
        os.makedirs(backup_dir, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        if export_format == "sql":
            filename = f"db_export_{timestamp}.sql"
            filepath = os.path.join(backup_dir, filename)
            from services.backup_service import BackupService
            from services.backup_exec import run_pg_tool

            params = BackupService._parse_db_url()
            pg_dump = BackupService._resolve_pg_tool("pg_dump", "PG_DUMP_PATH")
            if not params or not pg_dump:
                flash("pg_dump غير متوفر", "danger")
                return redirect(url_for("owner.list_backups"))
            env = os.environ.copy()
            if params.get("password"):
                env["PGPASSWORD"] = params["password"]
            cmd = [
                pg_dump,
                "--host",
                params["host"],
                "--port",
                params["port"],
                "--username",
                params["username"],
                "--file",
                filepath,
                params["dbname"],
            ]
            proc = run_pg_tool(cmd, env=env, timeout=3600)
            if proc.returncode != 0:
                raise RuntimeError(
                    (proc.stderr or proc.stdout or "pg_dump failed")[:200]
                )

            flash(f"✅ تم التصدير: {filename}", "success")
            _audit_owner_db_action(
                "export_database", {"format": "sql", "filename": filename}
            )

        elif export_format == "json":
            filename = f"db_export_{timestamp}.json"
            filepath = os.path.join(backup_dir, filename)

            export_data = {}
            for table_name in _known_tables_map().values():
                if _is_blocked_table(table_name):
                    continue
                result = db.session.execute(text(f"SELECT * FROM {table_name}"))  # nosec B608
                rows = result.fetchall()
                columns = result.keys()

                export_data[table_name] = [dict(zip(columns, row)) for row in rows]

            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(export_data, f, ensure_ascii=False, indent=2, default=str)

            flash(f"✅ تم التصدير: {filename}", "success")
            _audit_owner_db_action(
                "export_database",
                {"format": "json", "filename": filename, "tables": len(export_data)},
            )

    except Exception as e:
        current_app.logger.error(
            "export_database failed user_id=%s: %s", current_user.id, e
        )
        flash(f"❌ خطأ في التصدير: {str(e)}", "danger")

    return redirect(url_for("owner.database_tools"))


@owner_bp.route("/convert-database", methods=["GET", "POST"])
@owner_required
def convert_database():
    """تحويل بين أنواع قواعد البيانات"""
    if request.method == "POST":
        target_db = (request.form.get("target_db") or "").strip()

        if not target_db:
            flash("⚠️ يرجى اختيار قاعدة البيانات المستهدفة.", "warning")
            return render_template("owner/convert_database.html")

        if target_db != "postgresql":
            flash("❌ هذا النظام يدعم PostgreSQL فقط.", "danger")
            return render_template("owner/convert_database.html")

        new_uri = (request.form.get("postgresql_uri") or "").strip()
        if not _validate_postgresql_uri(new_uri):
            flash("❌ رابط PostgreSQL غير صالح.", "danger")
            current_app.logger.warning(
                "convert_database rejected invalid URI user_id=%s",
                current_user.id,
            )
            return render_template("owner/convert_database.html")

        flash("🔄 جاري التحويل إلى PostgreSQL...", "info")

        try:
            from sqlalchemy import create_engine

            target_engine = create_engine(new_uri)

            tables_copied = 0
            rows_copied = 0

            with target_engine.begin() as conn:
                for table_name in _known_tables_map().values():
                    if _is_blocked_table(table_name):
                        continue

                    allowed_columns = _inspector_column_names(table_name)
                    if not allowed_columns:
                        continue

                    result = db.session.execute(text(f"SELECT * FROM {table_name}"))  # nosec B608
                    rows = result.fetchall()
                    if not rows:
                        continue

                    row_columns = [c for c in result.keys() if c in allowed_columns]
                    if not row_columns:
                        continue

                    quoted_cols = ", ".join(f'"{c}"' for c in row_columns)
                    placeholders = ", ".join(f":{c}" for c in row_columns)
                    insert_sql = f'INSERT INTO "{table_name}" ({quoted_cols}) VALUES ({placeholders})'

                    for row in rows:
                        row_dict = dict(zip(result.keys(), row))
                        payload = {col: row_dict[col] for col in row_columns}
                        conn.execute(text(insert_sql), payload)
                        rows_copied += 1

                    tables_copied += 1

            flash("✅ تم التحويل إلى PostgreSQL بنجاح!", "success")
            _audit_owner_db_action(
                "convert_database",
                {
                    "target": _mask_db_uri(new_uri),
                    "tables_copied": tables_copied,
                    "rows_copied": rows_copied,
                },
            )

        except Exception as e:
            current_app.logger.error(
                "convert_database failed user_id=%s target=%s: %s",
                current_user.id,
                _mask_db_uri(new_uri),
                e,
            )
            flash(f"❌ خطأ في التحويل: {str(e)}", "danger")

    return render_template("owner/convert_database.html")


@owner_bp.route("/database-optimize", methods=["POST"])
@owner_required
def database_optimize():
    try:
        from utils.database_optimizer import DatabaseOptimizer

        vacuum_result = DatabaseOptimizer.vacuum_postgres()
        analyze_result = DatabaseOptimizer.analyze_tables()
        if vacuum_result.get("success") and analyze_result.get("success"):
            flash("✅ تم تحسين قاعدة البيانات وتحليل الجداول بنجاح", "success")
        else:
            msg = (
                vacuum_result.get("error")
                or analyze_result.get("error")
                or "عملية التحسين لم تكتمل"
            )
            flash(f"⚠️ تحذير: {msg}", "warning")
    except Exception as e:
        flash(f"❌ خطأ في التحسين: {str(e)}", "danger")

    return redirect(url_for("owner.system_health"))


@owner_bp.route("/verify-backups")
@owner_required
def verify_backups():
    try:
        from services.backup_service import BackupService

        backups = BackupService.list_backups()

        verified = []
        for backup in backups:
            fn = backup.get("filename", "")
            result = BackupService.verify_backup(fn) if fn else {"valid": False}
            verified.append(
                {
                    "filename": fn or "Unknown",
                    "size": backup.get("size_mb", 0),
                    "created": backup.get(
                        "datetime", backup.get("timestamp", "Unknown")
                    ),
                    "valid": bool(result.get("valid")),
                    "format": result.get("format"),
                    "errors": result.get("errors", []),
                }
            )

        return render_template("owner/verify_backups.html", backups=verified)

    except Exception as e:
        flash(f"خطأ في تحميل النسخ الاحتياطية: {str(e)}", "danger")
        return redirect(url_for("owner.dashboard"))


@owner_bp.route("/data-cleanup", methods=["GET", "POST"])
@owner_required
def data_cleanup():
    if request.method == "POST":
        days = request.form.get("days", 90, type=int)
        cleanup_type = (request.form.get("cleanup_type") or "").strip()

        if not cleanup_type:
            flash("⚠️ يرجى اختيار نوع البيانات للحذف.", "warning")
            stats = {
                "old_logs": AuditLog.query.filter(
                    AuditLog.created_at
                    < datetime.now(timezone.utc) - timedelta(days=90)
                ).count(),
                "old_archived": ArchivedRecord.query.filter(
                    ArchivedRecord.archived_at
                    < datetime.now(timezone.utc) - timedelta(days=180)
                ).count(),
            }
            return render_template("owner/data_cleanup.html", stats=stats)

        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)
        deleted_count = 0

        try:
            with atomic_transaction("data_cleanup"):
                if cleanup_type == "logs":
                    deleted_count = AuditLog.query.filter(
                        AuditLog.created_at < cutoff_date
                    ).delete()
                elif cleanup_type == "archived":
                    deleted_count = ArchivedRecord.query.filter(
                        ArchivedRecord.archived_at < cutoff_date
                    ).delete()
        except Exception as e:
            flash(f"❌ خطأ في التنظيف: {str(e)}", "danger")
            return redirect(url_for("owner.data_cleanup"))
        _invalidate_owner_changes()
        flash(f"✅ تم حذف {deleted_count} سجل قديم", "success")
        return redirect(url_for("owner.data_cleanup"))

    stats = {
        "old_logs": AuditLog.query.filter(
            AuditLog.created_at < datetime.now(timezone.utc) - timedelta(days=90)
        ).count(),
        "old_archived": ArchivedRecord.query.filter(
            ArchivedRecord.archived_at
            < datetime.now(timezone.utc) - timedelta(days=180)
        ).count(),
    }

    return render_template("owner/data_cleanup.html", stats=stats)


@owner_bp.route("/import-export-tools")
@owner_required
def import_export_tools():
    return render_template("owner/import_export_tools.html")


@owner_bp.route("/export-excel/<table_name>")
@owner_required
def export_excel(table_name):
    normalized = (table_name or "").strip().lower()
    if _is_blocked_table(normalized) or _is_blocked_table(table_name):
        current_app.logger.warning(
            "export_excel rejected entity=%r user_id=%s (tenant business table)",
            table_name,
            current_user.id,
        )
        flash("❌ تصدير جداول بيانات المستأجرين محظور من لوحة المالك", "danger")
        return redirect(url_for("owner.import_export_tools"))

    flash("❌ جدول غير موجود", "danger")
    return redirect(url_for("owner.import_export_tools"))


@owner_bp.route("/api/recent-audit-logs")
@owner_required
def api_recent_audit_logs():
    """API endpoint for maintenance audit log display."""
    from models import AuditLog
    from sqlalchemy import desc

    logs = (
        AuditLog.query.filter(
            AuditLog.action.in_(["fix_cost_centers", "rebuild_gl_tree"])
        )
        .order_by(desc(AuditLog.created_at))
        .limit(20)
        .all()
    )

    return jsonify(
        {
            "logs": [
                {
                    "timestamp": log.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                    "action": log.action,
                    "success": (
                        log.metadata.get("success", True) if log.metadata else True
                    ),
                    "details": log.details or "",
                }
                for log in logs
            ]
        }
    )
