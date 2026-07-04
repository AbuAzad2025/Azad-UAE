"""Settings, configuration, and communication routes for the owner blueprint."""

from decimal import Decimal
from routes.owner import (
    render_template, request, jsonify, flash, redirect, url_for, current_app, abort,
    login_required, current_user, func, text, db, limiter,
    Tenant, SystemSettings, IntegrationSettings, InvoiceSettings,
    StorePaymentMethod, CardVault, User, Role, Warehouse, TenantStore,
    owner_required, owner_or_company_admin, company_admin_required,
    is_global_owner_user, get_active_tenant_id, get_system_default_currency,
    get_tenant_ai_level, set_tenant_ai_level,
)
from services.logging_core import LoggingCore
from services.store_service import StoreService
from routes.owner import owner_bp
from routes.owner.shared import _invalidate_owner_changes, _audit_owner_db_action, _mask_api_key, _get_developer_from_settings

import logging
import os
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

@owner_bp.route('/integrations')
@owner_required
def integrations():
    """عرض إعدادات التكاملات من قاعدة البيانات"""
    from services.integration_service import IntegrationService
    integrations_data = IntegrationService.get_integrations_context()
    return render_template('owner/integrations.html', integrations=integrations_data)

@owner_bp.route('/integrations/update/<service>', methods=['POST'])
@owner_required
def update_integration(service):
    """تحديث إعدادات التكامل - حفظ حقيقي في قاعدة البيانات"""
    try:
        # الحصول على أو إنشاء سجل الخدمة
        integration = IntegrationSettings.get_service_config(service)

        # تحديث enabled
        integration.enabled = request.form.get('enabled') == 'true' or request.form.get('enabled') == '1'

        # بناء config_data حسب نوع الخدمة
        config_data = {}

        if service == 'whatsapp':
            config_data = {
                'api_token': request.form.get('api_token', ''),
                'phone_number': request.form.get('phone_number', ''),
                'api_url': request.form.get('api_url', ''),
                'message_template': request.form.get('message_template', '')
            }

        elif service == 'email':
            config_data = {
                'smtp_host': request.form.get('smtp_host', ''),
                'smtp_port': request.form.get('smtp_port', '587'),
                'smtp_user': request.form.get('smtp_user', ''),
                'smtp_password': request.form.get('smtp_password', ''),
                'smtp_use_tls': request.form.get('smtp_use_tls') == 'true' or request.form.get('smtp_use_tls') == '1',
                'from_email': request.form.get('from_email', ''),
                'from_name': request.form.get('from_name', '')
            }

        elif service == 'redis':
            config_data = {
                'redis_host': request.form.get('redis_host', 'localhost'),
                'redis_port': request.form.get('redis_port', '6379'),
                'redis_password': request.form.get('redis_password', ''),
                'redis_db': request.form.get('redis_db', '0')
            }

        elif service == 'currency_api':
            config_data = {
                'api_key': request.form.get('api_key', ''),
                'api_url': request.form.get('api_url', ''),
                'update_frequency': request.form.get('update_frequency', 'daily')
            }

        # حفظ الإعدادات
        integration.set_config(config_data)
        integration.updated_by = current_user.id
        integration.updated_at = datetime.now(timezone.utc)

        db.session.commit()
        _invalidate_owner_changes()
        flash(f'✅ تم حفظ إعدادات {service} بنجاح!', 'success')

    except Exception as e:
        db.session.rollback()
        flash(f'❌ خطأ في حفظ الإعدادات: {str(e)}', 'danger')
        current_app.logger.error(f"Error saving integration {service}: {e}")

    return redirect(url_for('owner.integrations'))

def _owner_backup_filename(filename: str):
    from services.backup_service import BackupService
    return BackupService.sanitize_filename(filename)

def _backup_created_by_payload():
    role = None
    if getattr(current_user, 'role', None):
        role = getattr(current_user.role, 'slug', None)
    return {
        'user_id': getattr(current_user, 'id', None),
        'role': role,
        'username': getattr(current_user, 'username', None),
    }

@owner_bp.route('/reports')
@owner_required
def reports():
    """صفحة التقارير"""
    # إحصائيات عامة
    from models import User, Customer, Product, Sale, Receipt, PaymentVault, Donation, Payment

    tid = get_active_tenant_id(current_user)
    vault = PaymentVault.get_platform_vault()
    scoped_branch_id = _owner_branch_scope()

    # Base customer query scoped by tenant
    customers_stats_query = Customer.query.filter_by(tenant_id=tid, is_active=True)
    if scoped_branch_id is not None:
        customers_stats_query = customers_stats_query.join(Sale, Customer.id == Sale.customer_id).filter(Sale.branch_id == scoped_branch_id).distinct()

    # Base queries scoped by tenant
    base_sale_q = Sale.query.filter_by(tenant_id=tid)
    base_receipt_q = Receipt.query.filter_by(tenant_id=tid)
    base_payment_q = Payment.query.filter_by(tenant_id=tid)
    base_product_q = Product.query.filter_by(tenant_id=tid, is_active=True)
    base_donation_q = Donation.query.filter_by(tenant_id=tid, transaction_type='donation')

    if scoped_branch_id is not None:
        stats = {
            'total_users': User.query.filter_by(tenant_id=tid, is_active=True, is_owner=False).count(),
            'total_customers': customers_stats_query.count(),
            'total_products': get_visible_products_query(current_user).count(),
            'total_sales': base_sale_q.filter(Sale.branch_id == scoped_branch_id).count(),
            'total_invoices': base_sale_q.filter(Sale.payment_status == 'paid', Sale.branch_id == scoped_branch_id).count(),
            'total_receipts': base_receipt_q.filter(Receipt.branch_id == scoped_branch_id).count(),
            'total_donations': base_donation_q.count(),
            'total_payments': base_payment_q.filter(Payment.branch_id == scoped_branch_id).count(),
            'vault_status': vault.is_locked if vault else True
        }
    else:
        stats = {
            'total_users': User.query.filter_by(tenant_id=tid, is_active=True, is_owner=False).count(),
            'total_customers': customers_stats_query.count(),
            'total_products': base_product_q.count(),
            'total_sales': base_sale_q.count(),
            'total_invoices': base_sale_q.filter_by(payment_status='paid').count(),
            'total_receipts': base_receipt_q.count(),
            'total_donations': base_donation_q.count(),
            'total_payments': base_payment_q.count(),
            'vault_status': vault.is_locked if vault else True
        }

    return render_template('owner/reports.html', stats=stats)

@owner_bp.route('/company-info', methods=['GET', 'POST'])
@login_required
@owner_or_company_admin
def company_info():
    """معلومات الشركة/الكراج"""
    tenant = Tenant.get_current()

    if request.method == 'POST':
        try:
            tenant.name_ar = request.form.get('name_ar', '').strip()
            tenant.name_en = request.form.get('name_en', '').strip()
            tenant.name = tenant.name_en or tenant.name_ar
            tenant.slug = request.form.get('slug', '').strip()
            from services.industry_service import IndustryService
            business_type = request.form.get('business_type', 'general').strip()
            tenant.business_type = business_type if IndustryService.validate_industry_code(business_type) else 'general'
            tenant.industry = tenant.business_type

            # Contact Info
            tenant.address_ar = request.form.get('address_ar', '').strip()
            tenant.address_en = request.form.get('address_en', '').strip()
            tenant.city = request.form.get('city', '').strip()
            tenant.country = request.form.get('country', 'PS')
            tenant.phone_1 = request.form.get('phone_1', '').strip()
            tenant.phone_2 = request.form.get('phone_2', '').strip()
            tenant.mobile = request.form.get('mobile', '').strip()
            tenant.email = request.form.get('email', '').strip()
            tenant.website = request.form.get('website', '').strip()

            # Legal Info
            tenant.tax_number = request.form.get('tax_number', '').strip()
            tenant.commercial_register = request.form.get('commercial_register', '').strip()
            tenant.license_number = request.form.get('license_number', '').strip()

            # Branding
            tenant.brand_color_primary = request.form.get('brand_color_primary', '#007A3D')
            tenant.brand_color_secondary = request.form.get('brand_color_secondary', '#D4AF37')

            tenant.updated_by = current_user.id

            # مزامنة اسم الشركة مع إعدادات الفواتير حتى يظهر في الترويسات وصفحة الدخول من مصدر واحد
            try:
                inv = InvoiceSettings.get_active()
                if inv:
                    inv.company_name_ar = tenant.name_ar or inv.company_name_ar
                    inv.company_name_en = tenant.name_en or tenant.name or inv.company_name_en
                    inv.address_ar = tenant.address_ar or inv.address_ar
                    inv.address_en = tenant.address_en or inv.address_en
                    inv.phone_1 = tenant.phone_1 or inv.phone_1
                    inv.phone_2 = tenant.phone_2 or inv.phone_2
                    inv.email = tenant.email or inv.email
                    inv.website = tenant.website or inv.website
                    inv.tax_number = tenant.tax_number or inv.tax_number
            except Exception as exc:
                logger.debug("sync invoice from tenant: %s", exc)

            db.session.commit()
            _invalidate_owner_changes()
            flash('تم حفظ معلومات الشركة بنجاح', 'success')
            return redirect(url_for('owner.company_info'))

        except Exception as e:
            db.session.rollback()
            flash(f'خطأ في حفظ المعلومات: {str(e)}', 'error')

    return render_template('owner/company_info.html', tenant=tenant)

def _get_developer_from_settings():
    """قيم الشركة المطورة من النظام (custom_settings) أو من config."""
    cfg = current_app.config
    settings = SystemSettings.get_current()
    return {
        'developer_name_ar': settings.get_custom_setting('developer_name_ar') or cfg.get('DEVELOPER_NAME_AR', ''),
        'developer_name': settings.get_custom_setting('developer_name') or cfg.get('DEVELOPER_NAME', ''),
        'developer_credit': settings.get_custom_setting('developer_credit') or cfg.get('DEVELOPER_CREDIT', ''),
        'developer_phone': settings.get_custom_setting('developer_phone') or cfg.get('DEVELOPER_PHONE', ''),
        'developer_email': settings.get_custom_setting('developer_email') or cfg.get('DEVELOPER_EMAIL', ''),
        'developer_website': settings.get_custom_setting('developer_website') or cfg.get('DEVELOPER_WEBSITE', ''),
        'developer_whatsapp': settings.get_custom_setting('developer_whatsapp') or cfg.get('DEVELOPER_WHATSAPP', ''),
        'developer_logo': settings.get_custom_setting('developer_logo') or cfg.get('DEVELOPER_LOGO', ''),
    }

@owner_bp.route('/developer-settings', methods=['GET', 'POST'])
@owner_required
def developer_settings():
    """إعدادات الشركة المطورة (للتواصل والدعم) — منفصلة عن التينانت."""
    settings = SystemSettings.get_current()
    dev = _get_developer_from_settings()

    if request.method == 'POST':
        try:
            settings.set_custom_setting('developer_name_ar', request.form.get('developer_name_ar', '').strip())
            settings.set_custom_setting('developer_name', request.form.get('developer_name', '').strip())
            settings.set_custom_setting('developer_credit', request.form.get('developer_credit', '').strip())
            settings.set_custom_setting('developer_phone', request.form.get('developer_phone', '').strip())
            settings.set_custom_setting('developer_email', request.form.get('developer_email', '').strip())
            settings.set_custom_setting('developer_website', request.form.get('developer_website', '').strip())
            settings.set_custom_setting('developer_whatsapp', request.form.get('developer_whatsapp', '').strip())
            settings.set_custom_setting('developer_logo', request.form.get('developer_logo', '').strip())
            settings.updated_by = current_user.id
            db.session.commit()
            _invalidate_owner_changes()
            flash('تم حفظ إعدادات الشركة المطورة بنجاح', 'success')
            return redirect(url_for('owner.developer_settings'))
        except Exception as e:
            db.session.rollback()
            flash(f'خطأ في الحفظ: {str(e)}', 'error')
    return render_template('owner/developer_settings.html', dev=dev, config=current_app.config)

@owner_bp.route('/system-config', methods=['GET', 'POST'])
@owner_required
def system_config():
    """إعدادات النظام الشاملة"""
    settings = SystemSettings.get_current()

    if request.method == 'POST':
        try:
            settings.enable_sales = request.form.get('enable_sales') == 'on'
            settings.enable_purchases = request.form.get('enable_purchases') == 'on'
            settings.enable_inventory = request.form.get('enable_inventory') == 'on'
            settings.enable_customers = request.form.get('enable_customers') == 'on'
            settings.enable_expenses = request.form.get('enable_expenses') == 'on'
            settings.enable_gl = request.form.get('enable_gl') == 'on'
            settings.enable_reports = request.form.get('enable_reports') == 'on'
            settings.enable_ai_assistant = request.form.get('enable_ai_assistant') == 'on'
            settings.enable_pos = request.form.get('enable_pos') == 'on'

            settings.enable_barcode_scanner = request.form.get('enable_barcode_scanner') == 'on'
            settings.enable_multi_warehouse = request.form.get('enable_multi_warehouse') == 'on'
            settings.enable_multi_currency = request.form.get('enable_multi_currency') == 'on'
            settings.enable_discounts = request.form.get('enable_discounts') == 'on'
            settings.enable_returns = request.form.get('enable_returns') == 'on'
            settings.enable_ecommerce = request.form.get('enable_ecommerce') == 'on'

            # Azad Platform Fees
            try:
                fee_rate = Decimal(request.form.get('azad_platform_fee_rate', '1.00'))
                settings.azad_platform_fee_rate = fee_rate.quantize(Decimal('0.01'))
            except Exception:
                pass
            try:
                settings.subscription_monthly_fee_aed = Decimal(request.form.get('subscription_monthly_fee_aed', '0') or '0').quantize(Decimal('0.001'))
            except Exception:
                pass
            try:
                settings.subscription_yearly_fee_aed = Decimal(request.form.get('subscription_yearly_fee_aed', '0') or '0').quantize(Decimal('0.001'))
            except Exception:
                pass
            try:
                settings.subscription_perpetual_fee_aed = Decimal(request.form.get('subscription_perpetual_fee_aed', '0') or '0').quantize(Decimal('0.001'))
            except Exception:
                pass

            try:
                default_currency = request.form.get('default_currency', 'ILS')
                settings.default_currency = default_currency
            except Exception:
                pass
            try:
                from models import Tenant
                tenant = Tenant.get_current()
                tenant.default_currency = default_currency
            except Exception as exc:
                logger.debug("tenant default_currency sync: %s", exc)
            settings.default_language = request.form.get('default_language', 'ar')
            settings.timezone = request.form.get('timezone', 'Asia/Dubai')
            settings.items_per_page = int(request.form.get('items_per_page', 25))

            settings.updated_by = current_user.id

            db.session.commit()
            _invalidate_owner_changes()
            flash('تم حفظ إعدادات النظام بنجاح', 'success')
            return redirect(url_for('owner.system_config'))

        except Exception as e:
            db.session.rollback()
            flash(f'خطأ في حفظ الإعدادات: {str(e)}', 'error')

    return render_template('owner/system_config.html', settings=settings)

@owner_bp.route('/store-payment-methods')
@owner_required
def store_payment_methods():
    """إدارة طرق دفع المتاجر — تنعكس على كل تينانت"""
    from services.store_payment_method_service import StorePaymentMethodService
    StorePaymentMethodService.ensure_defaults()
    methods = StorePaymentMethodService.list_all()
    return render_template('owner/store_payment_methods.html', methods=methods)

@owner_bp.route('/store-payment-methods/create', methods=['GET', 'POST'])
@owner_required
def store_payment_method_create():
    from services.store_payment_method_service import StorePaymentMethodService
    if request.method == 'POST':
        try:
            StorePaymentMethodService.create_method({
                'code': request.form.get('code'),
                'name_ar': request.form.get('name_ar'),
                'name_en': request.form.get('name_en'),
                'description_ar': request.form.get('description_ar'),
                'description_en': request.form.get('description_en'),
                'icon': request.form.get('icon'),
                'is_enabled': request.form.get('is_enabled') == 'on',
                'sort_order': request.form.get('sort_order', 100),
                'bank_name': request.form.get('bank_name'),
                'iban': request.form.get('iban'),
                'account_name': request.form.get('account_name'),
                'providers': request.form.get('providers'),
                'instructions': request.form.get('instructions'),
            })
            _invalidate_owner_changes()
            flash('تمت إضافة طريقة الدفع.', 'success')
            return redirect(url_for('owner.store_payment_methods'))
        except ValueError as exc:
            flash(str(exc), 'warning')
        except Exception as exc:
            db.session.rollback()
            flash(f'خطأ: {exc}', 'danger')
    return render_template('owner/store_payment_method_form.html', method=None)

@owner_bp.route('/store-payment-methods/<int:method_id>/edit', methods=['GET', 'POST'])
@owner_required
def store_payment_method_edit(method_id):
    from models.store_payment_method import StorePaymentMethod
    from services.store_payment_method_service import StorePaymentMethodService
    method = db.session.get(StorePaymentMethod, int(method_id))
    if not method:
        flash('طريقة الدفع غير موجودة.', 'warning')
        return redirect(url_for('owner.store_payment_methods'))
    if request.method == 'POST':
        try:
            StorePaymentMethodService.update_method(method.id, {
                'code': request.form.get('code'),
                'name_ar': request.form.get('name_ar'),
                'name_en': request.form.get('name_en'),
                'description_ar': request.form.get('description_ar'),
                'description_en': request.form.get('description_en'),
                'icon': request.form.get('icon'),
                'is_enabled': request.form.get('is_enabled') == 'on',
                'sort_order': request.form.get('sort_order', method.sort_order),
                'bank_name': request.form.get('bank_name'),
                'iban': request.form.get('iban'),
                'account_name': request.form.get('account_name'),
                'providers': request.form.get('providers'),
                'instructions': request.form.get('instructions'),
            })
            _invalidate_owner_changes()
            flash('تم تحديث طريقة الدفع.', 'success')
            return redirect(url_for('owner.store_payment_methods'))
        except ValueError as exc:
            flash(str(exc), 'warning')
        except Exception as exc:
            db.session.rollback()
            flash(f'خطأ: {exc}', 'danger')
    return render_template('owner/store_payment_method_form.html', method=method)

@owner_bp.route('/store-payment-methods/<int:method_id>/toggle', methods=['POST'])
@owner_required
def store_payment_method_toggle(method_id):
    from services.store_payment_method_service import StorePaymentMethodService
    try:
        enabled = request.form.get('is_enabled') == '1'
        StorePaymentMethodService.toggle_enabled(method_id, enabled)
        _invalidate_owner_changes()
        flash('تم تحديث حالة طريقة الدفع.', 'success')
    except ValueError as exc:
        flash(str(exc), 'warning')
    return redirect(url_for('owner.store_payment_methods'))

@owner_bp.route('/store-payment-methods/<int:method_id>/delete', methods=['POST'])
@owner_required
def store_payment_method_delete(method_id):
    from services.store_payment_method_service import StorePaymentMethodService
    try:
        StorePaymentMethodService.delete_method(method_id)
        _invalidate_owner_changes()
        flash('تم حذف طريقة الدفع.', 'success')
    except ValueError as exc:
        flash(str(exc), 'warning')
    except Exception as exc:
        db.session.rollback()
        flash(f'خطأ: {exc}', 'danger')
    return redirect(url_for('owner.store_payment_methods'))

@owner_bp.route('/invoice-settings', methods=['GET', 'POST'])
@login_required
@owner_or_company_admin
def invoice_settings():
    """إعدادات ترويسات الفواتير وسندات القبض"""
    settings = InvoiceSettings.get_active()

    if request.method == 'POST':
        try:
            # Company Info
            settings.company_name_ar = request.form.get('company_name_ar', '').strip()
            settings.company_name_en = request.form.get('company_name_en', '').strip()

            # Contact Info
            settings.address_ar = request.form.get('address_ar', '').strip()
            settings.address_en = request.form.get('address_en', '').strip()
            settings.phone_1 = request.form.get('phone_1', '').strip()
            settings.phone_2 = request.form.get('phone_2', '').strip()
            settings.email = request.form.get('email', '').strip()
            settings.website = request.form.get('website', '').strip()

            settings.tax_number = request.form.get('tax_number', '').strip()
            settings.commercial_register = request.form.get('commercial_register', '').strip()
            settings.license_number = request.form.get('license_number', '').strip()

            # Bank Info
            settings.bank_name = request.form.get('bank_name', '').strip()
            settings.bank_account_number = request.form.get('bank_account_number', '').strip()
            settings.iban = request.form.get('iban', '').strip()
            settings.swift_code = request.form.get('swift_code', '').strip()

            # Design
            settings.header_color = request.form.get('header_color', '#667eea').strip()
            settings.accent_color = request.form.get('accent_color', '#764ba2').strip()
            settings.text_color = request.form.get('text_color', '#333333').strip()

            # Layout
            settings.show_logo = request.form.get('show_logo') == 'on'
            settings.logo_position = request.form.get('logo_position', 'left')
            settings.logo_size = request.form.get('logo_size', 'medium')

            # Footer
            settings.footer_text_ar = request.form.get('footer_text_ar', '').strip()
            settings.footer_text_en = request.form.get('footer_text_en', '').strip()
            settings.show_terms = request.form.get('show_terms') == 'on'

            # Terms
            settings.terms_conditions_ar = request.form.get('terms_conditions_ar', '').strip()
            settings.terms_conditions_en = request.form.get('terms_conditions_en', '').strip()
            settings.payment_terms_ar = request.form.get('payment_terms_ar', '').strip()
            settings.payment_terms_en = request.form.get('payment_terms_en', '').strip()

            # Notes
            settings.default_invoice_note_ar = request.form.get('default_invoice_note_ar', '').strip()
            settings.default_invoice_note_en = request.form.get('default_invoice_note_en', '').strip()
            settings.default_receipt_note_ar = request.form.get('default_receipt_note_ar', '').strip()
            settings.default_receipt_note_en = request.form.get('default_receipt_note_en', '').strip()

            # QR & Watermark
            settings.enable_qr_code = request.form.get('enable_qr_code') == 'on'
            settings.qr_position = request.form.get('qr_position', 'bottom-right')
            settings.enable_watermark = request.form.get('enable_watermark') == 'on'
            settings.watermark_text = request.form.get('watermark_text', '').strip()

            settings.paper_size = request.form.get('paper_size', 'A4')
            settings.orientation = request.form.get('orientation', 'portrait')
            settings.default_language = request.form.get('default_language', 'ar')

            # Additional
            settings.show_barcode = request.form.get('show_barcode') == 'on'
            settings.show_page_numbers = request.form.get('show_page_numbers') == 'on'
            settings.show_due_date = request.form.get('show_due_date') == 'on'

            # Social Media
            settings.facebook_url = request.form.get('facebook_url', '').strip()
            settings.instagram_url = request.form.get('instagram_url', '').strip()
            settings.whatsapp_number = request.form.get('whatsapp_number', '').strip()

            # Template
            settings.active_template = request.form.get('active_template', 'modern')

            # Handle logo upload
            if 'company_logo' in request.files:
                logo_file = request.files['company_logo']
                if logo_file and logo_file.filename:
                    import os
                    from werkzeug.utils import secure_filename

                    filename = secure_filename(logo_file.filename)
                    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                    filename = f"logo_{timestamp}_{filename}"

                    upload_folder = os.path.join('static', 'uploads', 'logos')
                    os.makedirs(upload_folder, exist_ok=True)

                    filepath = os.path.join(upload_folder, filename)
                    logo_file.save(filepath)

                    settings.logo_path = f"uploads/logos/{filename}"

            # Handle watermark image upload
            if 'watermark_image' in request.files:
                watermark_file = request.files['watermark_image']
                if watermark_file and watermark_file.filename:
                    import os
                    from werkzeug.utils import secure_filename

                    filename = secure_filename(watermark_file.filename)
                    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                    filename = f"watermark_{timestamp}_{filename}"

                    upload_folder = os.path.join('static', 'uploads', 'watermarks')
                    os.makedirs(upload_folder, exist_ok=True)

                    filepath = os.path.join(upload_folder, filename)
                    watermark_file.save(filepath)

                    settings.watermark_image_path = f"uploads/watermarks/{filename}"

            settings.updated_by = current_user.id

            db.session.commit()
            _invalidate_owner_changes()
            flash('تم حفظ إعدادات الترويسات بنجاح', 'success')
            return redirect(url_for('owner.invoice_settings'))

        except Exception as e:
            db.session.rollback()
            flash(f'خطأ في حفظ الإعدادات: {str(e)}', 'error')

    return render_template('owner/invoice_settings.html', settings=settings)

@owner_bp.route('/preview-invoice/<template>')
@login_required
@owner_or_company_admin
def preview_invoice(template):
    """معاينة قالب الفاتورة"""
    from models.invoice_settings import InvoiceSettings
    from utils.tenant_branding import get_print_header_context
    from utils.tenanting import get_active_tenant_id
    from utils.auth_helpers import is_global_owner_user

    tid = request.args.get('tenant_id', type=int) or get_active_tenant_id(current_user)
    if request.args.get('tenant_id') and not is_global_owner_user(current_user):
        abort(403)
    settings = InvoiceSettings.get_active(tid)
    print_branding = get_print_header_context(tid)
    from utils.number_to_arabic import number_to_arabic_words
    from utils.qr_generator import generate_qr_data_url
    try:
        from models import Tenant
        default_currency = resolve_default_currency(Tenant.get_current())
    except Exception:
        default_currency = get_system_default_currency()

    # Sample data for preview
    class SampleCustomer:
        name = 'عميل تجريبي'
        phone = '0501234567'
        email = 'customer@example.com'
        address = 'دبي - الإمارات العربية المتحدة'

    class SampleSeller:
        full_name = 'البائع التجريبي'
        username = 'seller'
        def get_display_name(self, lang='ar'):
            return self.full_name

    class SampleBranch:
        name = 'الفرع الرئيسي'
        code = 'BR01'
        address = 'دبي - شارع الشيخ زايد'

    class SampleProduct:
        name = 'منتج تجريبي'

    class SampleLine:
        def __init__(self, name, qty, price, discount=0):
            self.product = type('obj', (object,), {'name': name})()
            self.quantity = qty
            self.unit_price = price
            self.discount_percent = discount
            self.line_total = qty * price * (1 - discount/100)

    class SamplePayment:
        def __init__(self):
            self.payment_number = 'PAY-2025-0001'
            self.payment_date = datetime.now()
            self.amount_aed = Decimal('500.00')
            self.payment_method = 'cheque'
            self.cheque_number = '123456'
            self.cheque_date = datetime.now().date()
            self.bank_name = 'بنك الإمارات دبي الوطني'
            self.reference_number = 'REF-001'

    class SampleSale:
        sale_number = 'S-2025-0001'
        sale_date = datetime.now()
        customer = SampleCustomer()
        seller = SampleSeller()
        lines = [
            SampleLine('زيت محرك سينثتك 5W-30', 5, 120, 10),
            SampleLine('فلتر هواء أصلي', 2, 85, 5),
            SampleLine('فلتر زيت', 3, 45, 0),
        ]
        subtotal = Decimal('925.00')
        discount_amount = Decimal('25.00')
        shipping_cost = Decimal('50.00')
        tax_rate = Decimal('5.00')
        tax_amount = Decimal('47.50')
        total_amount = Decimal('997.50')
        currency = default_currency
        notes = 'فاتورة تجريبية للمعاينة'
        payments = [SamplePayment()]

    sample_sale = SampleSale()
    sample_user_name = sample_sale.seller.get_display_name('ar')
    sample_amount_in_words = number_to_arabic_words(float(sample_sale.total_amount), sample_sale.currency)
    sample_qr_data_url = ''
    if settings and settings.enable_qr_code:
        sample_qr_data_url = generate_qr_data_url({
            't': 'invoice',
            'n': sample_sale.sale_number,
            'a': float(sample_sale.total_amount),
            'c': sample_sale.currency,
            'd': sample_sale.sale_date.strftime('%Y-%m-%d'),
            'co': settings.company_name_ar if settings and settings.company_name_ar else 'نظام المحاسبة',
            'u': sample_user_name,
            'b': SampleBranch.name,
        })

    return render_template(
        f'invoices/{template}.html',
        sale=sample_sale,
        settings=settings,
        preview=True,
        print_branch=SampleBranch(),
        print_user_name=sample_user_name,
        amount_in_words=sample_amount_in_words,
        qr_data_url=sample_qr_data_url,
        doc_number=sample_sale.sale_number,
        print_branding=print_branding,
        print_tenant_id=tid,
    )

@owner_bp.route('/preview-receipt/<template>')
@login_required
@owner_or_company_admin
def preview_receipt(template):
    """معاينة قالب سند القبض"""
    from models.invoice_settings import InvoiceSettings
    from utils.tenant_branding import get_print_header_context
    from utils.tenanting import get_active_tenant_id
    from utils.auth_helpers import is_global_owner_user

    tid = request.args.get('tenant_id', type=int) or get_active_tenant_id(current_user)
    if request.args.get('tenant_id') and not is_global_owner_user(current_user):
        abort(403)
    settings = InvoiceSettings.get_active(tid)
    print_branding = get_print_header_context(tid)
    try:
        from models import Tenant
        default_currency = resolve_default_currency(Tenant.get_current())
    except Exception:
        default_currency = get_system_default_currency()
    from utils.number_to_arabic import number_to_arabic_words
    from utils.qr_generator import generate_qr_data_url

    # Sample data for preview
    class SampleCustomer:
        name = 'عميل تجريبي'
        phone = '0501234567'
        email = 'customer@example.com'
        address = 'دبي - الإمارات'

    class SampleUser:
        full_name = 'المحصل التجريبي'
        username = 'collector'
        def get_display_name(self, lang='ar'):
            return self.full_name

    class SampleBranch:
        name = 'الفرع الرئيسي'
        code = 'BR01'
        address = 'دبي - شارع الشيخ زايد'

    class SampleSale:
        sale_number = 'S-2025-0001'
        sale_date = datetime.now()

    class SampleAllocation:
        def __init__(self, sale_num, amount):
            self.sale = type('obj', (object,), {
                'sale_number': sale_num,
                'sale_date': datetime.now()
            })()
            self.amount_allocated = Decimal(str(amount))

    class SampleReceipt:
        receipt_number = 'RCV-2025-0001'
        receipt_date = datetime.now()
        customer = SampleCustomer()
        user = SampleUser()
        amount = Decimal('1500.00')
        amount_aed = Decimal('1500.00')
        currency = default_currency
        payment_method = 'cheque'
        cheque_number = '789456'
        cheque_date = datetime.now().date()
        bank_name = 'بنك الإمارات دبي الوطني'
        reference_number = 'REF-2025-001'
        notes = 'تسديد ذمم فواتير سابقة - دفعة من مبيعات شهر أكتوبر 2025'
        allocations = [
            SampleAllocation('S-2025-0001', '800.00'),
            SampleAllocation('S-2025-0002', '700.00')
        ]

        def get_source_info(self):
            return {
                'type': 'فاتورة',
                'number': 'S-2025-0001',
                'date': datetime.now().strftime('%Y-%m-%d'),
                'id': 1
            }

    sample_receipt = SampleReceipt()
    sample_user_name = sample_receipt.user.get_display_name('ar')
    sample_amount_in_words = number_to_arabic_words(float(sample_receipt.amount), sample_receipt.currency)
    sample_qr_data_url = ''
    if settings and settings.enable_qr_code:
        sample_qr_data_url = generate_qr_data_url({
            't': 'receipt',
            'n': sample_receipt.receipt_number,
            'a': float(sample_receipt.amount),
            'c': sample_receipt.currency,
            'd': sample_receipt.receipt_date.strftime('%Y-%m-%d'),
            'co': settings.company_name_ar if settings and settings.company_name_ar else 'نظام المحاسبة',
            'u': sample_user_name,
            'b': SampleBranch.name,
        })

    return render_template(
        f'receipts/{template}.html',
        receipt=sample_receipt,
        settings=settings,
        preview=True,
        print_branch=SampleBranch(),
        print_user_name=sample_user_name,
        amount_in_words=sample_amount_in_words,
        qr_data_url=sample_qr_data_url,
        doc_number=sample_receipt.receipt_number,
        print_branding=print_branding,
        print_tenant_id=tid,
    )

@owner_bp.route('/tax-settings', methods=['GET', 'POST'])
@owner_required
def tax_settings():
    from decimal import Decimal
    from utils.tax_settings import VAT_COUNTRY_LABELS, suggested_rate_for_country

    tenant = Tenant.get_current()
    if not tenant:
        flash('لا توجد شركة نشطة.', 'danger')
        return redirect(url_for('owner.dashboard'))

    if request.method == 'POST':
        tenant.enable_tax = request.form.get('enable_tax') == 'on'
        tenant.vat_country = (request.form.get('vat_country') or 'PS').strip().upper()[:2]
        rate = request.form.get('default_tax_rate', type=float)
        if rate is None and tenant.enable_tax:
            rate = float(suggested_rate_for_country(tenant.vat_country))
        tenant.default_tax_rate = Decimal(str(rate or 0))
        tenant.vat_number = (request.form.get('vat_number') or '').strip() or None
        tenant.tax_number = (request.form.get('tax_number') or '').strip() or tenant.tax_number

        db.session.commit()
        _invalidate_owner_changes()
        flash('✅ تم تحديث إعدادات الضرائب للشركة الحالية', 'success')
        return redirect(url_for('owner.tax_settings'))

    return render_template(
        'owner/tax_settings.html',
        tenant=tenant,
        vat_countries=VAT_COUNTRY_LABELS,
    )

@owner_bp.route('/currency-settings', methods=['GET', 'POST'])
@owner_required
def currency_settings():
    from services.currency_service import CurrencyService

    if request.method == 'POST':
        settings = SystemSettings.get_current()

        default_currency = request.form.get('default_currency', 'AED')
        settings.default_currency = default_currency
        try:
            from models import Tenant
            tenant = Tenant.get_current()
            tenant.default_currency = default_currency
        except Exception as exc:
            logger.debug("tenant currency settings sync: %s", exc)
        settings.auto_update_rates = request.form.get('auto_update_rates') == 'on'

        db.session.commit()
        _invalidate_owner_changes()
        flash('✅ تم تحديث إعدادات العملات', 'success')
        return redirect(url_for('owner.currency_settings'))

    settings = SystemSettings.get_current()
    try:
        from models import Tenant
        default_currency = resolve_default_currency(Tenant.get_current())
    except Exception:
        default_currency = get_system_default_currency()
    rates = CurrencyService.get_all_rates(default_currency)

    return render_template('owner/currency_settings.html',
                         settings=settings,
                         rates=rates)


@owner_bp.route('/exchange-rates', methods=['GET', 'POST'])
@owner_required
def exchange_rates():
    """إدارة أسعار الصرف — Manual rate entry and history."""
    from services.exchange_rate_service import ExchangeRateService
    from models import ExchangeRateRecord
    from datetime import date

    today = date.today().isoformat()
    tenant_id = getattr(current_user, 'tenant_id', None)

    if request.method == 'POST':
        action = request.form.get('action', 'save')
        if action == 'save':
            from_currency = (request.form.get('from_currency') or 'USD').upper()
            to_currency = (request.form.get('to_currency') or 'AED').upper()
            rate_val = request.form.get('rate', type=float)
            effective = request.form.get('effective_date') or today

            if rate_val and rate_val > 0:
                result = ExchangeRateService.save_manual_rate(
                    from_currency=from_currency,
                    to_currency=to_currency,
                    rate=rate_val,
                    tenant_id=getattr(current_user, 'tenant_id', None),
                    created_by=current_user.id,
                )
                if result.get('ok'):
                    flash('✅ تم حفظ سعر الصرف بنجاح!', 'success')
                else:
                    flash(f"❌ خطأ: {result.get('error', 'unknown')}", 'danger')
            else:
                flash('⚠️ أدخل سعر صرف صالح أكبر من صفر.', 'warning')

        elif action == 'delete':
            record_id = request.form.get('record_id', type=int)
            if record_id:
                rec = ExchangeRateRecord.query.filter_by(
                    id=record_id, tenant_id=tenant_id
                ).first()
                if rec:
                    db.session.delete(rec)
                    db.session.commit()
                    flash('✅ تم حذف السجل.', 'success')
                else:
                    flash('⚠️ السجل غير موجود أو لا يخصك.', 'warning')

        return redirect(url_for('owner.exchange_rates'))

    # GET: show records
    records = (
        ExchangeRateRecord.query
        .filter_by(tenant_id=tenant_id)
        .order_by(ExchangeRateRecord.effective_date.desc(), ExchangeRateRecord.created_at.desc())
        .limit(100)
        .all()
    )

    return render_template('owner/exchange_rates.html',
                           records=records,
                           today=today,
                           currencies=ExchangeRateService.DISPLAY_CURRENCIES)

@owner_bp.route('/payment-gateways', methods=['GET', 'POST'])
@owner_required
def payment_gateways():
    from models import PaymentVault

    vault = PaymentVault.get_platform_vault()
    if not vault:
        vault = PaymentVault(tenant_id=None)
        vault.set_vault_password(current_app.config.get('SECRET_KEY', 'default-vault-password'))
        db.session.add(vault)
        db.session.commit()
        _invalidate_owner_changes()

    if request.method == 'POST':
        vault.stripe_publishable_key = request.form.get('stripe_publishable_key')
        vault.stripe_secret_key = request.form.get('stripe_secret_key')
        vault.paypal_client_id = request.form.get('paypal_client_id')
        vault.paypal_client_secret = request.form.get('paypal_client_secret')
        vault.nowpayments_api_key = request.form.get('nowpayments_api_key')

        db.session.commit()
        _invalidate_owner_changes()
        flash('✅ تم تحديث إعدادات بوابات الدفع', 'success')
        return redirect(url_for('owner.payment_gateways'))

    return render_template('owner/payment_gateways.html', vault=vault)

@owner_bp.route('/email-settings', methods=['GET', 'POST'])
@owner_required
def email_settings():
    if request.method == 'POST':
        settings = SystemSettings.get_current()

        settings.smtp_server = request.form.get('smtp_server')
        settings.smtp_port = request.form.get('smtp_port', type=int)
        settings.smtp_username = request.form.get('smtp_username')
        settings.smtp_password = request.form.get('smtp_password')
        settings.smtp_use_tls = request.form.get('smtp_use_tls') == 'on'
        settings.email_from = request.form.get('email_from')

        db.session.commit()
        _invalidate_owner_changes()
        flash('✅ تم تحديث إعدادات البريد الإلكتروني', 'success')
        return redirect(url_for('owner.email_settings'))

    settings = SystemSettings.get_current()

    return render_template('owner/email_settings.html', settings=settings)

@owner_bp.route('/sms-settings', methods=['GET', 'POST'])
@owner_required
def sms_settings():
    if request.method == 'POST':
        settings = SystemSettings.get_current()

        sms_provider = (request.form.get('sms_provider') or '').strip()
        settings.sms_provider = sms_provider or None
        settings.sms_api_key = request.form.get('sms_api_key')
        settings.sms_sender_name = request.form.get('sms_sender_name')
        settings.sms_enabled = request.form.get('sms_enabled') == 'on'

        db.session.commit()
        _invalidate_owner_changes()
        flash('✅ تم تحديث إعدادات الرسائل النصية', 'success')
        return redirect(url_for('owner.sms_settings'))

    settings = SystemSettings.get_current()

    return render_template('owner/sms_settings.html', settings=settings)

@owner_bp.route('/whatsapp-settings', methods=['GET', 'POST'])
@owner_required
def whatsapp_settings():
    if request.method == 'POST':
        settings = SystemSettings.get_current()

        settings.whatsapp_api_url = request.form.get('whatsapp_api_url')
        settings.whatsapp_api_key = request.form.get('whatsapp_api_key')
        settings.whatsapp_phone_number = request.form.get('whatsapp_phone_number')
        settings.whatsapp_enabled = request.form.get('whatsapp_enabled') == 'on'

        db.session.commit()
        _invalidate_owner_changes()
        flash('✅ تم تحديث إعدادات واتساب', 'success')
        return redirect(url_for('owner.whatsapp_settings'))

    settings = SystemSettings.get_current()

    return render_template('owner/whatsapp_settings.html', settings=settings)

@owner_bp.route('/notification-templates', methods=['GET', 'POST'])
@owner_required
def notification_templates():
    if request.method == 'POST':
        settings = SystemSettings.get_current()

        templates = {
            'invoice_email': request.form.get('invoice_email_template'),
            'payment_sms': request.form.get('payment_sms_template'),
            'reminder_whatsapp': request.form.get('reminder_whatsapp_template')
        }

        settings.notification_templates = templates
        db.session.commit()
        _invalidate_owner_changes()
        flash('✅ تم تحديث قوالب الإشعارات', 'success')
        return redirect(url_for('owner.notification_templates'))

    settings = SystemSettings.get_current()
    templates = settings.notification_templates or {}

    return render_template('owner/notification_templates.html',
                         templates=templates)

@owner_bp.route('/api/update-tenant-settings', methods=['POST'])
@login_required
@company_admin_required
def api_update_tenant_settings():
    """AJAX endpoint to update tenant-level settings from the company dashboard."""
    if not request.is_json:
        return jsonify({'success': False, 'error': 'JSON required'}), 400
    try:
        data = request.get_json()
        tenant = db.session.get(Tenant, get_active_tenant_id())
        if not tenant:
            return jsonify({'success': False, 'error': 'Tenant not found'}), 404
        field = data.get('field')
        value = data.get('value')
        if field == 'default_tax_rate':
            try:
                tenant.default_tax_rate = Decimal(str(value))
            except Exception:
                return jsonify({'success': False, 'error': 'Invalid tax rate value'}), 400
        elif field == 'prices_include_vat':
            tenant.prices_include_vat = bool(value)
        elif field == 'logo_url':
            tenant.logo_url = str(value).strip()
        else:
            return jsonify({'success': False, 'error': f'Unknown field: {field}'}), 400
        tenant.updated_at = datetime.now(timezone.utc)
        db.session.commit()
        _invalidate_owner_changes()
        _audit_owner_db_action('api_update_tenant_settings', {'field': field, 'tenant_id': tenant.id})
        return jsonify({'success': True, 'message': f'تم تحديث {field} بنجاح'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@owner_bp.route('/api/toggle-warehouse-negative', methods=['POST'])
@login_required
@company_admin_required
def api_toggle_warehouse_negative():
    """AJAX endpoint to toggle allow_negative_inventory for a warehouse."""
    if not request.is_json:
        return jsonify({'success': False, 'error': 'JSON required'}), 400
    try:
        data = request.get_json()
        warehouse_id = data.get('warehouse_id')
        if not warehouse_id:
            return jsonify({'success': False, 'error': 'warehouse_id required'}), 400
        tenant_id = get_active_tenant_id()
        warehouse = Warehouse.query.filter_by(id=warehouse_id, tenant_id=tenant_id).first()
        if not warehouse:
            return jsonify({'success': False, 'error': 'Warehouse not found'}), 404
        warehouse.allow_negative_inventory = not warehouse.allow_negative_inventory
        db.session.commit()
        _invalidate_owner_changes()
        return jsonify({
            'success': True,
            'allow_negative_inventory': warehouse.allow_negative_inventory,
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@owner_bp.route('/api/supervisor-override', methods=['POST'])
@login_required
def api_supervisor_override():
    """Verify supervisor credentials for cashier override actions."""
    if not request.is_json:
        return jsonify({'success': False, 'error': 'JSON required'}), 400
    try:
        data = request.get_json()
        action = data.get('action', '')
        supervisor_id = data.get('supervisor_id')
        password = data.get('password', '')
        if not supervisor_id or not password:
            return jsonify({'success': False, 'error': 'معرّف المشرف وكلمة المرور مطلوبان'}), 400
        supervisor = db.session.get(User, supervisor_id)
        if not supervisor or not supervisor.is_active:
            return jsonify({'success': False, 'error': 'المشرف غير موجود أو غير نشط'}), 404
        if not supervisor.is_manager() and not supervisor.is_admin():
            return jsonify({'success': False, 'error': 'المستخدم ليس مشرفاً'}), 403
        if not supervisor.check_password(password):
            return jsonify({'success': False, 'error': 'كلمة المرور غير صحيحة'}), 403
        LoggingCore.log_audit(
            'supervisor_override', 'system', None,
            {'supervisor_id': supervisor_id, 'action': action, 'cashier_id': current_user.id}
        )
        return jsonify({
            'success': True,
            'message': 'تم تفويض المشرف بنجاح',
            'supervisor_username': supervisor.username,
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

