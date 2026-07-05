import re

path = r'D:\Data\karaj\UAE\Azad-UAE\routes\owner.py'

with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# Find the line after currency_settings return and before payment-gateways
marker = "@owner_bp.route('/payment-gateways', methods=['GET', 'POST'])"
if marker not in content:
    print("Marker not found")
    exit(1)

new_route = '''

@owner_bp.route('/exchange-rates', methods=['GET', 'POST'])
@login_required
@owner_required
def exchange_rates():
    """إدارة أسعار الصرف — Manual rate entry and history."""
    from services.exchange_rate_service import ExchangeRateService
    from models import ExchangeRateRecord
    from datetime import date

    today = date.today().isoformat()

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
                rec = ExchangeRateRecord.query.get(record_id)
                if rec:
                    db.session.delete(rec)
                    db.session.commit()
                    flash('✅ تم حذف السجل.', 'success')

        return redirect(url_for('owner.exchange_rates'))

    # GET: show records
    tenant_id = getattr(current_user, 'tenant_id', None)
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
'''

content = content.replace(marker, new_route + '\n' + marker)

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)

print("Route inserted")
