"""
Public Routes - Landing Page, Pricing, User Guide, SEO
"""
from flask import Blueprint, render_template, redirect, url_for, Response, request, session
from flask_login import current_user
from datetime import datetime

public_bp = Blueprint('public', __name__)


@public_bp.route('/')
def landing():
    """Landing Page الفخمة"""
    lang = session.get('language', 'ar')
    if lang == 'en':
        return render_template('public/landing_en.html')
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


@public_bp.route('/sitemap.xml')
def sitemap():
    """
    خريطة الموقع الديناميكية لمحركات البحث
    Dynamic Sitemap for Search Engines (Google, Bing, etc.)
    """
    from models import Product, Customer, Sale
    
    # الحصول على URL الأساسي
    base_url = request.url_root.rstrip('/')
    
    # الصفحات الثابتة العامة (أولوية عالية)
    static_pages = [
        # الصفحات الرئيسية - أعلى أولوية
        {'loc': f'{base_url}/', 'priority': '1.0', 'changefreq': 'daily', 
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
    
    # المنتجات النشطة (آخر 100)
    try:
        products = Product.query.filter_by(is_active=True).order_by(
            Product.updated_at.desc()
        ).limit(100).all()
        
        for product in products:
            static_pages.append({
                'loc': f'{base_url}/products/{product.id}',
                'priority': '0.7',
                'changefreq': 'weekly',
                'lastmod': product.updated_at.strftime('%Y-%m-%d') if product.updated_at else None
            })
    except:
        pass
    
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

