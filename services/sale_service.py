from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from flask import current_app
from extensions import db
from models import PartnerCommissionEntry, Sale, SaleLine, Payment
from services.stock_service import StockService
from services.exchange_rate_service import ExchangeRateService
from services.gl_posting import post_or_fail, GlPostingError
from utils.gl_reference_types import GLRef
from services.commission_gl_service import post_sale_commissions
from services.gl_service import GLService
from utils.branching import ensure_warehouse_access
from utils.constants import normalize_payment_method_code
from utils.currency_utils import resolve_default_currency, get_system_default_currency, resolve_tenant_base_currency
from utils.field_validators import (
    canonical_payment_type,
    validate_currency_code,
    validate_payment_method,
    validate_sale_status,
)
from utils.helpers import generate_number
from utils.tenanting import get_active_tenant_id
from utils.tax_settings import normalize_tax_rate, should_post_vat_gl


class SaleService:

    @staticmethod
    def _commission_base_aed(profit_margin, exchange_rate):
        if profit_margin <= Decimal('0'):
            return Decimal('0')
        try:
            return (profit_margin * exchange_rate).quantize(
                Decimal('0.001'), rounding=ROUND_HALF_UP
            )
        except Exception:
            return profit_margin

    @staticmethod
    def create_sale(customer, seller, lines_data, warehouse_id=None, currency=None, user_exchange_rate=None,
                    discount_amount=0, shipping_cost=0, tax_rate=0, notes=None, payment_data=None,
                    source='internal', sale_status=None, checkout_payment_method=None,
                    defer_fulfillment=False, sales_rep_id=None):
        """
        Create a new sale with proper validations and decimal precision
        All financial calculations use Decimal for accuracy
        Uses database transaction with automatic rollback on error
        """
        # Input validations
        if not customer or not customer.is_active:
            raise ValueError('⚠️ العميل غير صالح أو غير نشط.\n💡 اختر عميل نشط من القائمة أو قم بتفعيله.')

        if not seller or not seller.is_active:
            raise ValueError('البائع غير صالح أو غير نشط')

        if not lines_data or len(lines_data) == 0:
            raise ValueError('⚠️ يجب إضافة منتج واحد على الأقل للفاتورة.\n💡 اضغط زر "➕ إضافة صف" واختر منتجاً.')

        if not currency:
            try:
                from models import Tenant
                currency = resolve_default_currency(Tenant.get_current())
            except Exception:
                currency = get_system_default_currency()
        currency = (currency or '').strip() or get_system_default_currency()
        currency = validate_currency_code(currency)

        # Validate discount and tax (rate finalized after tenant/warehouse resolved)
        discount_decimal = Decimal(str(discount_amount)) if discount_amount else Decimal('0')
        shipping_decimal = Decimal(str(shipping_cost)) if shipping_cost else Decimal('0')
        raw_tax_rate = Decimal(str(tax_rate)) if tax_rate else Decimal('0')

        if discount_decimal < Decimal('0'):
            raise ValueError('قيمة الخصم لا يمكن أن تكون سالبة')

        if shipping_decimal < Decimal('0'):
            raise ValueError('تكلفة الشحن لا يمكن أن تكون سالبة')

        # تحديد المستودع بطريقة ذكية مع عزل التينانت
        from models import Warehouse
        tenant_id = get_active_tenant_id(seller) or getattr(seller, 'tenant_id', None) or getattr(customer, 'tenant_id', None)
        if not warehouse_id:
            warehouse = None
            seller_branch_id = getattr(seller, 'branch_id', None)
            warehouse_query = Warehouse.query.filter_by(is_active=True)
            if tenant_id is not None:
                warehouse_query = warehouse_query.filter_by(tenant_id=tenant_id)
            if seller_branch_id:
                warehouse_query = warehouse_query.filter_by(branch_id=seller_branch_id)
            warehouse = warehouse_query.filter_by(is_main=True).first() or warehouse_query.first()
            if warehouse:
                warehouse_id = warehouse.id
        else:
            warehouse = ensure_warehouse_access(warehouse_id, user=seller)

        if not warehouse_id or not warehouse:
            raise ValueError('⚠️ لا يوجد مستودع متاح لهذا الفرع.\n💡 أنشئ مستودعاً للفرع أو اختر مستودعاً صحيحاً.')

        sale_branch_id = warehouse.branch_id or seller.branch_id
        tax_rate_decimal = normalize_tax_rate(raw_tax_rate, tenant_id)

        from utils.tax_settings import get_prices_include_vat
        prices_include_vat = get_prices_include_vat(tenant_id=tenant_id, branch_id=sale_branch_id)

        try:
            sale_number = generate_number(
                'S', Sale, 'sale_number', branch_id=sale_branch_id, tenant_id=tenant_id
            )
            paid_amount_aed = Decimal('0')

            from utils.currency_utils import resolve_tenant_base_currency
            base_currency = resolve_tenant_base_currency(tenant_id=tenant_id)
            rate_info = ExchangeRateService.resolve_exchange_rate_for_transaction(
                currency,
                base_currency,
                user_rate=user_exchange_rate,
                tenant_id=tenant_id,
            )
            if rate_info.get('rate_mode') == 'needs_input':
                raise ValueError(
                    '⚠️ سعر الصرف غير متوفر.\n'
                    '💡 اذهب إلى إعدادات المالك ← أسعار الصرف ← أدخل سعر يدوي، '
                    'أو أدخل سعراً في حقل "سعر الصرف" بالفاتورة.'
                )
            exchange_rate = Decimal(str(rate_info['rate']))

            # Validate exchange rate
            if exchange_rate <= Decimal('0'):
                raise ValueError('سعر الصرف غير صالح')

            # Create Sale Header
            sale = Sale(
                tenant_id=tenant_id,
                sale_number=sale_number,
                customer_id=customer.id,
                seller_id=seller.id,
                sales_rep_id=sales_rep_id,
                warehouse_id=warehouse_id,
                branch_id=sale_branch_id,
                currency=currency,
                exchange_rate=exchange_rate,
                discount_amount=discount_decimal,
                shipping_cost=shipping_decimal,
                tax_rate=tax_rate_decimal,
                prices_include_vat=prices_include_vat,
                total_amount=Decimal('0'),
                amount=Decimal('0'),
                amount_aed=Decimal('0'),
                notes=notes
            )

            db.session.add(sale)
            db.session.flush() # Get ID for lines

            subtotal = Decimal('0')

            for line_data in lines_data:
                product = line_data['product']
                quantity = Decimal(str(line_data['quantity']))

                # Validate quantity
                if quantity <= Decimal('0'):
                    raise ValueError(f'⚠️ المنتج "{product.name}": الكمية يجب أن تكون أكبر من صفر.\n💡 أدخل كمية صحيحة مثل: 1, 2, 5, 10')

                # Check stock availability
                available, msg = StockService.check_availability_in_warehouse(product.id, quantity, warehouse_id)
                if not available:
                    raise ValueError(f'{product.name}: {msg}')

                # Get unit price
                if line_data.get('unit_price'):
                    unit_price = Decimal(str(line_data['unit_price']))
                else:
                    unit_price = product.get_price_for_customer(customer.customer_type)

                # Validate unit price
                if unit_price <= Decimal('0'):
                    raise ValueError(f'⚠️ المنتج "{product.name}": السعر يجب أن يكون أكبر من صفر.\n💡 أدخل سعر صحيح بالدرهم.')

                discount_percent = Decimal(str(line_data.get('discount_percent', 0)))

                # Validate line discount
                if discount_percent < Decimal('0') or discount_percent > Decimal('100'):
                    raise ValueError(f'{product.name}: نسبة الخصم يجب أن تكون بين 0 و 100')

                # --- Serial Number Handling ---
                if product.has_serial_number:
                    from utils.serial_helpers import extract_serials, validate_serials
                    clean_serials = extract_serials(line_data)
                    validate_serials(clean_serials, product.name, int(quantity))

                    from models import ProductSerial
                    for sn in clean_serials:
                        existing_sn = ProductSerial.query.filter_by(
                            tenant_id=tenant_id,
                            product_id=product.id,
                            serial_number=sn
                        ).first()

                        if existing_sn:
                            if existing_sn.status not in ['available', 'returned']:
                                raise ValueError(f'⚠️ السيريال "{sn}" للمنتج "{product.name}" غير متاح للبيع (حالة: {existing_sn.status}).')
                            if warehouse_id and existing_sn.warehouse_id and existing_sn.warehouse_id != warehouse_id:
                                raise ValueError(f'⚠️ السيريال "{sn}" موجود في مستودع مختلف. يرجى تحويل المخزون أولاً.')
                        else:
                            allow_onsale = current_app.config.get('ALLOW_SERIAL_CREATION_ON_SALE', False)
                            if not allow_onsale:
                                raise ValueError(f'⚠️ السيريال "{sn}" للمنتج "{product.name}" غير موجود في النظام.\n💡 يجب إدخال الأرقام التسلسلية أثناء استلام المشتريات.')
                            existing_sn = ProductSerial(
                                tenant_id=tenant_id,
                                product_id=product.id,
                                serial_number=sn,
                                status='available',
                                warehouse_id=warehouse_id,
                            )
                            db.session.add(existing_sn)
                            db.session.flush()
                # ------------------------------

                # Create Sale Line

                # Create Sale Line
                line = SaleLine(
                    tenant_id=tenant_id,
                    sale_id=sale.id,
                    product_id=product.id,
                    quantity=quantity,
                    unit_price=unit_price,
                    discount_percent=discount_percent,
                    cost_price=Decimal(str(product.cost_price)) if product.cost_price else Decimal('0'),
                    line_total=Decimal('0'), # Initialize with 0
                    notes=line_data.get('notes') # Pass notes if any
                )

                # Calculate total before flush
                line.calculate_line_total()

                db.session.add(line)
                db.session.flush() # Get Line ID for serials

                subtotal += line.line_total

                # --- Partner Commission: calculated on NET PROFIT MARGIN (revenue - COGS) ---
                # Revenue excl VAT
                line_total_dec = Decimal(str(line.line_total))
                if sale.prices_include_vat and sale.tax_rate > 0:
                    revenue_excl_vat = (line_total_dec / (Decimal('1') + Decimal(str(sale.tax_rate)) / Decimal('100'))).quantize(
                        Decimal('0.001'), rounding=ROUND_HALF_UP
                    )
                else:
                    revenue_excl_vat = line_total_dec

                # Resolve unit cost from MWAC (or fallback to line.cost_price)
                try:
                    unit_cost, cost_source = StockService._resolve_cogs_unit_cost(
                        product.id, warehouse_id, tenant_id, line_cost_price=line.cost_price
                    )
                except Exception:
                    unit_cost = Decimal(str(line.cost_price)) if line.cost_price else Decimal('0')
                    cost_source = 'line_cost_price'

                qty_dec = Decimal(str(line.quantity)) if line.quantity else Decimal('0')
                cost_basis = (unit_cost * qty_dec).quantize(Decimal('0.001'), rounding=ROUND_HALF_UP)
                profit_margin = (revenue_excl_vat - cost_basis).quantize(Decimal('0.001'), rounding=ROUND_HALF_UP)

                base_amount = SaleService._commission_base_aed(profit_margin, exchange_rate)

                for ps in getattr(product, 'partner_shares', []) or []:
                    partner_customer_id = getattr(ps, 'partner_customer_id', None)
                    if not partner_customer_id:
                        continue
                    # Validate partner belongs to same tenant
                    from models import Customer
                    partner = Customer.query.filter_by(
                        id=partner_customer_id,
                        tenant_id=tenant_id,
                        customer_type='partner',
                    ).first()
                    if not partner:
                        current_app.logger.warning(
                            'Partner commission skipped: partner_customer_id=%s not found or not a partner in tenant=%s',
                            partner_customer_id, tenant_id
                        )
                        continue
                    pct = Decimal(str(getattr(ps, 'percentage', 0) or 0))
                    if pct <= Decimal('0'):
                        continue
                    commission_amount = (base_amount * (pct / Decimal('100'))).quantize(
                        Decimal('0.001'), rounding=ROUND_HALF_UP
                    )
                    if commission_amount <= Decimal('0'):
                        continue
                    entry = PartnerCommissionEntry(
                        tenant_id=tenant_id,
                        branch_id=sale_branch_id,
                        warehouse_id=warehouse_id,
                        sale_id=sale.id,
                        sale_line_id=line.id,
                        partner_customer_id=partner_customer_id,
                        product_id=product.id,
                        percentage=pct,
                        currency=currency,
                        base_currency=base_currency,
                        cost_basis=cost_basis,
                        profit_margin=profit_margin,
                        base_amount_aed=base_amount,
                        commission_amount_aed=commission_amount,
                    )
                    db.session.add(entry)

                # --- Link Serials to Sale Line ---
                if product.has_serial_number:
                    from models import ProductSerial
                    from datetime import datetime, timedelta
                    from utils.serial_helpers import extract_serials

                    clean_serials = extract_serials(line_data)
                    for sn in clean_serials:
                        serial_obj = ProductSerial.query.filter_by(
                            tenant_id=tenant_id,
                            product_id=product.id,
                            serial_number=sn
                        ).first()
                        if serial_obj:
                            serial_obj.status = 'sold'
                            serial_obj.sale_line_id = line.id
                            serial_obj.warehouse_id = warehouse_id
                            if product.warranty_days > 0:
                                serial_obj.warranty_start_date = datetime.now()
                                serial_obj.warranty_end_date = datetime.now() + timedelta(days=product.warranty_days)
                            db.session.add(serial_obj)
                # ---------------------------------

            sale.subtotal = subtotal
            sale.calculate_totals()

            # Handle payment if provided
            if payment_data:
                paid_amount = Decimal(str(payment_data.get('amount', 0)))
                payment_currency = payment_data.get('currency', get_system_default_currency())
                payment_exchange_rate = payment_data.get('exchange_rate', 1.0)

                # Convert payment to AED
                payment_exchange_decimal = Decimal(str(payment_exchange_rate)) if payment_exchange_rate else Decimal('1')
                paid_amount_aed = (paid_amount * payment_exchange_decimal).quantize(
                    Decimal('0.001'), rounding=ROUND_HALF_UP
                )

                # Validate payment amount (in AED)
                if paid_amount_aed < Decimal('0'):
                    raise ValueError('مبلغ الدفع لا يمكن أن يكون سالب')

                sale.paid_amount = paid_amount  # في عملة الفاتورة
                sale.paid_amount_aed = paid_amount_aed  # محول للدرهم

                # Handle overpayment (credit to customer)
                if paid_amount_aed > sale.amount_aed:
                    overpayment = paid_amount_aed - sale.amount_aed
                    payment_note = f"\n[دفع زائد] مبلغ {overpayment} AED سُجّل كرصيد للزبون"
                    sale.notes = (sale.notes or '') + payment_note

                # Add payment currency info to notes if not default
                default_curr = get_system_default_currency()
                if payment_currency.upper() != default_curr.upper():
                    payment_note = f"\n[دفعة] {paid_amount} {payment_currency} = {paid_amount_aed} {default_curr} (سعر: {payment_exchange_rate})"
                    sale.notes = (sale.notes or '') + payment_note

            sale.calculate_totals()

            db.session.flush()

            sale.source = source or 'internal'
            if sale_status:
                sale.status = validate_sale_status(sale_status)
            if checkout_payment_method:
                sale.checkout_payment_method = str(checkout_payment_method).strip().lower()[:50]

            if defer_fulfillment:
                try:
                    db.session.flush()
                except Exception:
                    current_app.logger.exception('Deferred sale flush failed for %s', sale.sale_number)
                    raise

                current_app.logger.info(f'Sale created (deferred): {sale.sale_number}')
                return sale

            SaleService.fulfill_sale(sale, payment_data=payment_data, paid_amount_aed=paid_amount_aed)

            try:
                db.session.flush()
            except Exception:
                current_app.logger.exception('Sale flush failed for %s', sale.sale_number)
                raise


            current_app.logger.info(f'Sale created: {sale.sale_number}')

            return sale

        except Exception:
            current_app.logger.exception('Sale creation failed for customer %s', getattr(customer, 'id', None))
            raise

    @staticmethod
    def fulfill_sale(sale, payment_data=None, paid_amount_aed=None):
        """
        Deduct stock, post GL, commissions, and customer balances for an existing sale.
        Used at POS checkout and when confirming deferred online store orders.
        """
        customer = sale.customer
        if not customer:
            raise ValueError('العميل غير موجود')

        warehouse_id = sale.warehouse_id
        tenant_id = getattr(sale, 'tenant_id', None)
        exchange_rate = Decimal(str(sale.exchange_rate or 1))

        if SaleService.has_inventory_posted(sale):
            raise ValueError('تم تنفيذ المخزون لهذه الفاتورة مسبقاً')

        for line in sale.lines:
            available, msg = StockService.check_availability_in_warehouse(
                line.product_id, line.quantity, warehouse_id
            )
            if not available:
                product_name = line.product.name if line.product else str(line.product_id)
                raise ValueError(f'{product_name}: {msg}')

        StockService.process_sale_lines(sale, warehouse_id)

        paid_aed = Decimal(str(paid_amount_aed)) if paid_amount_aed is not None else Decimal('0')
        if payment_data and payment_data.get('amount', 0) > 0:
            paid_amount = Decimal(str(payment_data.get('amount', 0)))
            payment_exchange_rate = payment_data.get('exchange_rate', 1.0)
            payment_exchange_decimal = Decimal(str(payment_exchange_rate)) if payment_exchange_rate else Decimal('1')
            paid_aed = (paid_amount * payment_exchange_decimal).quantize(
                Decimal('0.001'), rounding=ROUND_HALF_UP
            )
            if paid_aed < Decimal('0'):
                raise ValueError('مبلغ الدفع لا يمكن أن يكون سالب')

            sale.paid_amount = paid_amount
            sale.paid_amount_aed = paid_aed
            overpayment_aed = Decimal('0')
            if paid_aed > sale.amount_aed:
                overpayment_aed = paid_aed - sale.amount_aed
                payment_note = f"\n[دفع زائد] مبلغ {overpayment_aed} AED سُجّل كرصيد للزبون"
                sale.notes = (sale.notes or '') + payment_note

            payment_currency = payment_data.get('currency', get_system_default_currency())
            if payment_currency.upper() != get_system_default_currency().upper():
                payment_note = (
                    f"\n[دفعة] {paid_amount} {payment_currency} = {paid_aed} {get_system_default_currency()} "
                    f"(سعر: {payment_exchange_rate})"
                )
                sale.notes = (sale.notes or '') + payment_note

            if overpayment_aed > Decimal('0'):
                # Cap sale payment at invoice amount; remainder becomes prepayment
                overpayment_amount = (overpayment_aed / payment_exchange_decimal).quantize(
                    Decimal('0.001'), rounding=ROUND_HALF_UP
                )
                sale_payment_amount = paid_amount - overpayment_amount
                SaleService.create_payment_for_sale(
                    sale=sale,
                    amount=sale_payment_amount,
                    payment_method=payment_data['payment_method'],
                    currency=payment_currency,
                    exchange_rate=payment_data.get('exchange_rate', 1.0),
                    reference_number=payment_data.get('reference_number'),
                    cheque_number=payment_data.get('cheque_number'),
                    cheque_date=payment_data.get('cheque_date'),
                    bank_name=payment_data.get('bank_name'),
                    notes=payment_data.get('notes'),
                )
                # Record excess as customer prepayment (unlinked to sale for reuse)
                from models import Payment
                from utils.helpers import generate_number
                prepayment = Payment(
                    tenant_id=getattr(sale, 'tenant_id', None),
                    payment_number=generate_number(
                        'PRE',
                        Payment,
                        'payment_number',
                        branch_id=sale.branch_id,
                        tenant_id=getattr(sale, 'tenant_id', None),
                    ),
                    payment_type='prepayment',
                    direction='incoming',
                    customer_id=sale.customer_id,
                    amount=overpayment_amount,
                    currency=payment_currency,
                    exchange_rate=payment_exchange_decimal,
                    amount_aed=overpayment_aed,
                    payment_method=payment_data['payment_method'],
                    payment_confirmed=(payment_data['payment_method'] != 'cheque'),
                    notes=f"دفع زائد من فاتورة {sale.sale_number}",
                    user_id=sale.seller_id,
                    branch_id=sale.branch_id,
                )
                db.session.add(prepayment)
                db.session.flush()
                from decimal import Decimal as _D
                sale.customer.apply_receipt(_D(str(overpayment_aed or 0)))
            else:
                SaleService.create_payment_for_sale(
                    sale=sale,
                    amount=payment_data['amount'],
                    payment_method=payment_data['payment_method'],
                    currency=payment_data.get('currency', get_system_default_currency()),
                    exchange_rate=payment_data.get('exchange_rate', 1.0),
                    reference_number=payment_data.get('reference_number'),
                    cheque_number=payment_data.get('cheque_number'),
                    cheque_date=payment_data.get('cheque_date'),
                    bank_name=payment_data.get('bank_name'),
                    notes=payment_data.get('notes'),
                )

        sale.calculate_totals()
        customer.total_purchases += sale.amount_aed
        customer.update_classification()

        GLService.ensure_core_accounts(tenant_id=tenant_id)

        cogs_total_aed = StockService.calculate_sale_cogs_and_deduct(
            sale, warehouse_id=getattr(sale, 'warehouse_id', None)
        )

        ar_account = GLService.get_customer_credit_account(
            customer, branch_id=sale.branch_id, tenant_id=tenant_id
        )

        # When prices_include_vat=True, revenue/shipping/discount must be VAT-exclusive for GL balance
        if sale.prices_include_vat:
            tax_rate = Decimal(str(sale.tax_rate)) if sale.tax_rate else Decimal('0')
            if tax_rate > 0:
                divisor = Decimal('1') + (tax_rate / Decimal('100'))
                discount_debit = (sale.discount_amount / divisor).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                shipping_credit = (sale.shipping_cost / divisor).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                revenue_credit = (sale.taxable_amount - shipping_credit + discount_debit).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            else:
                revenue_credit = sale.subtotal
                shipping_credit = sale.shipping_cost
                discount_debit = sale.discount_amount
        else:
            revenue_credit = sale.subtotal
            shipping_credit = sale.shipping_cost
            discount_debit = sale.discount_amount

        gl_lines = [
            {
                'account': ar_account,
                'concept_code': GLService.get_customer_credit_concept(customer),
                'debit': sale.total_amount,
                'description': f'فاتورة {sale.sale_number}',
            },
            {
                'account': GLService.get_account_code_for_concept(
                    'SALES_REVENUE', branch_id=sale.branch_id, tenant_id=tenant_id, fallback_key='sales_revenue'
                ),
                'concept_code': 'SALES_REVENUE',
                'credit': revenue_credit,
                'description': 'إيرادات المبيعات',
            },
        ]

        if shipping_credit > Decimal('0'):
            gl_lines.append({
                'account': GLService.get_account_code_for_concept(
                    'SHIPPING_REVENUE', branch_id=sale.branch_id, tenant_id=tenant_id, fallback_key='shipping_revenue'
                ),
                'concept_code': 'SHIPPING_REVENUE',
                'credit': shipping_credit,
                'description': 'إيرادات الشحن',
            })

        if discount_debit > Decimal('0'):
            gl_lines.append({
                'account': GLService.get_account_code_for_concept(
                    'SALES_DISCOUNT', branch_id=sale.branch_id, tenant_id=tenant_id, fallback_key='discounts_given'
                ),
                'concept_code': 'SALES_DISCOUNT',
                'debit': discount_debit,
                'description': 'خصومات ممنوحة',
            })

        if sale.tax_amount > Decimal('0') and should_post_vat_gl(tenant_id):
            gl_lines.append({
                'account': GLService.get_account_code_for_concept(
                    'VAT_OUTPUT', branch_id=sale.branch_id, tenant_id=tenant_id, fallback_key='tax_payable'
                ),
                'concept_code': 'VAT_OUTPUT',
                'credit': sale.tax_amount,
                'description': 'ضرائب مستحقة (VAT Output)',
            })

        post_or_fail(
            gl_lines,
            description=f'Sale {sale.sale_number}',
            reference_type=GLRef.SALE,
            reference_id=sale.id,
            currency=sale.currency,
            exchange_rate=sale.exchange_rate,
            branch_id=sale.branch_id,
            tenant_id=tenant_id,
        )

        if cogs_total_aed > Decimal('0'):
            cogs_lines = [
                {
                    'account': GLService.get_account_code_for_concept(
                        'COGS', branch_id=sale.branch_id, tenant_id=tenant_id, fallback_key='cogs'
                    ),
                    'concept_code': 'COGS',
                    'debit': cogs_total_aed,
                    'description': 'تكلفة البضاعة المباعة',
                },
                {
                    'account': GLService.get_account_code_for_concept(
                        'INVENTORY_ASSET', branch_id=sale.branch_id, tenant_id=tenant_id, fallback_key='inventory'
                    ),
                    'concept_code': 'INVENTORY_ASSET',
                    'credit': cogs_total_aed,
                    'description': 'خصم من المخزون',
                },
            ]
            post_or_fail(
                cogs_lines,
                description=f'COGS - Sale {sale.sale_number}',
                reference_type=GLRef.SALE_COGS,
                reference_id=sale.id,
                exchange_rate=1.0,
                branch_id=sale.branch_id,
                tenant_id=tenant_id,
            )

        post_sale_commissions(sale)

        from decimal import Decimal as _D
        customer.apply_sale(_D(str(sale.amount_aed or 0)))

    @staticmethod
    def has_inventory_posted(sale):
        from models.warehouse import StockMovement
        return StockMovement.query.filter_by(
            reference_type=GLRef.SALE,
            reference_id=sale.id,
            movement_type='sale',
        ).first() is not None

    @staticmethod
    def create_payment_for_sale(sale, amount, payment_method, currency=None, exchange_rate=1.0,
                                reference_number=None, cheque_number=None, cheque_date=None,
                                bank_name=None, notes=None):
        """
        Create a payment for a sale with proper validations
        Uses Decimal for accurate financial calculations
        """
        from utils.helpers import generate_number
        from datetime import datetime, date

        # Validate payment amount
        amount_decimal = Decimal(str(amount))
        if amount_decimal <= Decimal('0'):
            raise ValueError('مبلغ الدفع يجب أن يكون أكبر من صفر')

        payment_method = validate_payment_method(payment_method)
        if not currency:
            currency = get_system_default_currency()
        currency = validate_currency_code(currency)

        # Validate cheque details if payment method is cheque
        if payment_method == 'cheque':
            if not cheque_number:
                raise ValueError('⚠️ رقم الشيك مطلوب عند الدفع بشيك.\n💡 أدخل رقم الشيك وتاريخ الاستحقاق واسم البنك.')
            if not cheque_date:
                raise ValueError('⚠️ تاريخ الاستحقاق مطلوب للشيك.\n💡 حدد تاريخ صرف الشيك من البنك.')
            if not bank_name:
                raise ValueError('⚠️ اسم البنك مطلوب للشيك.\n💡 أدخل اسم البنك المسحوب عليه الشيك.')

            # Convert cheque_date to date object if it's a string
            if isinstance(cheque_date, str):
                try:
                    cheque_date = datetime.strptime(cheque_date, '%Y-%m-%d').date()
                except ValueError:
                    raise ValueError('تاريخ الشيك غير صالح')

        payment_number = generate_number(
            'PAY',
            Payment,
            'payment_number',
            branch_id=sale.branch_id,
            tenant_id=getattr(sale, 'tenant_id', None),
        )

        # Calculate AED amount with proper rounding using PROVIDED exchange rate
        exchange_rate_decimal = Decimal(str(exchange_rate))
        amount_aed = (amount_decimal * exchange_rate_decimal).quantize(
            Decimal('0.001'), rounding=ROUND_HALF_UP
        )

        payment = Payment(
            tenant_id=getattr(sale, 'tenant_id', None),
            payment_number=payment_number,
            payment_type=canonical_payment_type('sale_payment'),
            sale_id=sale.id,
            customer_id=sale.customer_id,
            amount=amount_decimal,
            currency=currency,
            exchange_rate=exchange_rate_decimal,
            amount_aed=amount_aed,
            payment_method=payment_method,
            payment_confirmed=(payment_method != 'cheque'),
            confirmation_date=None if payment_method == 'cheque' else datetime.now(timezone.utc),
            reference_number=reference_number,
            cheque_number=cheque_number,
            cheque_date=cheque_date,
            bank_name=bank_name,
            notes=notes,
            user_id=sale.seller_id,
            branch_id=sale.branch_id,
        )

        db.session.add(payment)
        db.session.flush()

        # إنشاء سجل الشيك إذا كانت طريقة الدفع شيك
        if payment_method == 'cheque' and cheque_number:
            from models import Cheque
            cheque = Cheque(
                tenant_id=getattr(sale, 'tenant_id', None),
                branch_id=sale.branch_id,
                cheque_number=cheque_number,
                cheque_bank_number=cheque_number,  # نفس رقم الشيك
                cheque_type='incoming',
                customer_id=sale.customer_id,
                amount=amount_decimal,
                currency=currency,
                exchange_rate=exchange_rate_decimal,
                amount_aed=amount_aed,
                issue_date=sale.sale_date.date(),  # تاريخ الإصدار = تاريخ الفاتورة
                due_date=cheque_date,  # تاريخ الاستحقاق
                bank_name=bank_name,
                status='pending',
                notes=notes
            )
            db.session.add(cheque)
            db.session.flush()

            # ربط الشيك بالدفعة
            payment.cheque_id = cheque.id

        # GL Integration for Payment
        try:
            GLService.ensure_core_accounts(tenant_id=getattr(sale, 'tenant_id', None))

            if payment_method == 'cheque':
                debit_account = GLService.get_account_code_for_concept(
                    'CHEQUES_UNDER_COLLECTION',
                    branch_id=sale.branch_id,
                    tenant_id=getattr(sale, 'tenant_id', None),
                    fallback_key='cheques_under_collection',
                )
                debit_concept = 'CHEQUES_UNDER_COLLECTION'
            else:
                debit_account = GLService.get_payment_debit_account(
                    payment_method,
                    branch_id=sale.branch_id,
                    tenant_id=getattr(sale, 'tenant_id', None),
                )
                debit_concept = GLService.get_payment_debit_concept(payment_method)
            credit_account = GLService.get_customer_credit_account(
                sale.customer, branch_id=sale.branch_id, tenant_id=getattr(sale, 'tenant_id', None)
            )

            post_or_fail(
                [
                    {
                        'account': debit_account,
                        'concept_code': debit_concept,
                        'debit': amount_decimal,
                        'description': f'Payment for Sale {sale.sale_number} ({payment_method})'
                    },
                    {
                        'account': credit_account,
                        'concept_code': GLService.get_customer_credit_concept(sale.customer),
                        'credit': amount_decimal,
                        'description': f'Payment Received {payment.payment_number}'
                    }
                ],
                description=f'Payment {payment.payment_number}',
                reference_type=GLRef.PAYMENT,
                reference_id=payment.id,
                currency=currency,
                exchange_rate=exchange_rate_decimal,
                branch_id=sale.branch_id,
                tenant_id=getattr(sale, 'tenant_id', None),
            )
        except Exception as e:
            current_app.logger.error(f'GL posting failed for payment: {e}')
            raise
        from decimal import Decimal as _D
        sale.customer.apply_receipt(_D(str(amount_aed or 0)))
        sale.recalculate_payment_status()
        db.session.flush()

        # FX Gain/Loss auto-posting for direct payments (same currency, different rate)
        if currency and str(currency).upper() == str(sale.currency).upper():
            sale_rate = Decimal(str(sale.exchange_rate or 1))
            if sale_rate != exchange_rate_decimal and amount_decimal > 0:
                expected_aed = (amount_decimal * sale_rate).quantize(Decimal('0.001'), rounding=ROUND_HALF_UP)
                fx_diff = (amount_aed - expected_aed).quantize(Decimal('0.001'), rounding=ROUND_HALF_UP)
                if abs(fx_diff) > Decimal('0.01'):
                    try:
                        fx_lines = []
                        if fx_diff > 0:
                            fx_lines = [
                                {
                                    'account': GLService.get_account_code_for_concept(
                                        'AR', branch_id=sale.branch_id, tenant_id=getattr(sale, 'tenant_id', None), fallback_key='receivable'
                                    ),
                                    'concept_code': 'AR',
                                    'debit': fx_diff,
                                    'description': f'FX Gain Adjustment - Payment {payment.payment_number}'
                                },
                                {
                                    'account': GLService.get_account_code_for_concept(
                                        'FX_GAIN', branch_id=sale.branch_id, tenant_id=getattr(sale, 'tenant_id', None), fallback_key='fx_gain'
                                    ),
                                    'concept_code': 'FX_GAIN',
                                    'credit': fx_diff,
                                    'description': f'FX Gain - Payment {payment.payment_number}'
                                },
                            ]
                        else:
                            fx_lines = [
                                {
                                    'account': GLService.get_account_code_for_concept(
                                        'FX_LOSS', branch_id=sale.branch_id, tenant_id=getattr(sale, 'tenant_id', None), fallback_key='fx_loss'
                                    ),
                                    'concept_code': 'FX_LOSS',
                                    'debit': abs(fx_diff),
                                    'description': f'FX Loss - Payment {payment.payment_number}'
                                },
                                {
                                    'account': GLService.get_account_code_for_concept(
                                        'AR', branch_id=sale.branch_id, tenant_id=getattr(sale, 'tenant_id', None), fallback_key='receivable'
                                    ),
                                    'concept_code': 'AR',
                                    'credit': abs(fx_diff),
                                    'description': f'FX Loss Adjustment - Payment {payment.payment_number}'
                                },
                            ]
                        post_or_fail(
                            fx_lines,
                            description=f'FX Gain/Loss - Payment {payment.payment_number}',
                            reference_type=GLRef.PAYMENT,
                            reference_id=payment.id,
                            currency=get_system_default_currency(),
                            exchange_rate=1.0,
                            branch_id=sale.branch_id,
                            tenant_id=getattr(sale, 'tenant_id', None),
                        )
                    except Exception as fx_err:
                        current_app.logger.warning('FX auto-posting skipped for payment %s: %s', payment.payment_number, fx_err)

        return payment

    @staticmethod
    def cancel_sale(sale):
        if sale.status == 'cancelled':
            raise ValueError('الفاتورة ملغاة بالفعل')

        from models import Payment
        confirmed_payments = Payment.query.filter_by(
            sale_id=sale.id,
            payment_confirmed=True,
        ).count()
        if confirmed_payments > 0:
            raise ValueError('لا يمكن إلغاء فاتورة لها دفعات مؤكدة. قم بإلغاء الدفعات أولاً.')

        # Reject any pending payments/cheques linked to this sale
        pending_payments = Payment.query.filter_by(
            sale_id=sale.id,
            payment_confirmed=False,
        ).all()
        for pmt in pending_payments:
            if pmt.cheque_id:
                from services.cheque_service import process_cheque_cancel
                from models import Cheque
                cheque = db.session.get(Cheque,pmt.cheque_id)
                if cheque and cheque.status not in ['cancelled', 'bounced']:
                    process_cheque_cancel(cheque, reason=f'إلغاء فاتورة {sale.sale_number}')
            pmt.reject_payment(f'إلغاء فاتورة {sale.sale_number}')

        customer = sale.customer

        # عكس رصيد العميل وإحصائيات الشراء
        if customer:
            from decimal import Decimal as _D
            amount_aed = _D(str(sale.amount_aed or 0))
            customer.adjust_balance(+amount_aed)
            customer.total_purchases = max(
                (customer.total_purchases or _D('0')) - amount_aed,
                _D('0')
            )
            customer.update_classification()

        sale.status = 'cancelled'

        if SaleService.has_inventory_posted(sale):
            StockService.reverse_sale(sale)

            # Reverse GL Entry for Sale (Revenue & AR)
            try:
                GLService.reverse_entry(
                    reference_type=GLRef.SALE,
                    reference_id=sale.id,
                    description=f'Reverse Sale {sale.sale_number} (Cancelled)',
                    tenant_id=getattr(sale, 'tenant_id', None),
                )
                GLService.reverse_entry(
                    reference_type=GLRef.SALE_COGS,
                    reference_id=sale.id,
                    description=f'Reverse COGS {sale.sale_number} (Cancelled)',
                    tenant_id=getattr(sale, 'tenant_id', None),
                )
            except Exception as _e:
                current_app.logger.exception('GL reversal failed for cancelled sale %s', sale.sale_number)
                raise ValueError(f'فشل عكس القيد المحاسبي: {_e}') from _e

        # إعادة حساب حالة الدفع بعد الإلغاء
        sale.recalculate_payment_status()

        try:
            db.session.flush()
        except Exception:
            current_app.logger.exception('Cancel sale flush failed for %s', sale.sale_number)
            raise


        current_app.logger.info(f'Sale cancelled: {sale.sale_number}')

    @staticmethod
    def update_payment_status(sale):
        """
        Update payment status for a sale.
        Delegates to the canonical recalculate_payment_status() which correctly
        accounts for pending cheques, confirmed-only payments, and returns.
        """
        sale.recalculate_payment_status()
        try:
            db.session.flush()
        except Exception:
            current_app.logger.exception('Payment status update flush failed for %s', sale.sale_number)
            raise


