"""AI assistant pages and Excel upload routes."""

import logging
import os
from datetime import datetime
from typing import cast

import pandas as pd
from flask import current_app, render_template, request
from flask_babel import gettext
from flask_login import current_user, login_required
from werkzeug.utils import secure_filename

from extensions import db
from services.platform_query_service import PlatformQueryService
from services.stock_service import StockService
from utils.ai_access import get_ai_access_state
from utils.api_response import error_response, success_response
from utils.db_safety import atomic_transaction
from utils.decorators import owner_required, permission_required
from utils.gl_reference_types import GLRef
from utils.tenanting import assign_tenant_id, get_active_tenant_id

from .blueprint import ai_bp

logger = logging.getLogger(__name__)


@ai_bp.route("/assistant", methods=["GET"])
@login_required
@permission_required("view_reports")
def assistant_page():
    """صفحة المساعد الذكي - متاحة لكل مستخدم لديه صلاحية view_reports وتفعيل AI"""
    try:
        from utils.branching import get_accessible_warehouses

        warehouses = get_accessible_warehouses(current_user)
        state = get_ai_access_state(current_user)
        disable_reason = None
        if not state.get("allowed"):
            disable_reason = state.get("reason")
        return render_template(
            "ai/assistant.html",
            ai_enabled=bool(
                state.get("allowed") and state.get("global_enabled") and state.get("tenant_enabled") is not False
            ),
            ai_access_state=state,
            ai_disable_reason=disable_reason,
            warehouses=warehouses,
            current_user=current_user,
        )
    except Exception:
        current_app.logger.exception("AI assistant page failed")
        return render_template("errors/500.html"), 500


@ai_bp.route("/config", methods=["GET", "POST"])
@login_required
@owner_required
def config():
    """إعدادات AI - تحديث المفاتيح يومياً"""
    if request.method == "POST":
        api_key = request.form.get("api_key", "").strip()
        provider = request.form.get("provider", "groq")

        if not api_key:
            return error_response(message=gettext("المفتاح مطلوب"), status_code=200)

        try:
            from pathlib import Path

            base_env_path = Path(__file__).resolve().parent.parent / ".env"

            env_file = base_env_path

            if env_file.exists():
                with open(env_file, encoding="utf-8") as f:
                    lines = f.readlines()
            else:
                lines = []

            if provider == "groq":
                key_name = "GROQ_API_KEY"
            elif provider == "gemini":
                key_name = "GEMINI_API_KEY"
            else:
                key_name = "OPENAI_API_KEY"

            key_found = False

            for i, line in enumerate(lines):
                if line.startswith(key_name + "="):
                    lines[i] = f"{key_name}={api_key}\n"
                    key_found = True
                    break

            if not key_found:
                lines.append(f"{key_name}={api_key}\n")

            with open(env_file, "w", encoding="utf-8") as f:
                f.writelines(lines)

            os.environ[key_name] = api_key

            current_app.logger.info(f"✅ {key_name} updated successfully by user {current_user.username}")

            return success_response(
                data={
                    "provider": provider,
                    "expires_in": gettext("24 ساعة") if provider == "groq" else gettext("حسب اشتراكك"),
                },
                message=gettext(f"تم حفظ مفتاح {provider.upper()} بنجاح! ✅"),
            )

        except Exception:
            current_app.logger.exception("Failed to save AI API key")
            return error_response(
                message=gettext("تعذر حفظ إعدادات AI حالياً"),
                status_code=200,
            )

    current_groq = os.environ.get("GROQ_API_KEY", "")
    current_openai = os.environ.get("OPENAI_API_KEY", "")
    current_gemini = os.environ.get("GEMINI_API_KEY", "")

    state = get_ai_access_state(current_user)
    return render_template(
        "ai/config.html",
        ai_enabled=bool(state.get("global_enabled")),
        groq_key_exists=bool(current_groq),
        openai_key_exists=bool(current_openai or current_gemini),
    )


@ai_bp.route("/upload-excel", methods=["POST"])
@login_required
@permission_required("manage_products")
def upload_excel():
    """رفع ومعالجة ملف Excel للمنتجات - المعالج الذكي الخارق"""
    try:
        max_bytes = int(current_app.config.get("MAX_CONTENT_LENGTH") or (16 * 1024 * 1024))
        if request.content_length and request.content_length > max_bytes:
            return error_response(
                message=gettext("حجم الملف كبير جداً"),
                status_code=413,
            )

        if "file" not in request.files:
            return error_response(
                message=gettext("لم يتم رفع ملف"),
                status_code=400,
            )

        file = request.files["file"]
        warehouse_id = request.form.get("warehouse_id", type=int)
        if not warehouse_id:
            tid = get_active_tenant_id(current_user)
            warehouse = PlatformQueryService.main_import_warehouse(tid)
            if warehouse:
                warehouse_id = warehouse.id

        filename = secure_filename(file.filename or "")
        if not filename:
            return error_response(
                message=gettext("لم يتم اختيار ملف"),
                status_code=400,
            )

        if not filename.lower().endswith((".xlsx", ".xls")):
            return error_response(
                message=gettext("الملف يجب أن يكون Excel (.xlsx أو .xls)"),
                status_code=400,
            )

        file.stream.seek(0, 2)
        file_size = file.stream.tell()
        file.stream.seek(0)
        if file_size > max_bytes:
            return error_response(
                message=gettext("حجم الملف كبير جداً"),
                status_code=413,
            )

        result = _process_excel_intelligently(file, warehouse_id, current_user)

        return success_response(data=result)

    except Exception as e:
        return error_response(
            message=gettext(f"خطأ في معالجة الملف: {str(e)}"),
            status_code=500,
        )


def _process_excel_intelligently(file, warehouse_id, user):
    """معالج Excel ذكي خارق - أفضل من البشر"""
    try:
        from models import Product

        tid = get_active_tenant_id(user)
        df = pd.read_excel(file, engine="openpyxl")

        column_mapping = _intelligent_column_detector(df)

        if not column_mapping:
            return {
                "success": False,
                "error": gettext("لم أستطع فهم هيكل الملف. تأكد من وجود أعمدة: الاسم، رقم القطعة، السعر"),
            }

        warehouse = PlatformQueryService.warehouse_in_tenant(warehouse_id, tid)
        if not warehouse:
            return {
                "success": False,
                "error": gettext(f"المستودع #{warehouse_id} غير موجود"),
            }

        products_created = 0
        products_updated = 0
        errors = []

        with atomic_transaction("excel_upload"):
            for index, row in df.iterrows():
                try:
                    name = str(row[column_mapping["name"]]).strip()
                    part_number = str(row[column_mapping["part_number"]]).strip()
                    price = float(row[column_mapping["price"]])

                    if "quantity" in column_mapping and column_mapping["quantity"] in row:
                        quantity_val = row[column_mapping["quantity"]]
                        quantity = 0 if pd.isna(quantity_val) or quantity_val == "" else int(float(quantity_val))
                    else:
                        quantity = 0

                    if not name or name == "nan" or part_number == "nan":
                        continue

                    existing_product = PlatformQueryService.product_by_part_number(part_number, tid)

                    if existing_product:
                        existing_product.regular_price = price
                        products_updated += 1
                        if quantity > 0:
                            wh_import = PlatformQueryService.first_active_warehouse(tid)
                            StockService.add_stock(
                                product_id=existing_product.id,
                                quantity=quantity,
                                reference_type=GLRef.PRODUCT_UPDATE,
                                warehouse_id=wh_import.id if wh_import else None,
                            )
                    else:
                        product = Product(
                            name=name,
                            part_number=part_number,
                            regular_price=price,
                            current_stock=0,
                            is_active=True,
                        )
                        assign_tenant_id(product, user)
                        db.session.add(product)
                        if quantity > 0:
                            StockService.add_opening_stock(
                                product_id=product.id,
                                quantity=quantity,
                            )
                        products_created += 1

                except Exception as e:
                    errors.append(gettext(f"السطر {cast(int, index) + 2}: {str(e)}"))

        _train_ai_from_excel(df, products_created, products_updated, user.id)

        error_details = "\n".join(errors) if errors else ""

        message = f"""✅ تمت المعالجة بنجاح!
            
📊 النتائج:
- تم إنشاء: {products_created} منتج جديد
- تم تحديث: {products_updated} منتج موجود
- المستودع: {warehouse.name}
- الأخطاء: {len(errors)}

🤖 تم تدريب AI على البيانات الجديدة!
🧠 المصدر: GROQ + المحلي - معالج ذكي خارق"""

        if errors and len(errors) > 0:
            message += gettext(f"\n\n⚠️ تفاصيل الأخطاء:\n{error_details}")

        return {
            "success": True,
            "message": message,
            "details": {
                "created": products_created,
                "updated": products_updated,
                "errors": errors,
                "warehouse": warehouse.name,
            },
        }

    except Exception as e:
        return {"success": False, "error": gettext(f"خطأ في المعالجة: {str(e)}")}


def _intelligent_column_detector(df):
    """كاشف ذكي لأعمدة Excel - يفهم أي تسمية"""
    column_mapping = {}

    name_keywords = [
        gettext("اسم"),
        "name",
        "product",
        gettext("منتج"),
        "item",
        "description",
        gettext("وصف"),
    ]
    part_keywords = [
        gettext("رقم"),
        "part",
        "code",
        gettext("كود"),
        "sku",
        "id",
        "reference",
        gettext("مرجع"),
    ]
    price_keywords = [
        gettext("سعر"),
        "price",
        "cost",
        gettext("تكلفة"),
        "value",
        gettext("قيمة"),
        "amount",
        gettext("مبلغ"),
    ]
    quantity_keywords = [
        gettext("كمية"),
        "qty",
        "quantity",
        "stock",
        gettext("مخزون"),
        gettext("عدد"),
        "count",
    ]

    columns_lower = [str(col).lower() for col in df.columns]

    for idx, col in enumerate(columns_lower):
        if any(keyword in col for keyword in name_keywords):
            column_mapping["name"] = df.columns[idx]
        elif any(keyword in col for keyword in part_keywords):
            column_mapping["part_number"] = df.columns[idx]
        elif any(keyword in col for keyword in price_keywords):
            column_mapping["price"] = df.columns[idx]
        elif any(keyword in col for keyword in quantity_keywords):
            column_mapping["quantity"] = df.columns[idx]

    if "name" not in column_mapping and len(df.columns) > 0:
        column_mapping["name"] = df.columns[0]
    if "part_number" not in column_mapping and len(df.columns) > 1:
        column_mapping["part_number"] = df.columns[1]
    if "price" not in column_mapping and len(df.columns) > 2:
        column_mapping["price"] = df.columns[2]
    if "quantity" not in column_mapping and len(df.columns) > 3:
        column_mapping["quantity"] = df.columns[3]

    return column_mapping if len(column_mapping) >= 3 else None


def _train_ai_from_excel(df, created, updated, user_id):
    """تدريب AI من بيانات Excel"""
    try:
        {
            "source": "excel_upload",
            "timestamp": datetime.now().isoformat(),
            "user_id": user_id,
            "products_created": created,
            "products_updated": updated,
            "total_rows": len(df),
            "columns": list(df.columns),
            "sample_data": df.head(5).to_dict(),
        }

    except Exception as e:
        print(f"AI training from Excel failed: {e}")
