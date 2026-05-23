from decimal import Decimal, ROUND_HALF_UP
from flask import current_app
from extensions import db
from models import Sale, SaleLine, ProductReturn, ProductReturnLine, Product
from services.stock_service import StockService
from services.gl_service import GLService
from utils.helpers import generate_number

class ReturnService:
    
    @staticmethod
    def create_return(sale_id, return_lines_data, user_id=None, notes=None):
        """
        Create a product return (Sales Return) with financial and stock updates.
        
        Args:
            sale_id (int): The ID of the sale being returned.
            return_lines_data (list): List of dicts containing:
                - sale_line_id (int)
                - quantity (float/Decimal)
                - condition (str)
                - notes (str)
            user_id (int): ID of the user processing the return.
            notes (str): General notes for the return.
            
        Returns:
            ProductReturn: The created return record.
        """
        try:
            # 1. Validate Sale
            sale = Sale.query.get(sale_id)
            if not sale:
                raise ValueError(f"Sale with ID {sale_id} not found.")
            
            if sale.status == 'cancelled':
                raise ValueError("Cannot create return for a cancelled sale.")

            # 2. Prepare Return Record
            return_number = generate_number('R', ProductReturn, 'return_number', branch_id=sale.branch_id)
            
            product_return = ProductReturn(
                return_number=return_number,
                sale_id=sale.id,
                customer_id=sale.customer_id,
                branch_id=sale.branch_id, # Link to same branch as sale
                currency=sale.currency,
                exchange_rate=sale.exchange_rate,
                notes=notes,
                processed_by=user_id,
                status='approved'  # Immediate approval for now
            )
            
            product_return.total_amount = Decimal('0')
            product_return.refund_amount = Decimal('0')
            product_return.amount_aed = Decimal('0')
            
            db.session.add(product_return)
            db.session.flush() # Get ID
            
            total_return_amount = Decimal('0')
            gl_lines = []
            
            # 3. Process Lines
            for line_data in return_lines_data:
                sale_line_id = line_data.get('sale_line_id')
                quantity = Decimal(str(line_data.get('quantity', 0)))
                
                if quantity <= 0:
                    continue
                
                sale_line = SaleLine.query.get(sale_line_id)
                if not sale_line:
                    raise ValueError(f"Sale line {sale_line_id} not found.")
                
                if sale_line.sale_id != sale.id:
                    raise ValueError(f"Sale line {sale_line_id} does not belong to sale {sale.id}.")
                
                # Validate Quantity (Cannot return more than sold)
                # Note: This checks total sold. Ideally should check remaining returnable quantity if partial returns exist.
                # For now, let's assume simple validation against line quantity.
                # Future improvement: sum previous returns for this line.
                previous_returned = db.session.query(db.func.sum(ProductReturnLine.quantity))\
                    .join(ProductReturn)\
                    .filter(ProductReturnLine.sale_line_id == sale_line.id)\
                    .scalar() or Decimal('0')
                
                if (previous_returned + quantity) > sale_line.quantity:
                    raise ValueError(f"Cannot return {quantity} of {sale_line.product.name}. Already returned: {previous_returned}, Sold: {sale_line.quantity}.")

                # --- Serial Number Handling (Return) ---
                if sale_line.product.has_serial_number:
                    from models import ProductSerial
                    serials_to_return = line_data.get('serials', [])
                    required_qty = int(quantity)
                    
                    # For now, we skip serial check if none provided to avoid breaking existing returns
                    # But ideally we should enforce it.
                    if serials_to_return:
                        for sn in serials_to_return:
                            sn = sn.strip()
                            # Find the serial record
                            serial_obj = ProductSerial.query.filter_by(
                                product_id=sale_line.product_id, 
                                serial_number=sn,
                                sale_line_id=sale_line.id
                            ).first()
                            
                            if serial_obj:
                                # Update status
                                condition = line_data.get('condition', 'good')
                                serial_obj.status = 'available' if condition == 'good' else 'defective'
                                serial_obj.sale_line_id = None 
                                serial_obj.warranty_end_date = None # Cancel warranty? Or suspend? Let's cancel for now.
                                
                                db.session.add(serial_obj)
                # ---------------------------------------

                # Calculate refund amount for this line
                # Pro-rata calculation: (Line Total / Quantity) * Return Quantity
                # But usually it's Unit Price * Return Quantity
                unit_price = sale_line.unit_price
                line_total = (unit_price * quantity).quantize(Decimal('0.001'), rounding=ROUND_HALF_UP)
                
                # Pro-rata Global Discount Allocation
                # Calculate proportion of this line to total sale subtotal
                if sale.subtotal > 0 and sale.discount_amount > 0:
                    # Line's share of discount = (Line Return Amount / Sale Subtotal) * Sale Discount Amount
                    # Note: We use the returned amount as the basis
                    discount_share = (line_total / sale.subtotal * sale.discount_amount).quantize(Decimal('0.001'), rounding=ROUND_HALF_UP)
                    # Adjust line total (Net Line Return = Gross - Discount Share)
                    # Wait, ProductReturnLine usually stores GROSS amount. The refund amount on header should be NET.
                    # We store Gross in line_total, but we need to track discount somewhere or adjust header.
                    # Let's adjust the accumulation for header totals.
                    net_line_return = line_total - discount_share
                else:
                    discount_share = Decimal('0')
                    net_line_return = line_total

                # Pro-rata Shipping Allocation (Optional - based on user request)
                if sale.subtotal > 0 and sale.shipping_cost > 0:
                    shipping_share = (line_total / sale.subtotal * sale.shipping_cost).quantize(Decimal('0.001'), rounding=ROUND_HALF_UP)
                    # Shipping is usually ADDED to refund if we are refunding shipping
                    net_line_return += shipping_share
                else:
                    shipping_share = Decimal('0')

                total_return_amount += net_line_return
                
                # Create Return Line
                return_line = ProductReturnLine(
                    return_id=product_return.id,
                    sale_line_id=sale_line.id,
                    product_id=sale_line.product_id,
                    quantity=quantity,
                    unit_price=unit_price,
                    line_total=line_total, # Store GROSS for record
                    condition=line_data.get('condition'),
                    notes=line_data.get('notes')
                )
                db.session.add(return_line)
                
                # Stock Update: Return to Inventory
                # Using 'return' movement type
                StockService.create_movement(
                    product_id=sale_line.product_id,
                    quantity=quantity,
                    movement_type='return',
                    reference_type='ProductReturn',
                    reference_id=product_return.id,
                    notes=f"Return for Sale {sale.sale_number}",
                    warehouse_id=sale.warehouse_id # Return to same warehouse
                )
                
                # Prepare COGS Reversal GL Data (Credit COGS, Debit Inventory)
                # Need Cost Price. 
                # Ideally, we track cost at time of sale. If not available, use current cost.
                product = Product.query.get(sale_line.product_id)
                cost_price = product.cost_price if product else Decimal('0')
                cost_value = (quantity * cost_price).quantize(Decimal('0.001'), rounding=ROUND_HALF_UP)
                
                if cost_value > 0:
                     # Inventory (Asset) - Debit (Increase)
                    gl_lines.append({
                        'account': '1140', 
                        'debit': cost_value,
                        'credit': 0,
                        'description': f'Inventory Restock - {product.name}'
                    })
                    # COGS (Expense) - Credit (Decrease)
                    gl_lines.append({
                        'account': '5100', 
                        'debit': 0,
                        'credit': cost_value,
                        'description': f'COGS Reversal - {product.name}'
                    })

            product_return.calculate_totals()
            
            # Update header totals to match Net Calculation (Important!)
            # calculate_totals() usually sums line_totals (Gross). We want Refund Amount to be Net.
            # So we override refund_amount with our calculated net_return_amount.
            
            # 4. Financial GL Entries (Revenue Reversal)
            
            tax_rate = sale.tax_rate or Decimal('0')
            
            net_return_amount = total_return_amount # This is now (Gross - Discount + Shipping)
            
            # Calculate Tax Refund
            # Tax is applied on (Gross - Discount + Shipping)
            # So we apply tax rate on our net_return_amount base
            
            tax_amount = (net_return_amount * (tax_rate / Decimal('100'))).quantize(Decimal('0.001'), rounding=ROUND_HALF_UP)
            gross_return_amount = net_return_amount + tax_amount
            
            product_return.refund_amount = gross_return_amount 
            product_return.amount_aed = (gross_return_amount * product_return.exchange_rate).quantize(Decimal('0.001'), rounding=ROUND_HALF_UP)
            
            # Debit Sales Revenue (or Sales Returns)
            # We debit the amount EXCLUDING tax.
            # Note: net_return_amount includes shipping refund. Shipping refund should be debited to Shipping Income?
            # Or simplified: Debit Revenue with the full net amount.
            
            gl_lines.append({
                'account': '4100', # Sales Revenue
                'debit': net_return_amount,
                'credit': 0,
                'description': f'Sales Return Revenue Reversal {sale.sale_number}'
            })
            
            # Debit Tax Liability (Reducing liability)
            if tax_amount > 0:
                gl_lines.append({
                    'account': '2130', # Taxes Payable
                    'debit': tax_amount,
                    'credit': 0,
                    'description': f'Sales Return Tax Reversal {sale.sale_number}'
                })
            
            # Credit Accounts Receivable (Reducing customer debt)
            gl_lines.append({
                'account': GLService.get_customer_credit_account(sale.customer),
                'debit': 0,
                'credit': gross_return_amount,
                'description': f'Credit Customer for Return {sale.sale_number}'
            })
            
            # Post GL Entry
            if gl_lines:
                GLService.post_entry(
                    lines=gl_lines,
                    description=f'Sales Return {product_return.return_number} for Sale {sale.sale_number}',
                    reference_type='ProductReturn',
                    reference_id=product_return.id,
                    branch_id=product_return.branch_id
                )
            
            # Update Customer Balance (use helper for clarity)
            if sale.customer:
                sale.customer.apply_return(product_return.amount_aed)
            
            # Recalculate Sale Payment Status (Smart Handling for Partial Payments)
            if hasattr(sale, 'recalculate_payment_status'):
                # Force refresh of returns relationship
                db.session.expire(sale, ['returns'])
                sale.recalculate_payment_status()
                
            db.session.commit()
            return product_return
            
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Failed to create return: {e}")
            raise e
