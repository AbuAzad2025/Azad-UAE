"""
Public Routes - Landing Page, Pricing, User Guide, SEO
"""
from flask import Blueprint, render_template, redirect, url_for, Response, request, session, abort
from flask_login import current_user
from datetime import datetime, timezone

public_bp = Blueprint('public', __name__)


def _safe_vault_for_public(vault):
    if not vault:
        return None
    safe_fields = [
        'donation_title_ar', 'donation_title_en', 'donation_intro_ar', 'donation_intro_en',
        'min_donation_amount', 'max_donation_amount', 'bitcoin_address', 'bank_iban',
        'bank_account_number', 'paypal_business_email', 'bank_name', 'donations_enabled',
        'donation_page_enabled',
    ]
    safe = {}
    for f in safe_fields:
        safe[f] = getattr(vault, f, None)
    return safe


@public_bp.route('/')
def landing():
    """Landing Page الفخمة"""
    return render_template('public/landing.html')


@public_bp.route('/pricing')
def pricing():
    """صفحة الأسعار والعروض"""
    lang = session.get('language', 'ar')
    if lang == 'en':
        return render_template('public/pricing_en.html')
    return render_template('public/pricing.html')


@public_bp.route('/features')
def features():
    """صفحة المميزات"""
    lang = session.get('language', 'ar')
    if lang == 'en':
        return render_template('public/features_en.html')
    return render_template('public/features.html')


@public_bp.route('/user-guide')
def user_guide():
    """دليل المستخدم"""
    # اختيار القالب حسب اللغة
    lang = session.get('language', 'ar')
    
    if lang == 'en':
        return render_template('public/user_guide_en.html')
    else:
        return render_template('public/user_guide.html')


@public_bp.route('/contact')
def contact():
    """اتصل بنا"""
    lang = session.get('language', 'ar')
    if lang == 'en':
        return render_template('public/contact_en.html')
    return render_template('public/contact.html')


@public_bp.route('/donate')
@public_bp.route('/support-azad')
def donate_azad():
    """صفحة تبرع لشركة أزاد — تُتحكم من الخزينة السرية"""
    from models.payment_vault import PaymentVault
    vault = PaymentVault.get_platform_vault()
    lang = session.get('language', 'ar')
    if not vault or not vault.donations_enabled or not vault.donation_page_enabled:
        from flask import abort
        abort(404)
    return render_template(
        'public/donate_azad.html',
        vault=_safe_vault_for_public(vault),
        lang=lang,
        is_en=lang == 'en',
    )


@public_bp.route('/donate/submit', methods=['POST'])
def donate_azad_submit():
    from decimal import Decimal
    from flask import flash
    from extensions import db
    from models.donation import Donation
    from models.payment_vault import PaymentVault

    vault = PaymentVault.get_platform_vault()
    lang = session.get('language', 'ar')
    is_en = lang == 'en'
    if not vault or not vault.donations_enabled or not vault.donation_page_enabled:
        abort(404)

    try:
        amount = Decimal(str(request.form.get('amount', 0)))
        if amount < Decimal(str(vault.min_donation_amount or 10)):
            raise ValueError('المبلغ أقل من الحد الأدنى.' if not is_en else 'Amount below minimum.')
        if amount > Decimal(str(vault.max_donation_amount or 10000)):
            raise ValueError('المبلغ يتجاوز الحد الأقصى.' if not is_en else 'Amount exceeds maximum.')

        method = (request.form.get('payment_method') or 'bank_transfer').strip()
        donation = Donation(
            amount_usd=amount,
            payment_method=method,
            transaction_type='donation',
            status='pending',
            donor_name=(request.form.get('donor_name') or '').strip(),
            donor_email=(request.form.get('donor_email') or '').strip(),
            donor_message=(request.form.get('donor_message') or '').strip(),
            ip_address=request.remote_addr,
            user_agent=(request.headers.get('User-Agent') or '')[:500],
        )
        db.session.add(donation)
        db.session.commit()
        return render_template('public/donate_thanks.html', vault=_safe_vault_for_public(vault), donation=donation, lang=lang, is_en=is_en)
    except ValueError as exc:
        flash(str(exc), 'danger')
        return redirect(url_for('public.donate_azad'))
    except Exception:
        import logging
        logging.getLogger(__name__).exception('Donation submit failed')
        db.session.rollback()
        flash('تعذر إرسال التبرع.' if not is_en else 'Could not submit donation.', 'danger')
        return redirect(url_for('public.donate_azad'))


@public_bp.route('/sitemap.xml')
def sitemap():
    """
    خريطة الموقع الديناميكية لمحركات البحث
    Dynamic Sitemap for Search Engines (Google, Bing, etc.)
    """
    from flask import Response
    
    # الحصول على URL الأساسي
    base_url = request.url_root.rstrip('/')
    
    # الصفحات الثابتة العامة (أولوية عالية)
    static_pages = [
        # الصفحات الرئيسية - أعلى أولوية
        {'loc': f'{base_url}/', 'priority': '1.0', 'changefreq': 'daily',
         'lastmod': datetime.now(timezone.utc).strftime('%Y-%m-%d'),
         'keywords': 'نظام إدارة مستودعات، برنامج محاسبة الإمارات'},
        
        # صفحات تسويقية مهمة
        {'loc': f'{base_url}/pricing', 'priority': '0.95', 'changefreq': 'weekly',
         'keywords': 'أسعار برنامج المستودعات، باقات محاسبة'},
        {'loc': f'{base_url}/features', 'priority': '0.95', 'changefreq': 'weekly',
         'keywords': 'مميزات نظام المستودعات، خصائص البرنامج'},
        {'loc': f'{base_url}/contact', 'priority': '0.90', 'changefreq': 'monthly',
         'keywords': 'اتصل بنا، دبي، الإمارات'},
        {'loc': f'{base_url}/user-guide', 'priority': '0.85', 'changefreq': 'monthly',
         'keywords': 'دليل المستخدم، شرح البرنامج'},
        
        # صفحات عامة أخرى
        {'loc': f'{base_url}/auth/login', 'priority': '0.80', 'changefreq': 'monthly',
         'keywords': 'تسجيل دخول'},
    ]
    
    # المنتجات النشطة — لا تُدرج في sitemap العام (تسريب بيانات multi-tenant)
    # استخدم sitemap المتجر: /s/{slug}/sitemap.xml
    
    # بناء XML
    xml_content = '<?xml version="1.0" encoding="UTF-8"?>\n'
    xml_content += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    
    for page in static_pages:
        xml_content += '  <url>\n'
        xml_content += f'    <loc>{page["loc"]}</loc>\n'
        xml_content += f'    <priority>{page["priority"]}</priority>\n'
        xml_content += f'    <changefreq>{page["changefreq"]}</changefreq>\n'
        if page.get('lastmod'):
            xml_content += f'    <lastmod>{page["lastmod"]}</lastmod>\n'
        xml_content += '  </url>\n'
    
    xml_content += '</urlset>'
    
    return Response(xml_content, mimetype='application/xml')


@public_bp.route('/robots.txt')
def robots():
    """
    ملف Robots.txt لتوجيه محركات البحث
    Robots.txt for Search Engine Crawlers
    """
    base_url = request.url_root.rstrip('/')
    
    robots_content = f"""# شركة أزاد للأنظمة الذكية
# Azad Smart Systems - Robots.txt

User-agent: *
Allow: /
Allow: /pricing
Allow: /features
Allow: /user-guide
Allow: /contact
Allow: /static/

# منع الصفحات الإدارية والحساسة
Disallow: /owner/
Disallow: /dashboard
Disallow: /auth/
Disallow: /api/
Disallow: /admin/

# منع المجلدات الداخلية
Disallow: /instance/
Disallow: /logs/
Disallow: /migrations/

# خريطة الموقع
Sitemap: {base_url}/sitemap.xml

# معدل الزحف (Crawl-delay)
Crawl-delay: 1
"""
    return Response(robots_content, mimetype='text/plain')


@public_bp.route('/suspended/<int:tenant_id>')
def tenant_suspend_page(tenant_id):
    """Public page shown when a tenant is suspended."""
    from models import Tenant
    tenant = Tenant.query.get_or_404(tenant_id)
    return render_template(
        'public/tenant_suspended.html',
        tenant=tenant,
        reason=tenant.suspension_reason or 'Tenant suspended',
    )

