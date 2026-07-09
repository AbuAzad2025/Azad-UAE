"""AI system data query routes (customer, product, sales lookups)."""

import json
import logging
from datetime import datetime, timezone
from flask import render_template, request, jsonify, current_app
from flask_login import login_required, current_user
from utils.decorators import permission_required
from sqlalchemy import func, desc
from extensions import db
from models import (
    Customer, Product, Sale, SaleLine, Purchase, Payment, Receipt,
    StockMovement, AuditLog,
)
from services.ai_service import AIService
from services.logging_core import LoggingCore
from ai_knowledge.core.system_integration import system_integrator
from ai_knowledge.analytics.data_analyzer import data_analyzer
from routes.ai_routes import ai_bp

logger = logging.getLogger(__name__)

@ai_bp.route('/system/customer-balance/<customer_name>')
@login_required
@permission_required('manage_customers')
def get_customer_balance(customer_name):
    """جلب رصيد العميل بدقة"""
    try:
        result = system_integrator.get_customer_balance(customer_name)
        return jsonify(result)
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@ai_bp.route('/system/customer-debt/<int:customer_id>')
@login_required
@permission_required('manage_customers')
def analyze_customer_debt(customer_id):
    """تحليل ديون العميل بالتفصيل"""
    try:
        result = data_analyzer.analyze_customer_debt(customer_id)
        return jsonify(result)
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@ai_bp.route('/system/product-stock/<product_name>')
@login_required
@permission_required('manage_products')
def get_product_stock(product_name):
    """جلب مخزون المنتج بدقة"""
    try:
        result = system_integrator.get_product_stock(product_name)
        return jsonify(result)
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@ai_bp.route('/system/summary')
@login_required
@permission_required('view_reports')
def get_system_summary():
    """ملخص النظام الشامل"""
    try:
        result = system_integrator.get_system_summary()
        financial_result = system_integrator.get_financial_summary()
        
        return jsonify({
            'success': True,
            'summary': result.get('summary', {}),
            'financial': financial_result.get('financial', {})
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@ai_bp.route('/system/search/<search_term>')
@login_required
@permission_required('view_reports')
def search_system_data(search_term):
    """البحث في بيانات النظام"""
    try:
        result = system_integrator.search_data(search_term)
        return jsonify(result)
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@ai_bp.route('/system/add-customer', methods=['POST'])
@login_required
@permission_required('manage_customers')
def add_customer():
    """إضافة عميل جديد"""
    try:
        data = request.get_json(silent=True)
        result = system_integrator.add_customer(data)
        return jsonify(result)
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@ai_bp.route('/data/analyze-sales')
@login_required
@permission_required('view_reports')
def analyze_sales_performance():
    """تحليل أداء المبيعات"""
    try:
        period_days = request.args.get('period', 30, type=int)
        result = data_analyzer.analyze_sales_performance(period_days)
        return jsonify(result)
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@ai_bp.route('/data/analyze-products')
@login_required
@permission_required('view_products')
def analyze_product_performance():
    """تحليل أداء المنتجات"""
    try:
        product_id = request.args.get('product_id', type=int)
        result = data_analyzer.analyze_product_performance(product_id)
        return jsonify(result)
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@ai_bp.route('/data/financial-ratios')
@login_required
@permission_required('view_reports')
def get_financial_ratios():
    """النسب المالية"""
    try:
        result = data_analyzer.get_financial_ratios()
        return jsonify(result)
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


