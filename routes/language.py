"""
Language Routes - تبديل اللغة
"""
from flask import Blueprint, request, redirect, url_for, session, flash
from utils.safe_redirect import safe_redirect_target

language_bp = Blueprint('language', __name__, url_prefix='/language')


@language_bp.route('/set/<lang>')
def set_language(lang):
    """تغيير اللغة"""
    if lang in ['ar', 'en']:
        session['language'] = lang
        flash(f'تم تغيير اللغة إلى {"العربية" if lang == "ar" else "English"}', 'success')
    
    return redirect(safe_redirect_target(request.referrer, 'public.landing'))

