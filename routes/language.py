"""
Language Routes - تبديل اللغة
"""
from flask import Blueprint, request, redirect, url_for, session, flash
from flask_login import login_required

language_bp = Blueprint('language', __name__, url_prefix='/language')


@language_bp.route('/set/<lang>')
def set_language(lang):
    """تغيير اللغة"""
    if lang in ['ar', 'en']:
        session['language'] = lang
        flash(f'تم تغيير اللغة إلى {"العربية" if lang == "ar" else "English"}', 'success')
    
    return redirect(request.referrer or url_for('public.landing'))

